"""Versioned science contracts, shared by preparation and the read-only API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VariableId = Literal["temperature", "salinity", "eastward_velocity", "northward_velocity", "horizontal_kinetic_energy"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Variable(Contract):
    id: VariableId
    source_name: str
    label: str
    standard_name: str
    units: str
    definition: str
    source_units: str
    packing: dict


class Provenance(Contract):
    source_id: str
    title: str
    kind: Literal["model_analysis", "observation", "derived", "simulation"]
    provider: str
    dataset_version: str
    source_url: str
    licence_url: str
    licence: str
    citation: str
    retrieved_at: str
    files: list[dict]
    transformations: list[str]
    limitations: list[str]


class Coordinates(Contract):
    times: list[str]
    depth_m: list[float]
    latitude: list[float]
    longitude: list[float]
    depth_positive: Literal["down"] = "down"
    longitude_convention: Literal["[-180,180)", "[0,360)"] = "[-180,180)"
    calendar: str
    source_time_units: str
    source_depth_units: str
    source_longitude_convention: str


class ProfileSummary(Contract):
    id: str
    platform: str
    cycle: int
    time: str
    latitude: float
    longitude: float
    data_mode: Literal["R", "A", "D"]
    position_qc: str
    time_qc: str
    samples: int
    eligible_samples: int
    depth_range_m: tuple[float, float] | None
    source_id: str
    source_file: str
    source_sha256: str
    source_url: str
    overlap: dict = Field(default_factory=dict)


class Observation(ProfileSummary):
    schema_version: Literal["1"] = "1"
    kind: Literal["observation"] = "observation"
    selected_fields: dict[str, str]
    units: dict[str, str]
    definitions: dict[str, str]
    qc_policy: str
    depth_method: str
    levels: list[dict]
    source_metadata: dict


class CaseSummary(Contract):
    id: str
    title: str
    region_id: str
    kind: Literal["model_analysis"] = "model_analysis"
    bounds: tuple[float, float, float, float]
    time_start: str
    time_end: str
    time_count: int
    depth_range_m: tuple[float, float]
    depth_count: int
    profile_count: int
    variables: list[VariableId]
    source_label: str
    representation: Literal["source_grid_subset"] = "source_grid_subset"


class CaseManifest(Contract):
    schema_version: Literal["1"] = "1"
    case: CaseSummary
    coordinates: Coordinates
    display_coordinates: Coordinates
    variables: list[Variable]
    sources: list[Provenance]
    profiles: list[ProfileSummary]
    representations: dict
    samples: list[dict]
    limitations: list[str]
    files: list[dict]
    processing_version: str


class OperationResult(Contract):
    schema_version: Literal["1"] = "1"
    kind: Literal["model_analysis", "derived"] = "model_analysis"
    case_id: str
    source_id: str
    variable: VariableId
    units: str
    standard_name: str
    time: str
    representation: Literal["analytical", "display"]
    operation: Literal["depth_slice", "volume"]
    dimensions: tuple[str, str, str] = ("depth", "latitude", "longitude")
    shape: tuple[int, int, int]
    depth_m: list[float]
    latitude: list[float]
    longitude: list[float]
    values: list[float | None]
    missing_value: None = None
    processing: list[str]
    manifest_sha256: str


class UnsupportedData(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)
