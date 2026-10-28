from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkloadStatus = Literal["pending", "scheduled", "running", "completed", "failed", "deferred"]
AlertSeverity = Literal["warning", "critical"]


class WorkloadTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_status: WorkloadStatus
    reason: str | None = Field(default=None, max_length=2000)


class StatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    from_status: str
    to_status: str
    changed_at: datetime
    reason: str | None


class WorkloadMonitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    workload_type: str
    priority: str
    required_cpu_cores: int
    required_memory_gb: float
    max_latency_ms: float
    carbon_aware: bool
    status: str
    created_at: datetime


class WorkloadDetailResponse(WorkloadMonitorResponse):
    history: list[StatusHistoryResponse]


class WorkloadPageResponse(BaseModel):
    items: list[WorkloadMonitorResponse]
    page: int
    page_size: int
    total: int
    pages: int


class RegionMonitorResponse(BaseModel):
    id: int
    provider: str
    region: str
    used_cpu_cores: float
    total_cpu_cores: int
    available_cpu_cores: int
    cpu_utilisation_pct: float
    used_memory_gb: float
    total_memory_gb: float
    available_memory_gb: float
    memory_utilisation_pct: float
    level: Literal["ok", "warning", "critical"]
    carbon_freshness: Literal["fresh", "stale", "missing"]
    carbon_updated_at: datetime | None


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    alert_type: str
    severity: str
    region_id: int | None
    workload_id: int | None
    created_at: datetime
    resolved: bool
    message: str
    fingerprint: str


class AlertPageResponse(BaseModel):
    items: list[AlertResponse]
    page: int
    page_size: int
    total: int
    pages: int


class HealthSummaryResponse(BaseModel):
    region_count: int
    open_alerts_by_severity: dict[str, int]
    workloads_by_status: dict[str, int]
    carbon_freshness: dict[str, int]


class EvaluateResponse(BaseModel):
    created_count: int
    skipped_count: int


class AlertResolveResponse(BaseModel):
    id: int
    resolved: bool
