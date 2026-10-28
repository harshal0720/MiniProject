from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base, CloudRegion


@asynccontextmanager
async def disabled_lifespan(_: FastAPI) -> AsyncIterator[None]:
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

    def override_get_db() -> Generator[Session, None, None]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        app.router,
        "lifespan_context",
        disabled_lifespan,
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture
def seeded_client(client: TestClient) -> TestClient:
    dependency = app.dependency_overrides[get_db]()
    session = next(dependency)

    try:
        session.add_all(
            [
                CloudRegion(
                    provider="AWS",
                    region="eu-north-1",
                    carbon_intensity=90.0,
                    renewable_energy_pct=95.0,
                    estimated_cost_usd_per_kwh=0.13,
                    latency_ms=160.0,
                ),
                CloudRegion(
                    provider="GCP",
                    region="europe-west1",
                    carbon_intensity=160.0,
                    renewable_energy_pct=80.0,
                    estimated_cost_usd_per_kwh=0.11,
                    latency_ms=145.0,
                ),
            ]
        )
        session.commit()
    finally:
        dependency.close()

    return client


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_cloud_regions_returns_empty_list(client: TestClient) -> None:
    response = client.get("/api/cloud/regions")

    assert response.status_code == 200
    assert response.json() == []


def test_cloud_regions_returns_stored_regions(
    seeded_client: TestClient,
) -> None:
    response = seeded_client.get("/api/cloud/regions")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2
    assert {item["region"] for item in data} == {
        "eu-north-1",
        "europe-west1",
    }


def test_carbon_readings_are_sorted_by_intensity(
    seeded_client: TestClient,
) -> None:
    response = seeded_client.get("/api/carbon/current")

    assert response.status_code == 200
    data = response.json()

    assert [item["carbon_intensity"] for item in data] == [
        90.0,
        160.0,
    ]


def test_region_response_contains_required_fields(
    seeded_client: TestClient,
) -> None:
    response = seeded_client.get("/api/cloud/regions")

    assert response.status_code == 200
    data = response.json()
    assert data

    assert {
        "id",
        "provider",
        "region",
        "carbon_intensity",
        "renewable_energy_pct",
        "estimated_cost_usd_per_kwh",
        "latency_ms",
        "updated_at",
    }.issubset(data[0].keys())
