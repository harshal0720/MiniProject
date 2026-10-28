from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CloudRegionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    region: str
    carbon_intensity: float = Field(ge=0)
    renewable_energy_pct: float = Field(ge=0, le=100)
    estimated_cost_usd_per_kwh: float = Field(ge=0)
    latency_ms: float = Field(ge=0)
    updated_at: datetime


class CarbonReadingResponse(BaseModel):
    region_id: int
    provider: str
    region: str
    carbon_intensity: float
    renewable_energy_pct: float
    updated_at: datetime