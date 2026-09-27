"""Core Argo profile adapter. Adjusted-mode records never fall back to raw values."""

import hashlib
from pathlib import Path

import gsw
import numpy as np
import xarray as xr

from adapters.cf_model import decoded_values, json_value
from science.contracts import Observation, UnsupportedData

GOOD_QC = {"1", "2"}


def text(value) -> str:
    a = np.asarray(value)
    if a.ndim == 0:
        v = a.item()
        return v.decode().strip() if isinstance(v, bytes) else str(v).strip()
    return "".join(text(v) for v in a).strip()


def parse_argo(path: Path, source_url: str) -> list[Observation]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with xr.open_dataset(path, engine="netcdf4", decode_times=False, mask_and_scale=False) as source:
        raw_juld = decoded_values(source.JULD)
    with xr.open_dataset(path, engine="netcdf4", decode_times=True, mask_and_scale=False) as ds:
        if "N_PROF" not in ds.dims or "N_LEVELS" not in ds.dims or ds.sizes["N_LEVELS"] > 10000 or ds.sizes["N_PROF"] > 500:
            raise UnsupportedData("unsupported_profile", "A bounded core Argo profile file is required.")
        result = []
        for i in range(ds.sizes["N_PROF"]):
            p = ds.isel(N_PROF=i)
            mode = text(p.DATA_MODE.values)
            if mode not in {"D", "A", "R"}:
                raise UnsupportedData("unsupported_data_mode", "Argo DATA_MODE must be R, A or D.")
            if "PARAMETER_DATA_MODE" in p:
                raise UnsupportedData("unsupported_profile", "Per-parameter BGC modes require the later BGC adapter.")
            lat, lon = float(decoded_values(p.LATITUDE)), float(decoded_values(p.LONGITUDE))
            if not np.isfinite([lat, lon]).all() or abs(lat) > 90 or not -180 <= lon <= 180:
                raise UnsupportedData("invalid_position", "Argo position is missing or outside geographic bounds.")
            if np.isnat(p.JULD.values):
                raise UnsupportedData("invalid_time", "Argo timestamp is missing.")
            # Floating-day decoding can yield 12.999999936 instead of 13 seconds.
            seconds = int(np.rint(p.JULD.values.astype("datetime64[ns]").astype(np.int64) / 1e9))
            stamp = np.datetime_as_string(np.datetime64(seconds, "s"), unit="s") + "Z"
            position_qc, time_qc = text(p.POSITION_QC.values), text(p.JULD_QC.values)
            selected, raw, flags, errors, raw_flags, adjusted, adjusted_flags = {}, {}, {}, {}, {}, {}, {}
            fields = {}
            definitions = {"PRES": ("sea_water_pressure", {"decibar", "dbar"}), "TEMP": ("sea_water_temperature", {"degree_Celsius", "degrees_Celsius", "degC"}), "PSAL": ("sea_water_salinity", {"psu", "1"})}
            for name, (standard, units) in definitions.items():
                choice = name if mode == "R" else name + "_ADJUSTED"
                required = [name, name + "_QC", choice, choice + "_QC"]
                if any(k not in p for k in required):
                    raise UnsupportedData("missing_variable", f"Required Argo parameter/QC missing: {choice}.")
                if p[choice].attrs.get("units") not in units or p[choice].attrs.get("standard_name") != standard:
                    raise UnsupportedData("incompatible_variable", f"Unsupported Argo definition or units for {choice}.")
                fields[name] = choice
                selected[name] = decoded_values(p[choice])
                raw[name] = decoded_values(p[name])
                flags[name] = [text(v) for v in p[choice + "_QC"].values]
                raw_flags[name] = [text(v) for v in p[name + "_QC"].values]
                adjusted[name] = decoded_values(p[name + "_ADJUSTED"]) if name + "_ADJUSTED" in p else np.full_like(selected[name], np.nan)
                adjusted_flags[name] = [text(v) for v in p[name + "_ADJUSTED_QC"].values] if name + "_ADJUSTED_QC" in p else [""] * len(selected[name])
                errors[name] = decoded_values(p[name + "_ADJUSTED_ERROR"]) if name + "_ADJUSTED_ERROR" in p else np.full_like(selected[name], np.nan)
            # A pressure reading in dbar is not a depth in metres. Preserve both.
            pressure = selected["PRES"]
            depth = np.full_like(pressure, np.nan)
            valid_pressure = np.isfinite(pressure) & (pressure >= 0)
            depth[valid_pressure] = -gsw.z_from_p(pressure[valid_pressure], lat)
            eligible = np.array([position_qc in GOOD_QC and time_qc in GOOD_QC and all(flags[name][j] in GOOD_QC and np.isfinite(selected[name][j]) for name in definitions) and valid_pressure[j] for j in range(len(pressure))])
            levels = []
            for j in range(len(pressure)):
                levels.append({"source_level_index": j, "pressure_dbar": json_value(pressure[j]), "depth_m": json_value(depth[j]), "temperature_c": json_value(selected["TEMP"][j]), "salinity_psu": json_value(selected["PSAL"][j]), "eligible": bool(eligible[j]), "qc": {k: flags[k][j] for k in definitions}, "parameters": {k: {"raw": json_value(raw[k][j]), "raw_qc": raw_flags[k][j], "adjusted": json_value(adjusted[k][j]), "adjusted_qc": adjusted_flags[k][j], "adjusted_error": json_value(errors[k][j])} for k in definitions}})
            # Retain source order/index; consumers must not assume regular or sorted levels.
            platform, cycle = text(p.PLATFORM_NUMBER.values), int(p.CYCLE_NUMBER)
            meta = {"global": json_value(ds.attrs), "juld": {"units": p.JULD.encoding.get("units"), "calendar": p.JULD.encoding.get("calendar", "standard")}, "parameter_attributes": {name: json_value(p[name].attrs) for name in p.data_vars if name.startswith(("PRES", "TEMP", "PSAL"))}, "calibration": {k: json_value(p[k].values) for k in p.data_vars if k.startswith("SCIENTIFIC_CALIB")}, "date_update": text(ds.DATE_UPDATE.values) if "DATE_UPDATE" in ds else None}
            meta["juld"].update({"source_numeric": float(raw_juld[i]), "decoded_source_time": np.datetime_as_string(p.JULD.values, unit="ns") + "Z", "normalization": "Rounded to nearest second; original numeric days retained."})
            result.append(Observation(id=f"argo-{platform}-{cycle:03d}-{i}", platform=platform, cycle=cycle, time=stamp, latitude=lat, longitude=lon, data_mode=mode, position_qc=position_qc, time_qc=time_qc, samples=len(levels), eligible_samples=int(eligible.sum()), depth_range_m=(float(depth[eligible].min()), float(depth[eligible].max())) if eligible.any() else None, source_id="argo-gdac-incois", source_file=path.name, source_sha256=digest, source_url=source_url, selected_fields=fields, units={"pressure": "dbar", "depth": "m", "temperature": "°C", "salinity": "psu"}, definitions={"temperature": "In-situ temperature, ITS-90", "salinity": "Practical salinity, PSS-78"}, qc_policy="Eligible samples require selected PRES/TEMP/PSAL QC 1 or 2, position/time QC 1 or 2, finite values and nonnegative pressure. No raw fallback in A/D mode.", depth_method=f"-gsw.z_from_p(selected pressure, profile latitude), GSW {gsw.__version__}; dynamic height and sea-surface geopotential use library defaults (zero).", levels=levels, source_metadata=meta))
        return result
