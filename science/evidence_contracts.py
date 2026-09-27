"""P05 comparison contracts. Counts and coverage derive from the same sample gates."""
from typing import Literal
from pydantic import Field
from science.contracts import Contract
from science.instruments import InstrumentSummary

METHOD_VERSION = 'p05-native-column-v1'


class MatchSettings(Contract):
    variable: Literal['temperature', 'salinity'] = 'temperature'
    time_index: int = Field(default=1, ge=0, le=6)
    time_window_hours: float = Field(default=6, ge=0, le=72)
    distance_km: float = Field(default=5, ge=0, le=50)
    max_vertical_gap_m: float = Field(default=500, ge=1, le=1000)
    qc: Literal['good', 'good_probably_good'] = 'good_probably_good'


class MatchRow(Contract):
    sample_index: int
    observation_time: str
    latitude: float
    longitude: float
    depth_m: float | None
    observed: float | None
    model: float | None = None
    residual: float | None = None
    accepted: bool = False
    reason: str
    qc: str
    mode: str
    model_latitude: float | None = None
    model_longitude: float | None = None
    distance_km: float | None = None
    time_offset_hours: float
    lower_depth_m: float | None = None
    upper_depth_m: float | None = None
    upper_weight: float | None = None
    model_lower_value: float | None = None
    model_upper_value: float | None = None


class SampleMetrics(Contract):
    count: int
    bias: float | None
    rmse: float | None
    mae: float | None
    maximum_abs_residual: float | None


class Comparison(Contract):
    schema_version: Literal['1'] = '1'
    kind: Literal['model_observation_comparison'] = 'model_observation_comparison'
    method_version: str = METHOD_VERSION
    case_id: str
    manifest_sha256: str
    observation_library_sha256: str
    model_time: str
    profile: InstrumentSummary
    settings: MatchSettings
    units: str
    total_samples: int
    matched_count: int
    excluded_count: int
    exclusion_counts: dict[str, int]
    metrics: SampleMetrics
    rows: list[MatchRow]
    methods: list[str]
    caveats: list[str]


class CoverageProfile(Contract):
    profile: InstrumentSummary
    total_samples: int
    matched_count: int
    excluded_count: int
    exclusion_counts: dict[str, int]
    eligible_depths_m: list[float]
    time_offset_hours_min: float
    time_offset_hours_max: float
    minimum_abs_time_offset_hours: float | None
    distance_km_min: float | None
    distance_km_max: float | None
    metrics: SampleMetrics
    suggested_time_index: int | None
    suggested_matched_count: int
    suggested_time_offset_hours: float | None
    suggested_distance_km: float | None


class Coverage(Contract):
    schema_version: Literal['1'] = '1'
    kind: Literal['observation_coverage'] = 'observation_coverage'
    method_version: str = METHOD_VERSION
    case_id: str
    manifest_sha256: str
    observation_library_sha256: str
    model_time: str
    settings: MatchSettings
    total_profiles: int
    matched_profiles: int
    total_samples: int
    matched_samples: int
    excluded_samples: int
    exclusion_counts: dict[str, int]
    profiles: list[CoverageProfile]
    methods: list[str]
    caveats: list[str]
