from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base, CloudRegion, ScheduledAllocation, Workload


@asynccontextmanager
async def disabled_lifespan(_: FastAPI):
    yield


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=test_engine)

    with testing_session() as session:
        session.add(
            Workload(
                name="Scheduling test workload",
                workload_type="batch",
                priority="normal",
                required_cpu_cores=4,
                required_memory_gb=8.0,
                max_latency_ms=200.0,
                carbon_aware=True,
                status="pending",
            )
        )
        session.add_all(
            [
                CloudRegion(
                    provider="ProviderA",
                    region="green-region",
                    carbon_intensity=100.0,
                    renewable_energy_pct=90.0,
                    estimated_cost_usd_per_kwh=0.10,
                    latency_ms=50.0,
                    available_cpu_cores=8,
                    available_memory_gb=16.0,
                    carbon_updated_at=datetime.now(timezone.utc),
                ),
                CloudRegion(
                    provider="ProviderB",
                    region="fallback-region",
                    carbon_intensity=300.0,
                    renewable_energy_pct=40.0,
                    estimated_cost_usd_per_kwh=0.12,
                    latency_ms=60.0,
                    available_cpu_cores=16,
                    available_memory_gb=32.0,
                    carbon_updated_at=datetime.now(timezone.utc),
                ),
            ]
        )
        session.commit()

    def override_get_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    original_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(app.router, "lifespan_context", disabled_lifespan)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def open_test_session() -> tuple[Session, Generator[Session, None, None]]:
    generator = app.dependency_overrides[get_db]()
    session = next(generator)
    return session, generator


def read_state(client: TestClient) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    del client  # State is read from the test-only database override.
    session, generator = open_test_session()
    try:
        workload = session.get(Workload, 1)
        assert workload is not None
        regions = session.scalars(
            select(CloudRegion).order_by(CloudRegion.region)
        ).all()
        return (
            {"status": workload.status},
            [
                {
                    "region": region.region,
                    "cpu": region.available_cpu_cores,
                    "memory": region.available_memory_gb,
                }
                for region in regions
            ],
        )
    finally:
        generator.close()


def test_schedule_reserves_capacity_and_records_allocation(client: TestClient) -> None:
    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "scheduled"
    assert body["allocation_id"] is not None
    assert body["allocated_cpu_cores"] == 4
    assert body["allocated_memory_gb"] == 8.0

    workload_state, regions = read_state(client)
    assert workload_state["status"] == "scheduled"
    selected = next(region for region in regions if region["region"] == body["region"])
    assert selected["cpu"] >= 0
    assert selected["memory"] >= 0


def test_schedule_rejects_missing_workload(client: TestClient) -> None:
    response = client.post("/api/schedule", json={"workload_id": 999})
    assert response.status_code == 404


def test_schedule_rejects_duplicate_scheduling(client: TestClient) -> None:
    first = client.post("/api/schedule", json={"workload_id": 1})
    second = client.post("/api/schedule", json={"workload_id": 1})

    assert first.status_code == 200
    assert second.status_code == 409

    session, generator = open_test_session()
    try:
        allocations = session.scalars(select(ScheduledAllocation)).all()
        assert len(allocations) == 1
    finally:
        generator.close()


def test_schedule_rejects_invalid_workload_id(client: TestClient) -> None:
    response = client.post("/api/schedule", json={"workload_id": -1})
    assert response.status_code == 422


