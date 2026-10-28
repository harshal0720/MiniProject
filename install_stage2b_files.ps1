$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$backend = (Get-Location).Path
if (-not (Test-Path (Join-Path $backend 'alembic.ini'))) { throw 'Run from backend directory.' }
$files = @(
    @{ Path = 'tests/test_migration_roundtrip.py'; Content = @'
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_alembic(db_path: Path, revision: str) -> None:
    url = f"sqlite:///{db_path.as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["PYTHONPATH"] = str(BACKEND_DIR)
    script = (
        "import os; from alembic.config import Config; from alembic import command; "
        f"os.environ['DATABASE_URL']={url!r}; "
        f"cfg=Config({str(BACKEND_DIR / 'alembic.ini')!r}); "
        f"cfg.set_main_option('sqlalchemy.url', {url!r}); "
        + (f"command.downgrade(cfg, {revision!r})" if revision == '-1' else f"command.upgrade(cfg, {revision!r})")
    )
    subprocess.run([sys.executable, "-c", script], cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True)


def version_and_tables(db_path: Path):
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return version, tables


def test_empty_database_upgrade_downgrade_one_step_upgrade(tmp_path: Path):
    db_path = tmp_path / "empty_roundtrip.db"
    run_alembic(db_path, "head")
    version, tables = version_and_tables(db_path)
    assert version == "0003_monitoring"
    assert {"workload_status_history", "monitoring_alerts"} <= tables

    run_alembic(db_path, "-1")
    version, tables = version_and_tables(db_path)
    assert version == "0002_total_capacity"
    assert "workload_status_history" not in tables
    assert "monitoring_alerts" not in tables

    run_alembic(db_path, "head")
    version, tables = version_and_tables(db_path)
    assert version == "0003_monitoring"
    assert {"workload_status_history", "monitoring_alerts"} <= tables
'@ }
    @{ Path = 'tests/test_monitoring.py'; Content = @'
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

    result = schedule_workload(session, ScheduleRequest(workload_id=1))
    assert result.status == "no_capacity"
    assert session.get(Workload, 1).status == "pending"
    # This is a sequential unit/integration test; real parallel scheduling is NOT tested.
'@ }
    @{ Path = 'app/models/monitoring.py'; Content = @'
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.cloud_region import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkloadStatusHistory(Base):
    __tablename__ = "workload_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workload_id: Mapped[int] = mapped_column(ForeignKey("workloads.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonitoringAlert(Base):
    __tablename__ = "monitoring_alerts"
    __table_args__ = (Index("ix_monitoring_alerts_active_fingerprint", "fingerprint", "resolved"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("cloud_regions.id", ondelete="SET NULL"), nullable=True, index=True)
    workload_id: Mapped[int | None] = mapped_column(ForeignKey("workloads.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
'@ }
    @{ Path = 'app/models/__init__.py'; Content = @'
from app.models.cloud_region import Base, CloudRegion
from app.models.workload import Workload
from app.models.scheduled_allocation import ScheduledAllocation
from app.models.monitoring import MonitoringAlert, WorkloadStatusHistory

__all__ = [
    "Base", "CloudRegion", "Workload", "ScheduledAllocation",
    "MonitoringAlert", "WorkloadStatusHistory",
]
'@ }
    @{ Path = 'app/models/cloud_region.py'; Content = @'
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CloudRegion(Base):
    __tablename__ = "cloud_regions"
    __table_args__ = (
        CheckConstraint("carbon_intensity >= 0", name="ck_carbon_intensity_nonnegative"),
        CheckConstraint("renewable_energy_pct >= 0 AND renewable_energy_pct <= 100", name="ck_renewable_energy_pct_range"),
        CheckConstraint("estimated_cost_usd_per_kwh >= 0", name="ck_cost_nonnegative"),
        CheckConstraint("latency_ms >= 0", name="ck_latency_nonnegative"),
        CheckConstraint("available_cpu_cores >= 0", name="ck_region_cpu_nonnegative"),
        CheckConstraint("available_memory_gb > 0", name="ck_region_memory_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    carbon_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    carbon_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))
    renewable_energy_pct: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_cost_usd_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    available_cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False, default=64)
    available_memory_gb: Mapped[float] = mapped_column(Float, nullable=False, default=256.0)
    total_cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False, default=64)
    total_memory_gb: Mapped[float] = mapped_column(Float, nullable=False, default=256.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
'@ }
    @{ Path = 'app/services/monitoring.py'; Content = @'
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import monitoring_config as config
from app.models import CloudRegion, Workload
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
    history = WorkloadStatusHistory(
        workload_id=workload.id, from_status=from_status, to_status=to_status,
        changed_at=now_fn(), reason=reason,
    )
    workload.status = to_status
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
    session.add(MonitoringAlert(
        alert_type=alert_type, severity=severity, message=message,
        fingerprint=fingerprint, region_id=region_id, workload_id=workload_id,
        created_at=now, resolved=False,
    ))
    session.flush()
    return True


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
'@ }
    @{ Path = 'app/core/monitoring_config.py'; Content = @'
import os

CPU_WARNING_PCT = float(os.getenv("GREEN_SCALE_CPU_WARNING_PCT", "70"))
CPU_CRITICAL_PCT = float(os.getenv("GREEN_SCALE_CPU_CRITICAL_PCT", "90"))
MEMORY_WARNING_PCT = float(os.getenv("GREEN_SCALE_MEMORY_WARNING_PCT", "70"))
MEMORY_CRITICAL_PCT = float(os.getenv("GREEN_SCALE_MEMORY_CRITICAL_PCT", "90"))
LATENCY_WARNING_RATIO = float(os.getenv("GREEN_SCALE_LATENCY_WARNING_RATIO", "0.80"))
CARBON_STALE_AFTER_MINUTES = int(os.getenv("GREEN_SCALE_CARBON_STALE_MINUTES", "15"))
'@ }
    @{ Path = 'migrations/versions/0003_monitoring.py'; Content = @'
"""Add monitoring history/alerts and allow zero available CPU."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_monitoring"
down_revision = "0002_total_capacity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "workload_status_history" not in tables:
        op.create_table(
            "workload_status_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workload_id", sa.Integer(), sa.ForeignKey("workloads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=False),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
        )
        op.create_index("ix_workload_status_history_workload_id", "workload_status_history", ["workload_id"])
    if "monitoring_alerts" not in tables:
        op.create_table(
            "monitoring_alerts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("alert_type", sa.String(60), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("region_id", sa.Integer(), sa.ForeignKey("cloud_regions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("workload_id", sa.Integer(), sa.ForeignKey("workloads.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("fingerprint", sa.String(240), nullable=False),
        )
        for name, columns in (
            ("ix_monitoring_alerts_alert_type", ["alert_type"]),
            ("ix_monitoring_alerts_region_id", ["region_id"]),
            ("ix_monitoring_alerts_workload_id", ["workload_id"]),
            ("ix_monitoring_alerts_fingerprint", ["fingerprint"]),
            ("ix_monitoring_alerts_active_fingerprint", ["fingerprint", "resolved"]),
        ):
            op.create_index(name, "monitoring_alerts", columns)

    # Current scheduler may reserve all CPU cores. Model and schema must allow 0 free cores.
    checks = {item.get("name") for item in inspect(bind).get_check_constraints("cloud_regions")}
    if "ck_region_cpu_positive" in checks:
        with op.batch_alter_table("cloud_regions") as batch:
            batch.drop_constraint("ck_region_cpu_positive", type_="check")
            batch.create_check_constraint("ck_region_cpu_nonnegative", "available_cpu_cores >= 0")


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    checks = {item.get("name") for item in inspect(bind).get_check_constraints("cloud_regions")}
    if "ck_region_cpu_nonnegative" in checks:
        with op.batch_alter_table("cloud_regions") as batch:
            batch.drop_constraint("ck_region_cpu_nonnegative", type_="check")
            batch.create_check_constraint("ck_region_cpu_positive", "available_cpu_cores >= 1")
    if "monitoring_alerts" in tables:
        for name in (
            "ix_monitoring_alerts_active_fingerprint", "ix_monitoring_alerts_fingerprint",
            "ix_monitoring_alerts_workload_id", "ix_monitoring_alerts_region_id",
            "ix_monitoring_alerts_alert_type",
        ):
            op.drop_index(name, table_name="monitoring_alerts")
        op.drop_table("monitoring_alerts")
    if "workload_status_history" in tables:
        op.drop_index("ix_workload_status_history_workload_id", table_name="workload_status_history")
        op.drop_table("workload_status_history")
'@ }
)
foreach ($file in $files) {
  $target = Join-Path $backend $file.Path
  $parent = Split-Path -Parent $target
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  [System.IO.File]::WriteAllText($target, $file.Content + "`n", $utf8NoBom)
  Write-Host "Wrote $($file.Path)"
}
Write-Host 'Stage 2b files written UTF-8 without BOM. Implementation remains UNTESTED until local checks pass.'
