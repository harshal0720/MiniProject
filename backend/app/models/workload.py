
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.cloud_region import Base


class Workload(Base):
    __tablename__ = "workloads"

    __table_args__ = (
        CheckConstraint(
            "required_cpu_cores >= 1",
            name="ck_workload_cpu_positive",
        ),
        CheckConstraint(
            "required_memory_gb > 0",
            name="ck_workload_memory_positive",
        ),
        CheckConstraint(
            "max_latency_ms > 0",
            name="ck_workload_latency_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    workload_type: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    required_cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False)
    required_memory_gb: Mapped[float] = mapped_column(Float, nullable=False)
    max_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    carbon_aware: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
