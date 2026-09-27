"""Bounded historical sampling experiments. No operational routing claims."""
from typing import Literal
from pydantic import Field, model_validator
from science.contracts import Contract

METHOD = 'p10-sampling-v2'


class PlanQuery(Contract):
    variable: Literal['temperature', 'salinity'] = 'temperature'
    depth_index: int = Field(default=0, ge=0, le=32, strict=True)
    budget: int = Field(default=8, ge=3, le=16, strict=True)
    min_spacing_km: float = Field(default=30, ge=0, le=150)
    objective: Literal['gradient', 'coverage'] = 'gradient'
    seed: int = Field(default=26067, ge=0, le=2147483647, strict=True)


class SurveyQuery(Contract):
    variable: Literal['temperature', 'salinity'] = 'temperature'
    depth_index: int = Field(default=0, ge=0, le=32, strict=True)
    time_index: int = Field(default=0, ge=0, le=6, strict=True)
    start: tuple[float, float]
    end: tuple[float, float]
    stations: int = Field(default=25, ge=2, le=81, strict=True)


class ExpeditionRecipe(Contract):
    mode: Literal['expedition'] = 'expedition'
    case_id: str = Field(pattern=r'^[a-z0-9-]{1,64}$')
    query: PlanQuery
    survey: SurveyQuery | None = None
    experiment: bool = False

    @model_validator(mode='after')
    def compatible(self):
        if self.survey and (self.survey.variable != self.query.variable or self.survey.depth_index != self.query.depth_index):
            raise ValueError('The saved survey must use the plan variable and native depth.')
        return self
