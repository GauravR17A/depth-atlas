"""Bounded, explicit native-grid search and section requests."""
from typing import Literal
from pydantic import Field, model_validator
from science.contracts import Contract, VariableId

METHOD = 'p07-native-regions-v1'


class FeatureQuery(Contract):
    variable: VariableId = 'temperature'
    units: str = '°C'
    time_index: int = Field(default=1, ge=0, le=6)
    operator: Literal['at_least', 'at_most', 'between'] = 'at_least'
    threshold: float = 26
    upper_threshold: float | None = None
    depth_min_m: float = Field(default=0, ge=0, le=5000)
    depth_max_m: float = Field(default=300, ge=0, le=5000)
    order: Literal['volume', 'observations'] = 'volume'

    @model_validator(mode='after')
    def ordered(self):
        if self.depth_min_m >= self.depth_max_m:
            raise ValueError('Minimum depth must be less than maximum depth.')
        if self.operator == 'between':
            if self.upper_threshold is None or self.upper_threshold < self.threshold:
                raise ValueError('A range needs an upper threshold at least as large as its lower threshold.')
        elif self.upper_threshold is not None:
            raise ValueError('Upper threshold is only supported for a range.')
        return self


class SectionQuery(Contract):
    query: FeatureQuery
    start: tuple[float, float]  # longitude, latitude
    end: tuple[float, float]
    stations: int = Field(default=81, ge=2, le=201)


class RegionQuery(Contract):
    query: FeatureQuery
    region_id: str = Field(pattern=r'^r[0-9]{1,7}$')
