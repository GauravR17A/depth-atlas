"""Bounded rectilinear CF NetCDF adapter. No inferred units or grid rotation."""

from dataclasses import dataclass
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr

from science.contracts import Coordinates, UnsupportedData, Variable

MODEL_VARIABLES = {
    "temperature": ("water_temp", "sea_water_temperature", {"degC", "degree_Celsius", "degrees_Celsius"}, "°C", "In-situ temperature", "In-situ seawater temperature; not potential or conservative temperature."),
    "salinity": ("salinity", "sea_water_salinity", {"psu"}, "psu", "Salinity", "Source-defined practical salinity; not absolute salinity in g/kg."),
    "eastward_velocity": ("water_u", "eastward_sea_water_velocity", {"m/s", "m s-1"}, "m/s", "Eastward current", "Horizontal velocity, positive east; not grid-relative velocity."),
    "northward_velocity": ("water_v", "northward_sea_water_velocity", {"m/s", "m s-1"}, "m/s", "Northward current", "Horizontal velocity, positive north; not grid-relative velocity."),
}


def json_value(value):
    if isinstance(value, np.ndarray):
        return [json_value(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def decoded_values(variable: xr.DataArray) -> np.ndarray:
    """Mask in packed space before applying source scale/offset once, in float64."""
    a = np.asarray(variable.values)
    if a.dtype.kind not in "iuf":
        raise UnsupportedData("unsupported_dtype", f"{variable.name} must be numeric.")
    if str(variable.attrs.get("_Unsigned", "false")).lower() == "true":
        raise UnsupportedData("unsupported_packing", "Unsigned reinterpretation is not supported by this adapter.")
    mask = ~np.isfinite(a)
    for name in ("_FillValue", "missing_value"):
        for fill in np.atleast_1d(variable.attrs.get(name, [])):
            mask |= a == fill
    attrs = variable.attrs
    if "valid_range" in attrs:
        low, high = attrs["valid_range"]
        mask |= (a < low) | (a > high)
    if "valid_min" in attrs:
        mask |= a < attrs["valid_min"]
    if "valid_max" in attrs:
        mask |= a > attrs["valid_max"]
    scale, offset = float(attrs.get("scale_factor", 1)), float(attrs.get("add_offset", 0))
    if not np.isfinite(scale) or scale == 0 or not np.isfinite(offset):
        raise UnsupportedData("invalid_packing", f"Invalid scale or offset for {variable.name}.")
    result = a.astype(np.float64) * scale + offset
    return np.where(mask, np.nan, result)


@dataclass
class ModelGrid:
    coordinates: Coordinates
    fields: dict[str, np.ndarray]
    variables: list[Variable]
    source_metadata: dict
    transformations: list[str]


def load_model(path: Path, variable_map: dict[str, str] | None = None, *, axis_map: dict[str, str] | None = None, variable_specs: dict | None = None) -> ModelGrid:
    specs = variable_specs if variable_specs is not None else MODEL_VARIABLES
    mapping = variable_map or {key: value[0] for key, value in specs.items()}
    if set(mapping) != set(MODEL_VARIABLES) or set(specs) != set(MODEL_VARIABLES):
        raise UnsupportedData("incompatible_variables", "Temperature, salinity and both horizontal velocity components are required.")
    with xr.open_dataset(path, engine="netcdf4", decode_cf=False, mask_and_scale=False) as ds:
        if axis_map:
            if set(axis_map.values()) != {'time', 'depth', 'lat', 'lon'} or len(axis_map) != 4 or any(k not in ds for k in axis_map):
                raise UnsupportedData('unsupported_grid', 'The adapter must map four distinct coordinate axes.')
            ds = ds.rename({source: target for source, target in axis_map.items() if source != target})
        axes = ("time", "depth", "lat", "lon")
        for name in axes:
            if name not in ds or ds[name].dims != (name,) or ds.sizes[name] == 0:
                raise UnsupportedData("unsupported_grid", "Only nonempty independent time/depth/lat/lon axes are supported.")
        if np.prod([ds.sizes[k] for k in axes]) * 4 > 12_000_000:
            raise UnsupportedData("dataset_too_large", "This preparation path is limited to 12 million scalar values. Subset first.")
        if ds.lat.attrs.get("units") not in {"degrees_north", "degree_north"} or ds.lon.attrs.get("units") not in {"degrees_east", "degree_east"}:
            raise UnsupportedData("unsupported_units", "Latitude/longitude must explicitly use degrees north/east.")
        if ds.depth.attrs.get("units") not in {"m", "metre", "meter"} or ds.depth.attrs.get("positive") not in {"down", "up"}:
            raise UnsupportedData("unsupported_depth", "Depth must explicitly declare metres and its positive direction; pressure and sigma axes need another adapter.")
        time = decoded_values(ds.time)
        depth = decoded_values(ds.depth) * (-1 if ds.depth.attrs["positive"] == "up" else 1)
        lat, lon_original = decoded_values(ds.lat), decoded_values(ds.lon)
        if np.any(np.abs(lat) > 90) or np.any(depth < 0) or np.any(lon_original < -180) or np.any(lon_original > 360):
            raise UnsupportedData("invalid_coordinates", "Coordinates are outside supported geographic/depth bounds.")
        # Preserve the exact floats already in range; modulo would perturb them.
        lon = np.where(lon_original >= 180, lon_original - 360, lon_original)
        order = {}
        for name, values in zip(axes, (time, depth, lat, lon)):
            if not np.isfinite(values).all() or len(np.unique(values)) != len(values):
                raise UnsupportedData("invalid_coordinates", f"{name} contains missing or duplicate coordinates.")
            order[name] = np.argsort(values)
        calendar = ds.time.attrs.get("calendar", "standard")
        if calendar not in {"standard", "gregorian", "proleptic_gregorian"}:
            raise UnsupportedData("unsupported_calendar", f"Calendar {calendar} requires a separate time representation.")
        units = ds.time.attrs.get("units", "")
        try:
            times = netCDF4.num2date(time[order["time"]], units, calendar=calendar)
        except (ValueError, TypeError) as exc:
            raise UnsupportedData("invalid_time", "Time needs valid CF numeric units and a supported calendar.") from exc
        coordinates = Coordinates(times=[t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times], depth_m=depth[order["depth"]].tolist(), latitude=lat[order["lat"]].tolist(), longitude=lon[order["lon"]].tolist(), calendar=calendar, source_time_units=units, source_depth_units=ds.depth.attrs["units"], source_longitude_convention="0 to 360" if np.all(lon_original >= 0) else "-180 to 180")
        fields, variables = {}, []
        for key, source_name in mapping.items():
            _, standard, allowed_units, unit, label, definition = specs[key]
            if source_name not in ds:
                raise UnsupportedData("missing_variable", f"Required variable {source_name} is absent.")
            v = ds[source_name]
            if len(v.dims) != 4 or set(v.dims) != set(axes):
                raise UnsupportedData("unsupported_grid", f"{source_name} must share the rectilinear grid; staggered grids are unsupported.")
            if v.attrs.get("standard_name") != standard or v.attrs.get("units") not in allowed_units:
                raise UnsupportedData("incompatible_variable", f"{source_name} has an unsupported definition or units.")
            a = decoded_values(v.transpose(*axes))
            for dim, name in enumerate(axes):
                a = np.take(a, order[name], axis=dim)
            fields[key] = a
            packing = {k: json_value(v.attrs[k]) for k in ("_FillValue", "missing_value", "scale_factor", "add_offset", "valid_min", "valid_max", "valid_range") if k in v.attrs}
            variables.append(Variable(id=key, source_name=source_name, label=label, standard_name=standard, units=unit, source_units=v.attrs["units"], definition=definition, packing=packing))
        metadata = {"global": json_value(ds.attrs), "variables": {k: {"dtype": str(ds[k].dtype), "dimensions": list(ds[k].dims), "attributes": json_value(ds[k].attrs)} for k in [*axes, *mapping.values()]}, "original_coordinates": {k: json_value(ds[k].values) for k in axes}}
        return ModelGrid(coordinates, fields, variables, metadata, ["Mask fill/missing and declared valid ranges before decoding source scale/offset once in float64.", "Normalize longitude to [-180,180); sort coordinates and reorder matching array axes.", "Convert explicitly positive-up metre coordinates to positive-down depth when present.", "Preserve all supplied time steps and irregular depth levels; no interpolation or hole filling."])
