"""P14 observation exclusions, separate from source quality and matching gates."""
from typing import Annotated, Literal

from pydantic import Field, field_validator

from science.contracts import Contract
from science.evidence_contracts import Coverage, MatchSettings, SampleMetrics

METHOD = 'p14-blackout-v1'
Selection = Annotated[str, Field(min_length=1, max_length=256)]
Instrument = Literal['argo', 'glider', 'ctd', 'bgc']


class BlackoutQuery(Contract):
    settings: MatchSettings = Field(default_factory=MatchSettings)
    excluded_profile_ids: list[Selection] = Field(default_factory=list, max_length=128)
    excluded_instruments: list[Instrument] = Field(default_factory=list, max_length=4)
    excluded_platforms: list[Selection] = Field(default_factory=list, max_length=128)
    excluded_collections: list[Selection] = Field(default_factory=list, max_length=64)

    @field_validator('excluded_profile_ids', 'excluded_instruments', 'excluded_platforms', 'excluded_collections')
    @classmethod
    def normalize_selections(cls, value):
        return sorted(set(value))


class BlackoutRecipe(Contract):
    mode: Literal['blackout'] = 'blackout'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    query: BlackoutQuery


class ProfileEffect(Contract):
    profile_id: str
    excluded_by_user: bool
    selected_by: list[str]
    baseline_matched_samples: int
    remaining_matched_samples: int
    removed_eligible_samples: int
    removed_sample_indices: list[int]
    original_metrics: SampleMetrics


class EvidenceStatement(Contract):
    id: str
    baseline: str
    modified: str
    changed: bool


class BlackoutResult(Contract):
    schema_version: Literal['1'] = '1'
    kind: Literal['observation_blackout'] = 'observation_blackout'
    method_version: str = METHOD
    case_id: str
    query: BlackoutQuery
    manifest_sha256: str
    observation_library_sha256: str
    units: str
    baseline: Coverage
    modified: Coverage
    baseline_metrics: SampleMetrics
    modified_metrics: SampleMetrics
    profile_effects: list[ProfileEffect]
    excluded_profile_ids: list[str]
    removed_profiles: int
    removed_eligible_profiles: int
    removed_samples: int
    removed_eligible_samples: int
    statements: list[EvidenceStatement]
    model_unchanged: Literal[True] = True
    source_qc_unchanged: Literal[True] = True
    methods: list[str]
    caveats: list[str]
