"""Bounded historical surface-event and native-column diagnostic requests."""
from typing import Literal
from pydantic import Field
from science.contracts import Contract

METHOD = 'p12-heat-v1'


class HeatQuery(Contract):
    location_id: str = Field(pattern=r'^[a-z0-9-]{1,80}$')
    year: Literal[2023, 2024] = 2024
    event_id: str | None = Field(default=None, pattern=r'^mhw-\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}$')
    model_time_index: int = Field(default=0, ge=0, le=6, strict=True)
    depth_limit_m: Literal[100, 300, 700, 1000] = 300


class HeatRecipe(Contract):
    mode: Literal['heat'] = 'heat'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    query: HeatQuery
