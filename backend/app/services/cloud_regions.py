from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import Base, CloudRegion


# Illustrative demo values, not live provider measurements.
DEMO_REGIONS = [
    {
        "provider": "AWS",
        "region": "us-east-1",
        "carbon_intensity": 380.0,
        "renewable_energy_pct": 45.0,
        "estimated_cost_usd_per_kwh": 0.12,
        "latency_ms": 120.0,
        "available_cpu_cores": 128,
        "available_memory_gb": 512.0,
    },
    {
        "provider": "Azure",
        "region": "central-india",
        "carbon_intensity": 520.0,
        "renewable_energy_pct": 25.0,
        "estimated_cost_usd_per_kwh": 0.10,
        "latency_ms": 35.0,
        "available_cpu_cores": 96,
        "available_memory_gb": 384.0,
    },
    {
        "provider": "GCP",
        "region": "europe-west1",
        "carbon_intensity": 160.0,
        "renewable_energy_pct": 80.0,
        "estimated_cost_usd_per_kwh": 0.11,
        "latency_ms": 145.0,
        "available_cpu_cores": 160,
        "available_memory_gb": 768.0,
    },
    {
        "provider": "AWS",
        "region": "eu-north-1",
        "carbon_intensity": 90.0,
        "renewable_energy_pct": 95.0,
        "estimated_cost_usd_per_kwh": 0.13,
        "latency_ms": 160.0,
        "available_cpu_cores": 64,
        "available_memory_gb": 256.0,
    },
]


def initialize_database() -> None:
    """
    Seed demo regions only after Alembic has created the schema.

    Intentionally does not call Base.metadata.create_all().
    """
    now = datetime.now(timezone.utc)

    with Session(bind=engine) as session:
        existing_keys = set(session.execute(
            select(CloudRegion.provider, CloudRegion.region)
        ).all())
        regions = []
        for data in DEMO_REGIONS:
            key = (data["provider"], data["region"])
            if key in existing_keys:
                continue
            region_data = data.copy()
            region_data["total_cpu_cores"] = data["available_cpu_cores"]
            region_data["total_memory_gb"] = data["available_memory_gb"]
            region_data["carbon_updated_at"] = now
            region_data["updated_at"] = now
            regions.append(CloudRegion(**region_data))
        if regions:
            session.add_all(regions)
            session.commit()


def list_cloud_regions(session: Session) -> list[CloudRegion]:
    statement = select(CloudRegion).order_by(
        CloudRegion.provider,
        CloudRegion.region,
    )
    return list(session.scalars(statement).all())


def list_current_carbon_readings(
    session: Session,
) -> list[dict[str, object]]:
    statement = select(CloudRegion).order_by(
        CloudRegion.carbon_intensity
    )
    regions = session.scalars(statement).all()

    return [
        {
            "region_id": region.id,
            "provider": region.provider,
            "region": region.region,
            "carbon_intensity": region.carbon_intensity,
            "renewable_energy_pct": region.renewable_energy_pct,
            "updated_at": region.updated_at,
        }
        for region in regions
    ]
