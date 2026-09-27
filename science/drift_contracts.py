"""Bounded fixed-depth historical passive-tracer requests."""
from typing import Annotated, Literal, Union
from pydantic import Field, model_validator
from science.contracts import Contract

METHOD = 'p11-drift-v2'

class PointRelease(Contract):
    kind: Literal['point'] = 'point'
    longitude: float
    latitude: float

class BoxRelease(Contract):
    kind: Literal['box'] = 'box'
    bounds: tuple[float, float, float, float]

Release = Annotated[Union[PointRelease, BoxRelease], Field(discriminator='kind')]

class DriftQuery(Contract):
    release: Release
    depth_index: int = Field(default=0, ge=0, le=32, strict=True)
    start_time_index: int = Field(default=0, ge=0, le=6, strict=True)
    duration_hours: int = Field(default=24, ge=1, le=72, strict=True)
    particle_count: int = Field(default=24, ge=1, le=64, strict=True)
    seed: int = Field(default=26067, ge=0, le=2147483647, strict=True)
    dt_seconds: Literal[300, 600, 1200] = 600
    target_bounds: tuple[float, float, float, float] | None = None

class DriftRecipe(Contract):
    mode: Literal['drift'] = 'drift'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    query: DriftQuery
    comparison: DriftQuery | None = None

    @model_validator(mode='after')
    def different(self):
        if self.comparison == self.query:
            raise ValueError('Choose different settings for the comparison run.')
        return self
