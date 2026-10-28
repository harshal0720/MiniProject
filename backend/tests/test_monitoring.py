from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, CloudRegion, ScheduledAllocation, Workload
from app.models.monitoring import MonitoringAlert, WorkloadStatusHistory
from app.schemas.scheduling import ScheduleRequest
from app.services.monitoring import (
    InvalidStatusTransition, evaluate_monitoring, region_utilisation,
    transition_workload_status,
)
from app.services.scheduling import schedule_workload


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
        db.add(Workload(
            id=1, name="test-workload", workload_type="batch", priority="normal",
            required_cpu_cores=4, required_memory_gb=8.0, max_latency_ms=100.0,
            carbon_aware=True, status="pending", created_at=now,
        ))
        db.add(CloudRegion(
            provider="Test", region="test-region", carbon_intensity=100.0,
            renewable_energy_pct=50.0, estimated_cost_usd_per_kwh=0.1,
            latency_ms=50.0, available_cpu_cores=30, available_memory_gb=75.0,
            total_cpu_cores=100, total_memory_gb=100.0,
            carbon_updated_at=now, updated_at=now,
        ))
        db.commit()
        yield db
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_illegal_transition_raises_clear_exception(session):
    with pytest.raises(InvalidStatusTransition, match="Illegal workload status transition"):
        transition_workload_status(session, 1, "completed")
    assert session.get(Workload, 1).status == "pending"
    assert session.scalars(select(WorkloadStatusHistory)).all() == []


def test_transition_records_history_with_controlled_clock(session):
    fixed = datetime(2026, 10, 20, 12, 30, tzinfo=timezone.utc)
    history = transition_workload_status(session, 1, "scheduled", "accepted", now_fn=lambda: fixed)
    assert (history.from_status, history.to_status, history.changed_at) == ("pending", "scheduled", fixed)
    assert session.get(Workload, 1).status == "scheduled"


@pytest.mark.parametrize(("available_cpu", "expected"), [(30, "warning"), (10, "critical")])
def test_cpu_thresholds_exactly_at_warning_and_critical(session, monkeypatch, available_cpu, expected):
    import app.services.monitoring as monitoring
    monkeypatch.setattr(monitoring.config, "CPU_WARNING_PCT", 70.0)
    monkeypatch.setattr(monitoring.config, "CPU_CRITICAL_PCT", 90.0)
    region = session.scalar(select(CloudRegion).where(CloudRegion.region == "test-region"))
    region.available_cpu_cores = available_cpu
    session.commit()
    fixed = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    evaluate_monitoring(session, now_fn=lambda: fixed)
    alert = session.scalar(select(MonitoringAlert).where(MonitoringAlert.alert_type == "cpu_utilisation"))
    assert alert is not None and alert.severity == expected


def test_stale_carbon_alert_is_created_once(session, monkeypatch):
    import app.services.monitoring as monitoring
    monkeypatch.setattr(monitoring.config, "CARBON_STALE_AFTER_MINUTES", 15)
    fixed = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    region = session.scalar(select(CloudRegion).where(CloudRegion.region == "test-region"))
    region.carbon_updated_at = fixed - timedelta(minutes=16)
    session.commit()
    evaluate_monitoring(session, now_fn=lambda: fixed)
    evaluate_monitoring(session, now_fn=lambda: fixed)
    alerts = session.scalars(select(MonitoringAlert).where(MonitoringAlert.alert_type == "stale_carbon_data")).all()
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"


def test_region_utilisation(session):
    region = session.scalar(select(CloudRegion).where(CloudRegion.region == "test-region"))
    assert region_utilisation(region) == {"cpu_utilisation_pct": 70.0, "memory_utilisation_pct": 25.0}


def test_exact_zero_available_cpu_then_next_workload_gets_no_capacity(session):
    # Fill the only eligible region: zero free CPU, but persisted allocations prove
    # that total capacity could fit the workload if capacity were released.
    session.add(Workload(
        id=2, name="already-allocated", workload_type="batch", priority="normal",
        required_cpu_cores=8, required_memory_gb=16.0, max_latency_ms=100.0,
        carbon_aware=True, status="scheduled",
    ))
    session.flush()
    region = session.scalar(select(CloudRegion).where(CloudRegion.region == "test-region"))
    region.total_cpu_cores = 8
    region.total_memory_gb = 16.0
    region.available_cpu_cores = 0
    region.available_memory_gb = 1.0
    session.add(ScheduledAllocation(
        workload_id=2, region_id=region.id, allocated_cpu_cores=8, allocated_memory_gb=15.0
    ))
    session.commit()
    import app.services.scheduling as scheduling
    

    scheduling.is_carbon_data_fresh = lambda region: True
    result = schedule_workload(session, ScheduleRequest(workload_id=1))
    assert result.status == "no_capacity"
    assert session.get(Workload, 1).status == "pending"
    # This is a sequential unit/integration test; real parallel scheduling is NOT tested.


