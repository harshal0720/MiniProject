from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import monitoring_config as config
from app.core.database import get_db
from app.models import CloudRegion, MonitoringAlert, ScheduledAllocation, Workload
from app.models.monitoring import WorkloadStatusHistory
from app.schemas.monitoring import (
    AlertPageResponse, AlertResolveResponse, AlertResponse, EvaluateResponse,
    HealthSummaryResponse, RegionMonitorResponse, WorkloadDetailResponse,
    WorkloadPageResponse, WorkloadTransitionRequest,
)
from app.services import monitoring as monitoring_service
from app.services.monitoring import InvalidStatusTransition


class MonitoringRoute(APIRoute):
    """Keep validation errors from this router in the monitor API error shape."""
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Request validation failed", "code": "validation_error",
                             "errors": exc.errors()},
                )
        return handler


router = APIRouter(prefix="/api/monitor", tags=["Monitoring"], route_class=MonitoringRoute)
DatabaseSession = Annotated[Session, Depends(get_db)]
STATUSES = ("pending", "scheduled", "running", "completed", "failed", "deferred")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _error(status_code: int, detail: str, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code})


def _carbon_state(region: CloudRegion, now: datetime) -> str:
    if region.carbon_updated_at is None:
        return "missing"
    if now - _aware(region.carbon_updated_at) > timedelta(minutes=config.CARBON_STALE_AFTER_MINUTES):
        return "stale"
    return "fresh"


