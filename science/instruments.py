"""Observation contract v2. Quality is decided per parameter, never per curve."""
from typing import Literal
from pydantic import Field
from science.contracts import Contract


class Reading(Contract):
    value: float | None
    qc: str
    accepted: bool
    reason: str
    raw: float | None = None
    raw_qc: str = ""
    adjusted: float | None = None
    adjusted_qc: str = ""
    adjusted_error: float | None = None


class Measurement(Contract):
    index: int
    depth_m: float | None
    pressure_dbar: float | None
    latitude: float
    longitude: float
    time: str
    coordinate_status: str
    coordinate_qc: dict[str,str] = Field(default_factory=dict)
    coordinate_eligible: bool = False
    readings: dict[str, Reading]


class Parameter(Contract):
    label: str
    units: str
    definition: str
    source_field: str
    mode: str
    qc_scheme: str
    accepted_count: int = 0


class InstrumentSummary(Contract):
    id: str
    instrument: Literal['argo', 'glider', 'ctd', 'bgc']
    platform: str
    title: str
    time: str
    time_end: str
    latitude: float
    longitude: float
    samples: int
    depth_range_m: tuple[float, float] | None
    parameters: dict[str, Parameter]
    collection: str = "Imported file"
    source_url: str
    source_file: str
    source_sha256: str
    track: list[tuple[float, float]] = Field(default_factory=list)


class InstrumentProfile(InstrumentSummary):
    schema_version: Literal['2'] = '2'
    kind: Literal['observation'] = 'observation'
    depth_method: str
    qc_policy: str
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    levels: list[Measurement]


class ImportResult(Contract):
    schema_version: Literal['2'] = '2'
    format: str
    profiles: list[InstrumentProfile]
    warnings: list[str] = Field(default_factory=list)
    persistence: Literal['request_only'] = 'request_only'
