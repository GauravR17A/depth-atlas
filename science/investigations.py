"""Versioned replay recipes and portable numeric fingerprints.

Numbers are tagged IEEE-754 binary64 values so a JSON round trip through
JavaScript does not change 1.0 into a different fingerprint from 1.
"""
import hashlib
import json
import math
import struct
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator, model_serializer
from science.contracts import Contract
from science.evidence_contracts import MatchSettings
from science.feature_contracts import FeatureQuery, SectionQuery
from science.expedition_contracts import ExpeditionRecipe
from science.drift_contracts import DriftRecipe
from science.heat_contracts import HeatRecipe
from science.climate_contracts import ClimateRecipe
from science.evolution_contracts import EvolutionRecipe
from science.blackout_contracts import BlackoutRecipe
from science.imported import ImportedSource

METHOD = 'p08-replay-v1'
HASH_METHOD = 'tagged-json-f64-sha256-v1'
Hash = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Index = Annotated[int, Field(ge=0, le=10000, strict=True)]


def fingerprint(value):
    def tag(v):
        if v is None: return ['null']
        if isinstance(v, bool): return ['boolean', v]
        if isinstance(v, (int, float)):
            if not math.isfinite(v) or (isinstance(v, int) and abs(v) > 2**53-1):
                raise ValueError('Fingerprint requires finite, interoperable numbers.')
            return ['number', struct.pack('>d', 0.0 if v == 0 else float(v)).hex()]
        if isinstance(v, str): return ['string', v]
        if isinstance(v, (list, tuple)): return ['array', [tag(x) for x in v]]
        if isinstance(v, dict) and all(isinstance(k, str) for k in v):
            return ['object', [[k, tag(v[k])] for k in sorted(v)]]
        raise ValueError('Unsupported fingerprint value.')
    # ensure_ascii uses lowercase escape digits in both implementations.
    payload = json.dumps(tag(value), ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('ascii')).hexdigest()


class Paint(Contract):
    min: float
    max: float
    log: bool = False
    palette: Literal['thermal', 'teal', 'mono'] = 'thermal'
    opacity: float = Field(default=1, ge=0, le=1)

    @model_validator(mode='after')
    def domain(self):
        if self.min >= self.max or (self.log and self.min <= 0):
            raise ValueError('Invalid colour range.')
        return self


class OceanRecipe(Contract):
    mode: Literal['ocean'] = 'ocean'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    variable: Literal['temperature', 'salinity', 'currents', 'horizontal_kinetic_energy']
    time_index: int = Field(ge=0, le=6, strict=True)
    view: Literal['volume', 'slice', 'section', 'iso', 'currents']
    depth_index: Index
    section_index: Index
    point: tuple[Index, Index, Index]
    paint: Paint
    iso: float
    exaggeration: float = Field(ge=1, le=12000)
    window_depth: Literal[1000, 5000]
    cutaway: bool
    quality: Literal['auto', 'balanced', 'basic']
    show_instruments: bool

    @model_validator(mode='after')
    def compatible(self):
        if (self.variable == 'currents') != (self.view == 'currents'):
            raise ValueError('Current view and variable must agree.')
        if self.point[2] != self.depth_index:
            raise ValueError('Selected point and depth must agree.')
        return self


class ComparisonSelection(Contract):
    profile_id: str = Field(pattern=r'^[a-zA-Z0-9_.-]{1,100}$')
    settings: MatchSettings


class ComparisonRecipe(ComparisonSelection):
    mode: Literal['comparison'] = 'comparison'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    sample_index: Index = 0
    view: Literal['comparison', 'coverage'] = 'comparison'
    rank: Literal['nearest', 'residual'] = 'nearest'
    baseline: ComparisonSelection | None = None


class FeatureRecipe(Contract):
    mode: Literal['features'] = 'features'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    query: FeatureQuery
    selected_region: Annotated[str, Field(pattern=r'^r[0-9]{1,7}$')] | None = None
    section: SectionQuery | None = None
    section_pick: Index = 0
    show_observations: bool = True
    graphics: Literal['3d', 'basic'] = '3d'
    exaggeration: Literal[1, 100, 500, 1000, 2000] = 1000

    @model_validator(mode='after')
    def same_query(self):
        if self.section and self.section.query != self.query:
            raise ValueError('Section belongs to another query.')
        return self


class InstrumentRecipe(Contract):
    mode: Literal['instrument'] = 'instrument'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    profile_id: str = Field(pattern=r'^[a-zA-Z0-9_.-]{1,100}$')
    variable: str = Field(pattern=r'^[a-z_]{1,40}$')
    sample_index: Index = 0
    show_excluded: bool = False
    model_time_index: Index | None = None

    @model_serializer(mode='wrap')
    def keep_legacy_recipe(self, handler):
        data = handler(self)
        if self.model_time_index is None:
            data.pop('model_time_index', None)
        return data


Recipe = Annotated[Union[OceanRecipe, ComparisonRecipe, FeatureRecipe, InstrumentRecipe, ExpeditionRecipe, DriftRecipe, HeatRecipe, ClimateRecipe, EvolutionRecipe, BlackoutRecipe], Field(discriminator='mode')]


class CaptureRequest(Contract):
    title: str = Field(min_length=1, max_length=100)
    recipe: Recipe
    import_source: ImportedSource | None = None
    expected_model_sha256: Hash | None = None
    expected_profile_sha256: Hash | None = None
    expected_heat_manifest_sha256: Hash | None = None
    expected_climate_manifest_sha256: Hash | None = None
    expected_observation_library_sha256: Hash | None = None

    @model_validator(mode='after')
    def profile_identity(self):
        if self.expected_profile_sha256 and self.recipe.mode not in {'comparison','instrument'}:
            raise ValueError('A profile fingerprint requires a profile selection.')
        if self.expected_heat_manifest_sha256 and self.recipe.mode != 'heat':
            raise ValueError('An SST fingerprint requires a heat investigation.')
        if self.expected_climate_manifest_sha256 and self.recipe.mode != 'climate':
            raise ValueError('A climate fingerprint requires a climate investigation.')
        return self


class SourceIdentity(Contract):
    model_manifest_sha256: Hash
    observation_library_sha256: Hash
    heat_manifest_sha256: Hash | None = None
    climate_manifest_sha256: Hash | None = None
    import_context_sha256: Hash | None = None
    import_profiles_sha256: Hash | None = None
    methods: dict[Annotated[str, Field(max_length=40)], Annotated[str, Field(max_length=100)]] = Field(max_length=12)


class ReplayRequest(Contract):
    schema_version: Literal['1'] = '1'
    title: str = Field(min_length=1, max_length=100)
    recipe: Recipe
    import_source: ImportedSource | None = None
    sources: SourceIdentity
    expected_result_sha256: Hash
    expected_recipe_sha256: Hash


class ExportRequest(Contract):
    replay: ReplayRequest
    format: Literal['zip', 'html', 'csv'] = 'zip'
