
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
from app.models import Base


@asynccontextmanager
async def disabled_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
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
    monkeypatch.setattr(app.router, "lifespan_context", disabled_lifespan)

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def valid_payload() -> dict[str, object]:
    return {
        "name": "Image classification training",
        "workload_type": "ml_training",
        "priority": "high",
        "required_cpu_cores": 4,
        "required_memory_gb": 8,
        "max_latency_ms": 200,
        "carbon_aware": True,
    }


def test_create_workload(client: TestClient) -> None:
    response = client.post("/api/workload/create", json=valid_payload())

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Image classification training"
    assert data["status"] == "pending"
    assert data["id"] > 0


def test_list_workloads(client: TestClient) -> None:
    client.post("/api/workload/create", json=valid_payload())

    response = client.get("/api/workload/list")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_create_workload_rejects_invalid_type(client: TestClient) -> None:
    payload = valid_payload()
    payload["workload_type"] = "unknown"

    response = client.post("/api/workload/create", json=payload)

    assert response.status_code == 422


def test_create_workload_rejects_invalid_cpu(client: TestClient) -> None:
    payload = valid_payload()
    payload["required_cpu_cores"] = 0

    response = client.post("/api/workload/create", json=payload)

    assert response.status_code == 422


def test_create_workload_rejects_blank_name(client: TestClient) -> None:
    payload = valid_payload()
    payload["name"] = "   "

    response = client.post("/api/workload/create", json=payload)

    assert response.status_code == 422
