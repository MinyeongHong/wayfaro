import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from app.api.routes import get_db
from app.config import settings
from app.main import app
from app.models.core import BackgroundJob, JobSource

HEADERS = {"Authorization": "Bearer test-admin-only"}


@pytest.fixture
def admin_client(sessions, monkeypatch):
    monkeypatch.setattr(settings, "ingestion_admin_token", SecretStr("test-admin-only"))
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def source_id(sessions):
    with sessions.begin() as db:
        source = JobSource(provider="greenhouse", board_token="example", company_name="Example")
        db.add(source)
        db.flush()
        return str(source.id)


def test_auth_fails_closed_without_db(monkeypatch):
    def forbidden_db():
        pytest.fail("Unauthorized calls must not open a database session")
        yield
    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            monkeypatch.setattr(settings, "ingestion_admin_token", None)
            assert client.post("/api/v1/ingestions/sync", json={"source_id": str(uuid.uuid4())}, headers=HEADERS).status_code == 503
            monkeypatch.setattr(settings, "ingestion_admin_token", SecretStr(""))
            assert client.post("/api/v1/ingestions/sync", json={"source_id": str(uuid.uuid4())}, headers=HEADERS).status_code == 503
            monkeypatch.setattr(settings, "ingestion_admin_token", SecretStr("test-admin-only"))
            for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic bad"}):
                assert client.post("/api/v1/ingestions/sync", json={"source_id": str(uuid.uuid4())}, headers=headers).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_enqueue_and_task_status(admin_client, source_id, sessions):
    response = admin_client.post("/api/v1/ingestions/sync", json={"source_id": source_id}, headers=HEADERS)
    assert response.status_code == 202
    body = response.json()
    assert body["source_id"] == source_id and body["status"] == "pending"
    task = admin_client.get(body["status_url"]).json()
    assert task["task_type"] == "source_sync" and task["attempts"] == 0
    with sessions() as db:
        queued = db.get(BackgroundJob, uuid.UUID(body["task_id"]))
        assert queued.payload == {"source_id": source_id}


def test_persistent_idempotency_and_actual_status(admin_client, source_id, sessions):
    headers = {**HEADERS, "Idempotency-Key": "logical-request"}
    first = admin_client.post("/api/v1/ingestions/sync", json={"source_id": source_id}, headers=headers).json()
    with sessions.begin() as db:
        db.get(BackgroundJob, uuid.UUID(first["task_id"])).status = "completed"
    second = admin_client.post("/api/v1/ingestions/sync", json={"source_id": source_id}, headers=headers)
    assert second.status_code == 202
    assert second.json()["task_id"] == first["task_id"] and second.json()["status"] == "completed"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 1


def test_concurrent_idempotency(admin_client, source_id, sessions):
    def submit(_):
        with TestClient(app) as client:
            return client.post("/api/v1/ingestions/sync", json={"source_id": source_id},
                               headers={**HEADERS, "Idempotency-Key": "concurrent-request"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert all(response.status_code == 202 for response in responses)
    assert responses[0].json()["task_id"] == responses[1].json()["task_id"]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 1


def test_invalid_source_and_conflicting_key(admin_client, source_id, sessions):
    body = {"source_id": source_id}
    headers = {**HEADERS, "Idempotency-Key": "conflict"}
    assert admin_client.post("/api/v1/ingestions/sync", json=body, headers=headers).status_code == 202
    with sessions.begin() as db:
        other = JobSource(provider="greenhouse", board_token="other", company_name="Other")
        db.add(other)
        db.flush()
        other_id = str(other.id)
    assert admin_client.post("/api/v1/ingestions/sync", json={"source_id": other_id}, headers=headers).status_code == 409
    with sessions.begin() as db:
        db.get(JobSource, uuid.UUID(source_id)).is_active = False
    assert admin_client.post("/api/v1/ingestions/sync", json=body, headers=HEADERS).status_code == 409
    assert admin_client.post("/api/v1/ingestions/sync", json={"source_id": str(uuid.uuid4())}, headers=HEADERS).status_code == 404
    assert admin_client.post("/api/v1/ingestions/sync", json={"source_id": "invalid"}, headers=HEADERS).status_code == 422
    assert admin_client.post("/api/v1/ingestions/sync", json={"source_id": other_id}, headers={**HEADERS, "Idempotency-Key": "x" * 256}).status_code == 422
