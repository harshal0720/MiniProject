
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

PositiveWeight = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class OptimizationWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carbon: PositiveWeight = 0.40
    renewable: PositiveWeight = 0.25
    cost: PositiveWeight = 0.20
    latency: PositiveWeight = 0.15


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload_id: int = Field(gt=0)
    weights: OptimizationWeights = Field(default_factory=OptimizationWeights)


class RegionRejection(BaseModel):
    provider: str
    region: str
    reasons: list[str]


class RegionRecommendation(BaseModel):
    rank: int
    provider: str
    region: str
    score: float
    carbon_intensity: float
    renewable_energy_pct: float
    estimated_cost_usd_per_kwh: float
    latency_ms: float
    available_cpu_cores: int
    available_memory_gb: float
    explanation: list[str]


class OptimizationResponse(BaseModel):
    workload_id: int
    status: str
    scoring_note: str
    recommended_region: RegionRecommendation | None
    ranked_regions: list[RegionRecommendation]
    rejected_regions: list[RegionRejection]
