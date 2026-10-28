from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base, CloudRegion, MonitoringAlert, Workload, WorkloadStatusHistory


@asynccontextmanager
async def disabled_lifespan(_: FastAPI):
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    now = datetime.now(timezone.utc)
    with testing_session() as session:
        session.add_all([
            Workload(name="Monitor workload", workload_type="batch", priority="normal",
                     required_cpu_cores=4, required_memory_gb=8.0, max_latency_ms=200.0,
                     carbon_aware=True, status="pending", created_at=now),
            CloudRegion(provider="ProviderA", region="green-region", carbon_intensity=100.0,
                        carbon_updated_at=now, renewable_energy_pct=90.0,
                        estimated_cost_usd_per_kwh=0.10, latency_ms=50.0,
                        available_cpu_cores=8, available_memory_gb=16.0,
                        total_cpu_cores=16, total_memory_gb=32.0),
            CloudRegion(provider="ProviderB", region="fallback-region", carbon_intensity=300.0,
                        carbon_updated_at=now, renewable_energy_pct=40.0,
                        estimated_cost_usd_per_kwh=0.12, latency_ms=60.0,
                        available_cpu_cores=16, available_memory_gb=32.0,
                        total_cpu_cores=32, total_memory_gb=64.0),
        ])
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
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def db_session():
    generator = app.dependency_overrides[get_db]()
    return next(generator), generator


def test_health_summary_shape(client):
    response = client.get("/api/monitor/health")
    assert response.status_code == 200
    body = response.json()
    assert body["region_count"] == 2
    assert body["open_alerts_by_severity"] == {"warning": 0, "critical": 0}
    assert body["workloads_by_status"]["pending"] == 1
    assert body["carbon_freshness"]["fresh"] == 2


def test_regions_returns_utilisation_and_carbon_freshness(client):
    response = client.get("/api/monitor/regions")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["level"] == "ok"
    assert response.json()[0]["carbon_freshness"] == "fresh"


def test_regions_reports_stale_and_missing_carbon(client):
    session, generator = db_session()
    try:
        regions = session.scalars(select(CloudRegion).order_by(CloudRegion.id)).all()
        regions[0].carbon_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        regions[1].carbon_updated_at = None
        session.commit()
    finally:
        generator.close()
    states = {r["region"]: r["carbon_freshness"] for r in client.get("/api/monitor/regions").json()}
    assert states == {"green-region": "stale", "fallback-region": "missing"}


def test_workload_pagination(client):
    response = client.get("/api/monitor/workloads?page=1&page_size=1")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["pages"] == 1
    assert len(response.json()["items"]) == 1


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101"])
def test_workload_pagination_bounds(client, query):
    response = client.get(f"/api/monitor/workloads?{query}")
    assert response.status_code == 422


def test_workload_status_filter(client):
    assert client.get("/api/monitor/workloads?status=pending").json()["total"] == 1
    assert client.get("/api/monitor/workloads?status=completed").json()["total"] == 0


def test_workload_invalid_status_filter_is_422(client):
    assert client.get("/api/monitor/workloads?status=unknown").status_code == 422


def test_workload_invalid_date_range_is_422(client):
    response = client.get("/api/monitor/workloads?created_from=2026-10-20T12:00:00Z&created_to=2026-10-19T12:00:00Z")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_time_range"


def test_workload_detail_includes_empty_history(client):
    response = client.get("/api/monitor/workloads/1")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["history"] == []


def test_workload_detail_missing_is_404(client):
    response = client.get("/api/monitor/workloads/999")
    assert response.status_code == 404
    assert response.json()["code"] == "workload_not_found"


def test_transition_pending_to_deferred_creates_history(client):
    response = client.post("/api/monitor/workloads/1/transition", json={"to_status": "deferred", "reason": "waiting"})
    assert response.status_code == 200
    detail = client.get("/api/monitor/workloads/1").json()
    assert detail["status"] == "deferred"
    assert detail["history"][0]["reason"] == "waiting"


