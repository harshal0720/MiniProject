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