def _scheduled_allocation(session, workload_id=1):
    region = session.scalar(select(CloudRegion).where(CloudRegion.region == "test-region"))
    assert region is not None
    allocation = ScheduledAllocation(
        workload_id=workload_id, region_id=region.id,
        allocated_cpu_cores=4, allocated_memory_gb=8.0,
    )
    session.add(allocation)
    region.available_cpu_cores = 26
    region.available_memory_gb = 67.0
    session.commit()
    return region.id


@pytest.mark.parametrize("terminal_status", ["completed", "failed"])
def test_terminal_transition_releases_capacity_once(session, terminal_status):
    region_id = _scheduled_allocation(session)
    transition_workload_status(session, 1, "scheduled")
    session.commit()
    transition_workload_status(session, 1, "running")
    session.commit()
    transition_workload_status(session, 1, terminal_status)
    session.commit()
    region = session.get(CloudRegion, region_id)
    assert region.available_cpu_cores == 30
    assert region.available_memory_gb == 75.0
    allocation = session.scalar(select(ScheduledAllocation).where(ScheduledAllocation.workload_id == 1))
    assert allocation.released_at is not None


def test_terminal_transition_cannot_release_capacity_twice(session):
    region_id = _scheduled_allocation(session)
    transition_workload_status(session, 1, "scheduled")
    session.commit()
    transition_workload_status(session, 1, "running")
    session.commit()
    transition_workload_status(session, 1, "completed")
    session.commit()
    region = session.get(CloudRegion, region_id)
    assert region.available_cpu_cores == 30
    assert region.available_memory_gb == 75.0
    with pytest.raises(InvalidStatusTransition):
        transition_workload_status(session, 1, "completed")


def test_running_transition_does_not_release_capacity(session):
    region_id = _scheduled_allocation(session)
    transition_workload_status(session, 1, "scheduled")
    session.commit()
    transition_workload_status(session, 1, "running")
    session.commit()
    region = session.get(CloudRegion, region_id)
    allocation = session.scalar(select(ScheduledAllocation).where(ScheduledAllocation.workload_id == 1))
    assert region.available_cpu_cores == 26
    assert region.available_memory_gb == 67.0
    assert allocation.released_at is None


def test_active_alert_fingerprint_unique_but_resolved_can_repeat(session):
    now = datetime.now(timezone.utc)
    first = MonitoringAlert(alert_type="cpu_utilisation", severity="warning", region_id=None,
                            workload_id=None, created_at=now, resolved=False,
                            message="one", fingerprint="dedup:unique")
    session.add(first)
    session.commit()
    from sqlalchemy.exc import IntegrityError
    session.add(MonitoringAlert(alert_type="cpu_utilisation", severity="warning", region_id=None,
                                workload_id=None, created_at=now, resolved=False,
                                message="two", fingerprint="dedup:unique"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    first = session.scalar(select(MonitoringAlert).where(MonitoringAlert.fingerprint == "dedup:unique"))
    first.resolved = True
    session.commit()
    session.add(MonitoringAlert(alert_type="cpu_utilisation", severity="warning", region_id=None,
                                workload_id=None, created_at=now, resolved=False,
                                message="three", fingerprint="dedup:unique"))
    session.commit()
    assert len(session.scalars(select(MonitoringAlert).where(MonitoringAlert.fingerprint == "dedup:unique")).all()) == 2


def test_capacity_release_never_exceeds_region_totals(session):
    region_id = _scheduled_allocation(session)
    region = session.get(CloudRegion, region_id)
    region.available_cpu_cores = 99
    region.available_memory_gb = 99.0
    session.commit()
    transition_workload_status(session, 1, "scheduled")
    session.commit()
    transition_workload_status(session, 1, "running")
    session.commit()
    transition_workload_status(session, 1, "completed")
    session.commit()
    region = session.get(CloudRegion, region_id)
    assert region.available_cpu_cores == region.total_cpu_cores == 100
    assert region.available_memory_gb == region.total_memory_gb == 100.0


def test_status_and_history_rollback_together(session):
    history = transition_workload_status(session, 1, "deferred", "transaction test")
    assert session.get(Workload, 1).status == "deferred"
    assert session.scalar(select(WorkloadStatusHistory).where(WorkloadStatusHistory.id == history.id)) is not None
    session.rollback()
    assert session.get(Workload, 1).status == "pending"
    assert session.scalar(select(WorkloadStatusHistory).where(WorkloadStatusHistory.id == history.id)) is None
