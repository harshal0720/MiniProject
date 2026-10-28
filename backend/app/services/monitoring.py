from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import monitoring_config as config
from app.models import CloudRegion, ScheduledAllocation, Workload
from app.models.monitoring import MonitoringAlert, WorkloadStatusHistory

LIFECYCLE_STATES = frozenset({"pending", "scheduled", "running", "completed", "failed", "deferred"})

# Single source of truth for allowed transitions.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"scheduled", "failed", "deferred"}),
    "scheduled": frozenset({"running", "failed", "deferred"}),
    "running": frozenset({"completed", "failed", "deferred"}),
    "deferred": frozenset({"pending", "scheduled", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvalidStatusTransition(ValueError):
    pass


def transition_workload_status(
    session: Session, workload_id: int, to_status: str, reason: str | None = None,
    *, now_fn: Clock = utc_now,
) -> WorkloadStatusHistory:
    workload = session.get(Workload, workload_id)
    if workload is None:
        raise ValueError(f"Workload {workload_id} not found.")
    if to_status not in LIFECYCLE_STATES:
        raise InvalidStatusTransition(f"Unknown workload status: {to_status!r}.")
    from_status = workload.status
    if to_status not in LEGAL_TRANSITIONS.get(from_status, frozenset()):
        raise InvalidStatusTransition(
            f"Illegal workload status transition: {from_status!r} -> {to_status!r}."
        )
    changed_at = now_fn()
    # The workload row is the transaction's state change; history and capacity
    # release are committed by the caller in the same transaction.
    history = WorkloadStatusHistory(
        workload_id=workload.id, from_status=from_status, to_status=to_status,
        changed_at=changed_at, reason=reason,
    )
    workload.status = to_status

    if to_status in {"completed", "failed"}:
        allocation = session.scalar(
            select(ScheduledAllocation).where(
                ScheduledAllocation.workload_id == workload.id
            )
        )
        if allocation is not None and allocation.released_at is None:
            # Conditional UPDATE is the exactly-once guard under concurrent calls.
            claim = session.execute(
                update(ScheduledAllocation)
                .where(
                    ScheduledAllocation.id == allocation.id,
                    ScheduledAllocation.released_at.is_(None),
                )
                .values(released_at=changed_at)
                .execution_options(synchronize_session=False)
            )
            if claim.rowcount == 1:
                region = session.get(CloudRegion, allocation.region_id)
                if region is not None:
                    session.execute(
                        update(CloudRegion)
                        .where(CloudRegion.id == region.id)
                        .values(
                            available_cpu_cores=case(
                                (CloudRegion.available_cpu_cores + allocation.allocated_cpu_cores > CloudRegion.total_cpu_cores,
                                 CloudRegion.total_cpu_cores),
                                else_=CloudRegion.available_cpu_cores + allocation.allocated_cpu_cores,
                            ),
                            available_memory_gb=case(
                                (CloudRegion.available_memory_gb + allocation.allocated_memory_gb > CloudRegion.total_memory_gb,
                                 CloudRegion.total_memory_gb),
                                else_=CloudRegion.available_memory_gb + allocation.allocated_memory_gb,
                            ),
                        )
                    )
    session.add(history)
    session.flush()
    return history


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def region_utilisation(region: CloudRegion) -> dict[str, float]:
    cpu_total = float(region.total_cpu_cores)
    memory_total = float(region.total_memory_gb)
    cpu_used = max(0.0, cpu_total - float(region.available_cpu_cores))
    memory_used = max(0.0, memory_total - float(region.available_memory_gb))
    return {
        "cpu_utilisation_pct": 0.0 if cpu_total <= 0 else min(100.0, cpu_used / cpu_total * 100.0),
        "memory_utilisation_pct": 0.0 if memory_total <= 0 else min(100.0, memory_used / memory_total * 100.0),
    }


def _severity(value: float, warning: float, critical: float) -> str | None:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return None


def _create_alert_if_new(
    session: Session, *, alert_type: str, severity: str, message: str,
    fingerprint: str, region_id: int | None, workload_id: int | None, now: datetime,
) -> bool:
    existing = session.scalar(select(MonitoringAlert.id).where(
        MonitoringAlert.fingerprint == fingerprint,
        MonitoringAlert.resolved.is_(False),
    ).limit(1))
    if existing is not None:
        return False
    try:
        # A savepoint keeps the outer evaluate transaction usable if another
        # evaluator inserts this active fingerprint first.
        with session.begin_nested():
            session.add(MonitoringAlert(
                alert_type=alert_type, severity=severity, message=message,
                fingerprint=fingerprint, region_id=region_id, workload_id=workload_id,
                created_at=now, resolved=False,
            ))
            session.flush()
        return True
    except IntegrityError:
        return False


def evaluate_monitoring(session: Session, *, now_fn: Clock = utc_now) -> list[MonitoringAlert]:
    now = now_fn()
    before_ids = set(session.scalars(select(MonitoringAlert.id)).all())
    regions = session.scalars(select(CloudRegion).order_by(CloudRegion.id)).all()

    for region in regions:
        usage = region_utilisation(region)
        for resource, pct, warning, critical in (
            ("cpu", usage["cpu_utilisation_pct"], config.CPU_WARNING_PCT, config.CPU_CRITICAL_PCT),
            ("memory", usage["memory_utilisation_pct"], config.MEMORY_WARNING_PCT, config.MEMORY_CRITICAL_PCT),
        ):
            severity = _severity(pct, warning, critical)
            if severity:
                _create_alert_if_new(
                    session, alert_type=f"{resource}_utilisation", severity=severity,
                    message=f"{region.provider}/{region.region} {resource} utilisation is {pct:.1f}%.",
                    fingerprint=f"{resource}_utilisation:region:{region.id}",
                    region_id=region.id, workload_id=None, now=now,
                )

        carbon_time = region.carbon_updated_at
        stale = carbon_time is None or now - _aware(carbon_time) > timedelta(
            minutes=config.CARBON_STALE_AFTER_MINUTES
        )
        if stale:
            _create_alert_if_new(
                session, alert_type="stale_carbon_data", severity="warning",
                message=f"Carbon data for {region.provider}/{region.region} is missing or stale.",
                fingerprint=f"stale_carbon_data:region:{region.id}",
                region_id=region.id, workload_id=None, now=now,
            )

    workloads = session.scalars(select(Workload).where(
        Workload.status.in_(("pending", "scheduled", "running", "deferred"))
    )).all()
    for workload in workloads:
        for region in regions:
            if region.latency_ms > workload.max_latency_ms * config.LATENCY_WARNING_RATIO:
                _create_alert_if_new(
                    session, alert_type="latency_sla_risk",
                    severity="critical" if region.latency_ms > workload.max_latency_ms else "warning",
                    message=f"{region.provider}/{region.region} latency {region.latency_ms:.1f} ms risks workload {workload.id} SLA ({workload.max_latency_ms:.1f} ms maximum).",
                    fingerprint=f"latency_sla_risk:workload:{workload.id}:region:{region.id}",
                    region_id=region.id, workload_id=workload.id, now=now,
                )

    session.flush()
    all_ids = set(session.scalars(select(MonitoringAlert.id)).all())
    new_ids = all_ids - before_ids
    if not new_ids:
        return []
    return list(session.scalars(select(MonitoringAlert).where(
        MonitoringAlert.id.in_(new_ids)
    ).order_by(MonitoringAlert.id)).all())


def list_alerts(session: Session, *, include_resolved: bool = False, limit: int = 100) -> list[MonitoringAlert]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")
    statement = select(MonitoringAlert)
    if not include_resolved:
        statement = statement.where(MonitoringAlert.resolved.is_(False))
    return list(session.scalars(statement.order_by(
        MonitoringAlert.created_at.desc(), MonitoringAlert.id.desc()
    ).limit(limit)).all())


def resolve_alert(session: Session, alert_id: int) -> MonitoringAlert:
    alert = session.get(MonitoringAlert, alert_id)
    if alert is None:
        raise ValueError(f"Alert {alert_id} not found.")
    alert.resolved = True
    session.flush()
    return alert