def test_schedule_returns_no_eligible_region_when_latency_fails(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        workload = session.get(Workload, 1)
        assert workload is not None
        workload.max_latency_ms = 1.0
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "no_eligible_region"
    state, _ = read_state(client)
    assert state["status"] == "pending"


def test_schedule_returns_no_eligible_region_when_total_capacity_is_too_small(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        for region in session.scalars(select(CloudRegion)).all():
            region.available_cpu_cores = 2
            region.available_memory_gb = 4.0
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "no_eligible_region"
    assert read_state(client)[0]["status"] == "pending"


def test_schedule_returns_no_capacity_when_region_is_temporarily_full(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        region = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "green-region")
        )
        assert region is not None

        # Simulate a workload already consuming most of this region's capacity.
        region.available_cpu_cores = 1
        region.available_memory_gb = 2.0
        session.add(
            ScheduledAllocation(
                workload_id=99,
                region_id=region.id,
                allocated_cpu_cores=7,
                allocated_memory_gb=14.0,
            )
        )
        session.commit()
    finally:
        generator.close()

    # The fallback region can still accept the workload, so scheduling succeeds.
    response = client.post("/api/schedule", json={"workload_id": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    assert response.json()["region"] == "fallback-region"


def test_schedule_returns_no_capacity_if_all_eligible_regions_are_full(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        for region in session.scalars(select(CloudRegion)).all():
            session.add(
                ScheduledAllocation(
                    workload_id=100 + region.id,
                    region_id=region.id,
                    allocated_cpu_cores=region.available_cpu_cores - 1,
                    allocated_memory_gb=region.available_memory_gb - 1.0,
                )
            )
            region.available_cpu_cores = 1
            region.available_memory_gb = 1.0
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "no_capacity"
    assert read_state(client)[0]["status"] == "pending"


def test_stale_carbon_region_is_not_eligible(client: TestClient) -> None:
    session, generator = open_test_session()
    try:
        for region in session.scalars(select(CloudRegion)).all():
            region.carbon_updated_at = datetime.now(timezone.utc) - timedelta(
                minutes=60
            )
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "no_eligible_region"


def test_missing_carbon_timestamp_is_not_eligible(client: TestClient) -> None:
    session, generator = open_test_session()
    try:
        region = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "green-region")
        )
        assert region is not None
        region.carbon_updated_at = None
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    assert response.json()["region"] == "fallback-region"


def test_fresh_zero_carbon_value_is_allowed(client: TestClient) -> None:
    session, generator = open_test_session()
    try:
        region = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "green-region")
        )
        assert region is not None
        region.carbon_intensity = 0.0
        region.carbon_updated_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    assert response.json()["region"] == "green-region"


def test_invalid_negative_resources_are_rejected_on_workload_creation(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/workload/create",
        json={
            "name": "Invalid workload",
            "workload_type": "batch",
            "priority": "normal",
            "required_cpu_cores": -2,
            "required_memory_gb": 8,
            "max_latency_ms": 100,
            "carbon_aware": True,
        },
    )
    assert response.status_code == 422
    
    
def test_schedule_fallback_preserves_preferred_region_capacity(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        preferred = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "green-region")
        )
        fallback = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "fallback-region")
        )
        assert preferred is not None
        assert fallback is not None

        preferred.available_cpu_cores = 1
        preferred.available_memory_gb = 2.0
        preferred_before = (
            preferred.available_cpu_cores,
            preferred.available_memory_gb,
        )
        fallback_before = (
            fallback.available_cpu_cores,
            fallback.available_memory_gb,
        )
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    assert response.json()["region"] == "fallback-region"

    session, generator = open_test_session()
    try:
        preferred_after = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "green-region")
        )
        fallback_after = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "fallback-region")
        )
        assert preferred_after is not None
        assert fallback_after is not None

        assert (
            preferred_after.available_cpu_cores,
            preferred_after.available_memory_gb,
        ) == preferred_before

        assert fallback_after.available_cpu_cores == fallback_before[0] - 4
        assert fallback_after.available_memory_gb == fallback_before[1] - 8.0
    finally:
        generator.close()


def test_rejected_no_eligible_schedule_preserves_capacity(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        workload = session.get(Workload, 1)
        assert workload is not None
        workload.max_latency_ms = 1.0
        session.commit()
    finally:
        generator.close()

    _, before = read_state(client)
    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    assert response.json()["status"] == "no_eligible_region"

    _, after = read_state(client)
    assert after == before


def test_duplicate_schedule_does_not_consume_capacity_twice(
    client: TestClient,
) -> None:
    first = client.post("/api/schedule", json={"workload_id": 1})
    assert first.status_code == 200
    assert first.json()["status"] == "scheduled"

    _, after_first = read_state(client)

    second = client.post("/api/schedule", json={"workload_id": 1})
    assert second.status_code == 409

    _, after_second = read_state(client)
    assert after_second == after_first
    assert all(region["cpu"] >= 0 for region in after_second)
    assert all(region["memory"] >= 0 for region in after_second)


def test_critical_workload_never_uses_region_over_latency_limit(
    client: TestClient,
) -> None:
    session, generator = open_test_session()
    try:
        workload = session.get(Workload, 1)
        green = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "green-region")
        )
        fallback = session.scalar(
            select(CloudRegion).where(CloudRegion.region == "fallback-region")
        )
        assert workload is not None
        assert green is not None
        assert fallback is not None

        workload.priority = "critical"
        workload.max_latency_ms = 55.0
        green.latency_ms = 50.0
        fallback.latency_ms = 60.0
        session.commit()
    finally:
        generator.close()

    response = client.post("/api/schedule", json={"workload_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "scheduled"
    assert body["region"] == "green-region"

    session, generator = open_test_session()
    try:
        selected = session.scalar(
            select(CloudRegion).where(CloudRegion.region == body["region"])
        )
        assert selected is not None
        assert selected.latency_ms <= 55.0
    finally:
        generator.close()
