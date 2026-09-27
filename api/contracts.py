"""Application catalogue contracts. Data availability comes from a checked pack."""

from typing import Literal

from pydantic import BaseModel, Field
from science.contracts import CaseSummary
from api.version import APP_VERSION


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "Depth Atlas"
    version: str = APP_VERSION
    data_status: Literal["not_configured", "historical_case_ready"] = "not_configured"
    case_count: int = 0


class RegionPreview(BaseModel):
    id: str
    name: str
    description: str
    center: tuple[float, float]
    viewport_bounds: tuple[float, float, float, float]
    status: Literal["planned", "data_available"] = "planned"


class CatalogResponse(BaseModel):
    schema_version: Literal["2"] = "2"
    data_status: Literal["not_configured", "historical_case_ready"] = "not_configured"
    message: str = "No scientific datasets have been connected yet."
    regions: list[RegionPreview]
    cases: list[CaseSummary] = Field(default_factory=list)
    unavailable_tools: dict[str, list[str]] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
