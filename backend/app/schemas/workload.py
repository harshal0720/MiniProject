
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


WorkloadType = Literal[
    "batch",
    "web_service",
    "ml_training",
    "data_processing",
]

WorkloadPriority = Literal["low", "normal", "high", "critical"]

WorkloadName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]


class WorkloadCreate(BaseModel):
    name: WorkloadName
    workload_type: WorkloadType
    priority: WorkloadPriority = "normal"
    required_cpu_cores: int = Field(ge=1, le=1024)
    required_memory_gb: float = Field(gt=0, le=4096, allow_inf_nan=False)
    max_latency_ms: float = Field(gt=0, le=60000, allow_inf_nan=False)
    carbon_aware: bool = True


class WorkloadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    workload_type: WorkloadType
    priority: WorkloadPriority
    required_cpu_cores: int
    required_memory_gb: float
    max_latency_ms: float
    carbon_aware: bool
    status: str
    created_at: datetime
