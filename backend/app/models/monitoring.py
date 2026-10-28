from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
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
    __table_args__ = (
        Index(
            "uq_monitoring_alerts_active_fingerprint",
            "fingerprint",
            unique=True,
            sqlite_where=text("resolved = 0"),
            postgresql_where=text("resolved = false"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("cloud_regions.id", ondelete="SET NULL"), nullable=True, index=True)
    workload_id: Mapped[int | None] = mapped_column(ForeignKey("workloads.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
