from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SchedulingStatus = Literal[
    "scheduled",
    "no_eligible_region",
    "no_capacity",
]


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workload_id: int = Field(gt=0)


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workload_id: int
    status: SchedulingStatus
    allocation_id: int | None = None
    provider: str | None = None
    region: str | None = None
    allocated_cpu_cores: int | None = None
    allocated_memory_gb: float | None = None
    scheduled_at: datetime | None = None
    message: str