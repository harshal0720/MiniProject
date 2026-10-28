from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.cloud_region import Base


class ScheduledAllocation(Base):
    __tablename__ = "scheduled_allocations"
    __table_args__ = (
        UniqueConstraint("workload_id", name="uq_allocation_workload"),
        CheckConstraint("allocated_cpu_cores >= 1", name="ck_allocation_cpu_positive"),
        CheckConstraint(
            "allocated_memory_gb > 0",
            name="ck_allocation_memory_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id"),
        nullable=False,
        index=True,
    )
    region_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_regions.id"),
        nullable=False,
        index=True,
    )
    allocated_cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_memory_gb: Mapped[float] = mapped_column(Float, nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