def test_transition_illegal_is_409(client):
    response = client.post("/api/monitor/workloads/1/transition", json={"to_status": "completed"})
    assert response.status_code == 409
    assert response.json()["code"] == "illegal_transition"


def test_transition_unknown_status_is_422(client):
    response = client.post("/api/monitor/workloads/1/transition", json={"to_status": "bogus"})
    assert response.status_code == 422


def test_transition_missing_workload_is_404(client):
    response = client.post("/api/monitor/workloads/999/transition", json={"to_status": "deferred"})
    assert response.status_code == 404


def test_transition_rejects_extra_body_fields(client):
    response = client.post("/api/monitor/workloads/1/transition", json={"to_status": "deferred", "unexpected": True})
    assert response.status_code == 422


def test_alerts_pagination_and_filters(client):
    session, generator = db_session()
    try:
        session.add_all([
            MonitoringAlert(alert_type="cpu_utilisation", severity="critical", region_id=1,
                            workload_id=None, created_at=datetime.now(timezone.utc), resolved=False,
                            message="cpu high", fingerprint="test:cpu"),
            MonitoringAlert(alert_type="stale_carbon_data", severity="warning", region_id=2,
                            workload_id=None, created_at=datetime.now(timezone.utc), resolved=True,
                            message="carbon stale", fingerprint="test:carbon"),
        ])
        session.commit()
    finally:
        generator.close()
    page = client.get("/api/monitor/alerts?page=1&page_size=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    filtered = client.get("/api/monitor/alerts?severity=critical&resolved=false&region_id=1&type=cpu_utilisation")
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


def test_alerts_invalid_date_range_is_422(client):
    response = client.get("/api/monitor/alerts?created_from=2026-10-20T12:00:00Z&created_to=2026-10-19T12:00:00Z")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_time_range"


def test_evaluate_creates_and_deduplicates_alerts(client):
    session, generator = db_session()
    try:
        region = session.scalar(select(CloudRegion).where(CloudRegion.region == "green-region"))
        assert region is not None
        region.available_cpu_cores = 1
        region.available_memory_gb = 2.0
        region.carbon_updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()
    finally:
        generator.close()
    first = client.post("/api/monitor/evaluate")
    second = client.post("/api/monitor/evaluate")
    assert first.status_code == second.status_code == 200
    assert first.json()["created_count"] >= 1
    assert second.json()["created_count"] == 0
    assert second.json()["skipped_count"] >= 1


def test_alert_resolve_and_missing_alert(client):
    session, generator = db_session()
    try:
        alert = MonitoringAlert(alert_type="cpu_utilisation", severity="warning", region_id=1,
                                workload_id=None, created_at=datetime.now(timezone.utc), resolved=False,
                                message="test", fingerprint="resolve:test")
        session.add(alert)
        session.commit()
        alert_id = alert.id
    finally:
        generator.close()
    assert client.post(f"/api/monitor/alerts/{alert_id}/resolve").json() == {"id": alert_id, "resolved": True}
    missing = client.post("/api/monitor/alerts/999/resolve")
    assert missing.status_code == 404
    assert missing.json()["code"] == "alert_not_found"


def test_end_to_end_schedule_history_capacity_and_health(client):
    before = client.get("/api/monitor/regions").json()
    response = client.post("/api/schedule", json={"workload_id": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    detail = client.get("/api/monitor/workloads/1").json()
    assert detail["status"] == "scheduled"
    assert detail["history"][-1]["to_status"] == "scheduled"
    after = client.get("/api/monitor/regions").json()
    selected_before = next(r for r in before if r["region"] == response.json()["region"])
    selected_after = next(r for r in after if r["region"] == response.json()["region"])
    assert selected_after["available_cpu_cores"] < selected_before["available_cpu_cores"]
    health = client.get("/api/monitor/health").json()
    assert health["workloads_by_status"]["scheduled"] == 1