def _page(statement, session: Session, page: int, page_size: int):
    total = int(session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
    rows = session.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total, (ceil(total / page_size) if total else 0)


@router.get("/health", response_model=HealthSummaryResponse)
def monitor_health(session: DatabaseSession) -> HealthSummaryResponse:
    now = utc_now()
    regions = session.scalars(select(CloudRegion)).all()
    alerts = session.scalars(select(MonitoringAlert).where(MonitoringAlert.resolved.is_(False))).all()
    workloads = session.scalars(select(Workload)).all()
    severity_counts = {"warning": 0, "critical": 0}
    for alert in alerts:
        severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1
    workload_counts = {status: 0 for status in STATUSES}
    for workload in workloads:
        workload_counts[workload.status] = workload_counts.get(workload.status, 0) + 1
    freshness = {"fresh": 0, "stale": 0, "missing": 0, "total": len(regions)}
    for region in regions:
        freshness[_carbon_state(region, now)] += 1
    return HealthSummaryResponse(region_count=len(regions), open_alerts_by_severity=severity_counts,
                                 workloads_by_status=workload_counts, carbon_freshness=freshness)


@router.get("/regions", response_model=list[RegionMonitorResponse])
def monitor_regions(session: DatabaseSession) -> list[RegionMonitorResponse]:
    now = utc_now()
    output = []
    for region in session.scalars(select(CloudRegion).order_by(CloudRegion.id)).all():
        usage = monitoring_service.region_utilisation(region)
        cpu = usage["cpu_utilisation_pct"]
        memory = usage["memory_utilisation_pct"]
        if cpu >= config.CPU_CRITICAL_PCT or memory >= config.MEMORY_CRITICAL_PCT:
            level = "critical"
        elif cpu >= config.CPU_WARNING_PCT or memory >= config.MEMORY_WARNING_PCT:
            level = "warning"
        else:
            level = "ok"
        output.append(RegionMonitorResponse(
            id=region.id, provider=region.provider, region=region.region,
            used_cpu_cores=max(0, region.total_cpu_cores - region.available_cpu_cores),
            total_cpu_cores=region.total_cpu_cores, available_cpu_cores=region.available_cpu_cores,
            cpu_utilisation_pct=cpu,
            used_memory_gb=max(0.0, region.total_memory_gb - region.available_memory_gb),
            total_memory_gb=region.total_memory_gb, available_memory_gb=region.available_memory_gb,
            memory_utilisation_pct=memory, level=level,
            carbon_freshness=_carbon_state(region, now), carbon_updated_at=region.carbon_updated_at,
        ))
    return output


@router.get("/workloads", response_model=WorkloadPageResponse)
def monitor_workloads(
    session: DatabaseSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Literal["pending", "scheduled", "running", "completed", "failed", "deferred"] | None = None,
    region: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> WorkloadPageResponse | JSONResponse:
    if created_from and created_to and _aware(created_from) > _aware(created_to):
        return _error(422, "created_from must be less than or equal to created_to.", "invalid_time_range")
    statement = select(Workload)
    if region:
        statement = statement.join(ScheduledAllocation, ScheduledAllocation.workload_id == Workload.id).join(
            CloudRegion, CloudRegion.id == ScheduledAllocation.region_id
        ).where(or_(func.lower(CloudRegion.region) == region.lower(), func.lower(CloudRegion.provider) == region.lower()))
    if status:
        statement = statement.where(Workload.status == status)
    if created_from:
        statement = statement.where(Workload.created_at >= created_from)
    if created_to:
        statement = statement.where(Workload.created_at <= created_to)
    statement = statement.distinct().order_by(Workload.created_at.desc(), Workload.id.desc())
    items, total, pages = _page(statement, session, page, page_size)
    return WorkloadPageResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/workloads/{workload_id}", response_model=WorkloadDetailResponse)
def monitor_workload_detail(workload_id: int, session: DatabaseSession):
    workload = session.get(Workload, workload_id)
    if workload is None:
        return _error(404, f"Workload {workload_id} not found.", "workload_not_found")
    history = session.scalars(select(WorkloadStatusHistory).where(
        WorkloadStatusHistory.workload_id == workload_id
    ).order_by(WorkloadStatusHistory.changed_at, WorkloadStatusHistory.id)).all()
    body = {column.name: getattr(workload, column.name) for column in Workload.__table__.columns}
    body["history"] = history
    return WorkloadDetailResponse.model_validate(body)


@router.post("/workloads/{workload_id}/transition", response_model=dict)
def transition_workload(workload_id: int, payload: WorkloadTransitionRequest, session: DatabaseSession):
    if session.get(Workload, workload_id) is None:
        return _error(404, f"Workload {workload_id} not found.", "workload_not_found")
    try:
        history = monitoring_service.transition_workload_status(
            session, workload_id, payload.to_status, payload.reason, now_fn=utc_now
        )
        session.commit()
        return {"workload_id": workload_id, "status": history.to_status, "history_id": history.id,
                "changed_at": history.changed_at, "reason": history.reason}
    except InvalidStatusTransition as exc:
        session.rollback()
        message = str(exc)
        if message.startswith("Unknown workload status:"):
            return _error(422, message, "unknown_status")
        return _error(409, message, "illegal_transition")
    except ValueError as exc:
        session.rollback()
        return _error(404, str(exc), "workload_not_found")


@router.get("/alerts", response_model=AlertPageResponse)
def monitor_alerts(
    session: DatabaseSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: Literal["warning", "critical"] | None = None,
    resolved: bool | None = None,
    region_id: int | None = Query(None, ge=1),
    alert_type: str | None = Query(None, alias="type", min_length=1, max_length=60),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AlertPageResponse | JSONResponse:
    if created_from and created_to and _aware(created_from) > _aware(created_to):
        return _error(422, "created_from must be less than or equal to created_to.", "invalid_time_range")
    statement = select(MonitoringAlert)
    if severity:
        statement = statement.where(MonitoringAlert.severity == severity)
    if resolved is not None:
        statement = statement.where(MonitoringAlert.resolved.is_(resolved))
    if region_id is not None:
        statement = statement.where(MonitoringAlert.region_id == region_id)
    if alert_type:
        statement = statement.where(MonitoringAlert.alert_type == alert_type)
    if created_from:
        statement = statement.where(MonitoringAlert.created_at >= created_from)
    if created_to:
        statement = statement.where(MonitoringAlert.created_at <= created_to)
    statement = statement.order_by(MonitoringAlert.created_at.desc(), MonitoringAlert.id.desc())
    items, total, pages = _page(statement, session, page, page_size)
    return AlertPageResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


def _active_candidate_fingerprints(session: Session, now: datetime) -> set[str]:
    fingerprints: set[str] = set()
    regions = session.scalars(select(CloudRegion).order_by(CloudRegion.id)).all()
    for region in regions:
        usage = monitoring_service.region_utilisation(region)
        if usage["cpu_utilisation_pct"] >= config.CPU_WARNING_PCT:
            fingerprints.add(f"cpu_utilisation:region:{region.id}")
        if usage["memory_utilisation_pct"] >= config.MEMORY_WARNING_PCT:
            fingerprints.add(f"memory_utilisation:region:{region.id}")
        if _carbon_state(region, now) != "fresh":
            fingerprints.add(f"stale_carbon_data:region:{region.id}")
    workloads = session.scalars(select(Workload).where(Workload.status.in_(("pending", "scheduled", "running", "deferred")))).all()
    for workload in workloads:
        for region in regions:
            if region.latency_ms > workload.max_latency_ms * config.LATENCY_WARNING_RATIO:
                fingerprints.add(f"latency_sla_risk:workload:{workload.id}:region:{region.id}")
    return fingerprints


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(session: DatabaseSession) -> EvaluateResponse:
    now = utc_now()
    candidates = _active_candidate_fingerprints(session, now)
    existing = set(session.scalars(select(MonitoringAlert.fingerprint).where(
        MonitoringAlert.resolved.is_(False), MonitoringAlert.fingerprint.in_(candidates)
    )).all()) if candidates else set()
    try:
        created = monitoring_service.evaluate_monitoring(session, now_fn=lambda: now)
        session.commit()
    except Exception:
        session.rollback()
        raise
    created_count = len(created)
    skipped_count = len(existing.intersection(candidates))
    return EvaluateResponse(created_count=created_count, skipped_count=skipped_count)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResolveResponse)
def resolve_monitor_alert(alert_id: int, session: DatabaseSession) -> AlertResolveResponse | JSONResponse:
    try:
        alert = monitoring_service.resolve_alert(session, alert_id)
        session.commit()
        return AlertResolveResponse(id=alert.id, resolved=alert.resolved)
    except ValueError as exc:
        session.rollback()
        return _error(404, str(exc), "alert_not_found")
