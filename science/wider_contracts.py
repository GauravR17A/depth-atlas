"""Bounded, versioned requests for wider prepared native sources."""
from typing import Literal
from pydantic import ConfigDict, Field, model_validator
from science.contracts import Contract

WIDER_METHOD = 'p15-native-subset-v1'
MAX_NATIVE_VALUES = 120_000
MAX_PACK_BYTES = 4_000_000


class WiderQuery(Contract):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False,validate_default=True)
    dataset: Literal['godas-2022', 'gobai-v2.2'] = 'godas-2022'
    variable: Literal['potential_temperature', 'source_salinity', 'oxygen', 'oxygen_uncertainty'] = 'potential_temperature'
    time_index: int = Field(default=0, ge=0, le=1, strict=True)
    west: float = Field(default=-65, ge=-180, le=180)
    east: float = Field(default=-45, ge=-180, le=180)
    south: float = Field(default=25, ge=-90, le=90)
    north: float = Field(default=40, ge=-90, le=90)
    level_min: float = Field(default=5, ge=0, le=5000)
    level_max: float = Field(default=459, ge=0, le=5000)
    resolution: Literal['preview', 'display', 'native'] = 'display'

    @model_validator(mode='after')
    def bounds(self):
        width=(self.east-self.west)%360
        if not 0 < width <= 90: raise ValueError('Select a longitude span greater than zero and at most 90 degrees, crossing the date line when needed.')
        if not 0 < self.north-self.south <= 40: raise ValueError('Select a latitude span greater than zero and at most 40 degrees.')
        if self.level_max < self.level_min: raise ValueError('The vertical interval is reversed.')
        return self


class WiderProfileRequest(Contract):
    query: WiderQuery
    longitude: float = Field(ge=-540,le=540)
    latitude: float = Field(ge=-90,le=90)


class WiderPack(Contract):
    schema_version: Literal['p15-pack-1'] = 'p15-pack-1'
    method: Literal['p15-native-subset-v1'] = WIDER_METHOD
    payload_text: str = Field(max_length=MAX_PACK_BYTES)
    sha256: str = Field(pattern='^[a-f0-9]{64}$')
