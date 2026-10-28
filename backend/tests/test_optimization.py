from sqlalchemy import select
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base, CloudRegion
from app.models.workload import Workload


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=test_engine)

    with TestingSessionLocal() as session:
        session.add(
            Workload(
                name="Test workload",
                workload_type="batch",
                priority="normal",
                required_cpu_cores=4,
                required_memory_gb=8.0,
                max_latency_ms=200.0,
                carbon_aware=True,
                status="pending",
                created_at=datetime.now(timezone.utc),
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
                    available_cpu_cores=16,
                    available_memory_gb=32.0,
                ),
                CloudRegion(
                    provider="ProviderB",
                    region="fast-but-dirty",
                    carbon_intensity=500.0,
                    renewable_energy_pct=20.0,
                    estimated_cost_usd_per_kwh=0.08,
                    latency_ms=20.0,
                    available_cpu_cores=16,
                    available_memory_gb=32.0,
                ),
                CloudRegion(
                    provider="ProviderC",
                    region="too-small",
                    carbon_intensity=50.0,
                    renewable_energy_pct=99.0,
                    estimated_cost_usd_per_kwh=0.05,
                    latency_ms=10.0,
                    available_cpu_cores=2,
                    available_memory_gb=4.0,
                ),
            ]
        )
        session.commit()

    def override_get_db():
        with TestingSessionLocal() as session:
            yield session

    @asynccontextmanager
    async def disabled_lifespan(_app):
        yield

    original_overrides = app.dependency_overrides.copy()
    original_lifespan = app.router.lifespan_context

    app.dependency_overrides[get_db] = override_get_db
    app.router.lifespan_context = disabled_lifespan

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        app.router.lifespan_context = original_lifespan
        test_engine.dispose()


def test_optimization_returns_ranked_eligible_regions(client):
    response = client.post("/api/optimize", json={"workload_id": 1})

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "recommended"
    assert body["recommended_region"]["region"] == "green-region"
    assert len(body["ranked_regions"]) == 2
    assert (
        body["ranked_regions"][0]["score"]
        >= body["ranked_regions"][1]["score"]
    )
    assert body["rejected_regions"][0]["region"] == "too-small"


def test_optimization_rejects_missing_workload(client):
    response = client.post("/api/optimize", json={"workload_id": 999})

    assert response.status_code == 404


def test_optimization_rejects_invalid_weight(client):
    response = client.post(
        "/api/optimize",
        json={"workload_id": 1, "weights": {"carbon": 2.0}},
    )

    assert response.status_code == 422


def test_optimization_returns_no_eligible_region(client):
    session_generator = app.dependency_overrides[get_db]()
    session = next(session_generator)

    try:
        workload = session.get(Workload, 1)
        assert workload is not None

        workload.max_latency_ms = 1.0
        session.commit()
    finally:
        session_generator.close()

    response = client.post("/api/optimize", json={"workload_id": 1})

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "no_eligible_region"
    assert body["recommended_region"] is None
    assert body["ranked_regions"] == []
    
    
def test_equal_scores_have_deterministic_provider_region_order(client):
    from app.models import CloudRegion

    session_generator = app.dependency_overrides[get_db]()
    session = next(session_generator)

    try:
        regions = session.scalars(select(CloudRegion)).all()
        assert len(regions) == 3

        # Give all regions identical scoring metrics.
        for region in regions:
            region.carbon_intensity = 100.0
            region.renewable_energy_pct = 50.0
            region.estimated_cost_usd_per_kwh = 0.10
            region.latency_ms = 50.0
            region.available_cpu_cores = 16
            region.available_memory_gb = 32.0

        session.commit()
    finally:
        session_generator.close()

    first = client.post("/api/optimize", json={"workload_id": 1})
    second = client.post("/api/optimize", json={"workload_id": 1})

    assert first.status_code == 200
    assert second.status_code == 200

    def ranking(response):
        return [
            (item["provider"], item["region"])
            for item in response.json()["ranked_regions"]
        ]

    expected = [
        ("ProviderA", "green-region"),
        ("ProviderB", "fast-but-dirty"),
    ]

    # The "too-small" region is now eligible too.
    expected.append(("ProviderC", "too-small"))

    assert ranking(first) == expected
    assert ranking(second) == expected


