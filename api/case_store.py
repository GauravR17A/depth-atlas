"""Bounded immutable case-pack access; registered products use native NumPy arrays."""

from array import array
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

from science.contracts import CaseManifest, Observation, OperationResult, UnsupportedData
from science.case_recipes import RECIPES

CASE_ID = "bay-bengal-2024-01"
PACIFIC_CASE_IDS = tuple(f'pacific-godas-{year}-son' for year in (2013, 2015, 2022))
CASE_IDS = (CASE_ID, 'arabian-sea-2024-01', *PACIFIC_CASE_IDS,
            *(key for key in RECIPES if key not in {CASE_ID, 'arabian-sea-2024-01'}))
MAX_VALUES = 100_000


class CaseStore:
    def __init__(self, root: Path):
        self.root = root

    @lru_cache(maxsize=8)
    def manifest(self, case_id=CASE_ID) -> tuple[CaseManifest, str] | None:
        if case_id not in CASE_IDS:
            return None
        path = self.root / case_id / "manifest.json"
        if not path.exists():
            return None
        body = path.read_bytes()
        manifest = CaseManifest.model_validate_json(body)
        if manifest.case.id != case_id:
            raise UnsupportedData('case_integrity_error', 'Case identity does not match its catalogue entry.')
        return manifest, hashlib.sha256(body).hexdigest()

    def available(self):
        return [entry for case_id in CASE_IDS if (entry := self.manifest(case_id)) is not None]

    def require(self, case_id: str) -> tuple[CaseManifest, str]:
        # IDs are catalogue keys, never filesystem paths supplied by the caller.
        if case_id not in CASE_IDS or not self.manifest(case_id):
            raise UnsupportedData("case_not_found", "This case is not available. Choose a case from the catalogue.")
        return self.manifest(case_id)

    @lru_cache(maxsize=3)
    def _read_array(self, case_id, representation, variable, time_index):
        manifest, _ = self.require(case_id)
        if variable == 'horizontal_kinetic_energy':
            if not {'eastward_velocity', 'northward_velocity'} <= set(manifest.case.variables):
                raise UnsupportedData('unsupported_variable', 'Horizontal kinetic energy requires both current components, which this case does not supply.')
            import numpy as np
            from science.products import PRODUCTS
            shape = manifest.representations['analytical']['shape']
            inputs = {name: np.asarray(self._read_array(case_id, 'analytical', name, time_index)).reshape(shape) for name in PRODUCTS.get(variable).metadata.inputs}
            result = PRODUCTS.evaluate(variable, inputs)
            if representation == 'display':
                display = manifest.representations['display']
                result = result[:, display['latitude_source_indices'], :][:, :, display['longitude_source_indices']].astype(np.float32)
            return array('d' if representation == 'analytical' else 'f', result.ravel())
        relative = f"{representation}/{variable}-{time_index}.bin.gz"
        record = next((f for f in manifest.files if f["path"] == relative), None)
        if not record:
            raise UnsupportedData("unsupported_subset", "This variable, timestamp or representation is unavailable.")
        packed = (self.root / case_id / relative).read_bytes()
        if hashlib.sha256(packed).hexdigest() != record["sha256"]:
            raise UnsupportedData("case_integrity_error", "Case data failed an integrity check.")
        values = array("d" if representation == "analytical" else "f")
        values.frombytes(gzip.decompress(packed))
        if sys.byteorder != "little":
            values.byteswap()
        if len(values) != math.prod(record["shape"]):
            raise UnsupportedData("case_integrity_error", "Case array dimensions are inconsistent.")
        return values

    def observation(self, case_id, profile_id):
        manifest, _ = self.require(case_id)
        if profile_id not in {p.id for p in manifest.profiles}:
            raise UnsupportedData("profile_not_found", "This instrument profile is not in the selected case.")
        relative = f"profiles/{profile_id}.json"
        body = (self.root / case_id / relative).read_bytes()
        record = next(f for f in manifest.files if f["path"] == relative)
        if hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise UnsupportedData("case_integrity_error", "Profile failed an integrity check.")
        return Observation.model_validate_json(body)

    def subset(self, case_id, variable, time_index, representation, operation, depth_index, bounds):
        manifest, digest = self.require(case_id)
        coordinates = manifest.coordinates if representation == "analytical" else manifest.display_coordinates
        if variable not in manifest.case.variables and variable != 'horizontal_kinetic_energy':
            raise UnsupportedData("unsupported_variable", "The selected variable is not supplied by this case.")
        if not 0 <= time_index < len(coordinates.times):
            raise UnsupportedData("unsupported_time", "Choose an available timestamp from this case.")
        if operation == "depth_slice":
            if depth_index is None or not 0 <= depth_index < len(coordinates.depth_m):
                raise UnsupportedData("unsupported_depth", "A depth slice requires an available depth index.")
            zi = [depth_index]
        else:
            if depth_index is not None:
                raise UnsupportedData("invalid_request", "Use depth_slice to request an individual depth.")
            zi = list(range(len(coordinates.depth_m)))
        lat, lon = coordinates.latitude, coordinates.longitude
        yi, xi = list(range(len(lat))), list(range(len(lon)))
        if any(v is not None for v in bounds):
            if not all(v is not None and math.isfinite(v) for v in bounds):
                raise UnsupportedData("invalid_bounds", "Supply all four finite west/south/east/north bounds.")
            west, south, east, north = bounds
            if not (lon[0] <= west <= east <= lon[-1] and lat[0] <= south <= north <= lat[-1]):
                raise UnsupportedData("outside_coverage", "Requested bounds must lie within this case; dateline-crossing requests are not supported here.")
            yi = [i for i, value in enumerate(lat) if south <= value <= north]
            xi = [i for i, value in enumerate(lon) if west <= value <= east]
            if not yi or not xi:
                raise UnsupportedData("empty_subset", "No grid coordinates fall inside these bounds.")
        count = len(zi) * len(yi) * len(xi)
        if count > MAX_VALUES:
            raise UnsupportedData("subset_too_large", f"Limit is {MAX_VALUES} scalar values per response. Use a depth slice, smaller bounds or the display representation.")
        array_values = self._read_array(case_id, representation, variable, time_index)
        values = []
        for z in zi:
            for y in yi:
                for x in xi:
                    v = array_values[(z * len(lat) + y) * len(lon) + x]
                    values.append(v if math.isfinite(v) else None)
        if variable == 'horizontal_kinetic_energy':
            from science.products import PRODUCTS
            product = PRODUCTS.get(variable).metadata
            return OperationResult(kind='derived',case_id=case_id,source_id=next(s.source_id for s in manifest.sources if s.kind=='model_analysis'),variable=variable,units=product.units,standard_name='',time=coordinates.times[time_index],representation=representation,operation=operation,shape=(len(zi),len(yi),len(xi)),depth_m=[coordinates.depth_m[i] for i in zi],latitude=[lat[i] for i in yi],longitude=[lon[i] for i in xi],values=values,processing=[product.method_id,product.definition,'Calculated on the native grid in float64; both input masks are retained. Display selects coordinates then rounds to float32.',*product.limitations],manifest_sha256=digest)
        spec = next(v for v in manifest.variables if v.id == variable)
        processing=[manifest.representations[representation]["method"],"Coordinate selection only; JSON null preserves missing values."]
        temporal=manifest.representations.get('temporal_support')
        if temporal and temporal['kind']=='calendar_month_mean':
            start,end=temporal['intervals'][time_index]
            processing += [spec.definition, f'Monthly mean over [{start}, {end}). The timestamp identifies the first day of this averaging interval, not an instantaneous field.',f'Source longitude convention: {coordinates.longitude_convention}; native coordinate order is retained.']
        return OperationResult(case_id=case_id,source_id=next(s.source_id for s in manifest.sources if s.kind=='model_analysis'),variable=variable,units=spec.units,standard_name=spec.standard_name,time=coordinates.times[time_index],representation=representation,operation=operation,shape=(len(zi),len(yi),len(xi)),depth_m=[coordinates.depth_m[i] for i in zi],latitude=[lat[i] for i in yi],longitude=[lon[i] for i in xi],values=values,processing=processing,manifest_sha256=digest)
