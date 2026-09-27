"""Pinned historical event comparisons. No scenario or forecast controls."""
from typing import Literal
from pydantic import Field
from science.contracts import Contract

METHOD = 'p13-climate-v1'
EventId = Literal['son-2013', 'son-2015', 'son-2022']


class ClimateQuery(Contract):
    event_id: EventId = 'son-2015'
    reference_event_id: EventId = 'son-2013'
    period: Literal['SON', '09', '10', '11'] = 'SON'
    longitude_index: int = Field(default=70, ge=0, le=139, strict=True)
    depth_index: int = Field(default=10, ge=0, le=27, strict=True)


class ClimateRecipe(Contract):
    mode: Literal['climate'] = 'climate'
    case_id: Literal['pacific-godas-2013-son', 'pacific-godas-2015-son', 'pacific-godas-2022-son']
    query: ClimateQuery
