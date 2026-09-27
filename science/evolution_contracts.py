"""Bounded native-region correspondence, separate from water-parcel transport."""
from typing import Literal

from pydantic import Field, model_validator

from science.contracts import Contract, VariableId
from science.feature_contracts import FeatureQuery


METHOD = 'p14-native-overlap-v2'
SUPPORTED_CASES = ('bay-bengal-2024-01', 'arabian-sea-2024-01')
NATIVE_CADENCE_HOURS = 12.0


class EvolutionQuery(Contract):
    variable: VariableId = 'temperature'
    units: str = '°C'
    operator: Literal['at_least', 'at_most', 'between'] = 'at_least'
    threshold: float = 26
    upper_threshold: float | None = None
    depth_min_m: float = Field(default=0, ge=0, le=5000)
    depth_max_m: float = Field(default=300, ge=0, le=5000)
    start_index: int = Field(default=0, ge=0, le=6, strict=True)
    end_index: int = Field(default=6, ge=0, le=6, strict=True)
    frame_step: int = Field(default=1, ge=1, le=6, strict=True)
    minimum_overlap: float = Field(default=0.1, gt=0, le=1)
    sensitivity_delta: float = Field(default=0.25, ge=0, le=100)

    @model_validator(mode='after')
    def valid_interval(self):
        if self.start_index >= self.end_index:
            raise ValueError('Choose at least two source frames in increasing order.')
        if (self.end_index - self.start_index) % self.frame_step:
            raise ValueError('The frame step must reach the selected end frame exactly.')
        self.feature_query(self.start_index)
        # Validate shifted range bounds and overflow without silently narrowing
        # the user's threshold sensitivity experiment.
        for offset in (-self.sensitivity_delta, self.sensitivity_delta):
            self.feature_query(self.start_index, offset)
        return self

    def feature_query(self, time_index, offset=0.0):
        return FeatureQuery(
            variable=self.variable, units=self.units, time_index=time_index,
            operator=self.operator, threshold=self.threshold + offset,
            upper_threshold=None if self.upper_threshold is None else self.upper_threshold + offset,
            depth_min_m=self.depth_min_m, depth_max_m=self.depth_max_m,
            order='volume',
        )

    def indices(self):
        return list(range(self.start_index, self.end_index + 1, self.frame_step))


class EvolutionRecipe(Contract):
    mode: Literal['evolution'] = 'evolution'
    case_id: Literal['bay-bengal-2024-01', 'arabian-sea-2024-01']
    query: EvolutionQuery
    selected_node: str | None = Field(default=None, pattern=r'^t[0-6]:r[0-9]{1,7}$')

    @model_validator(mode='after')
    def selected_frame(self):
        if self.selected_node is not None:
            index = int(self.selected_node.split(':', 1)[0][1:])
            if index not in self.query.indices():
                raise ValueError('The selected region must belong to a selected source frame.')
        return self
