"""Integration tests use only TEST_DATABASE_URL and disposable, unique schemas."""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.api.routes import get_db
from app.main import app
from app.models.core import BackgroundJob, JobListing, JobSource, SourceSyncRun
from app.services.ingestion.base import FetchResult, NormalizedJob
from app.services.ingestion.greenhouse import GreenhouseConnector
from app.services.ingestion.sync import enqueue_source_sync
from app.workers import runner


def setup_source(sessions, **kwargs):
    with sessions.begin() as db:
        source = JobSource(provider="greenhouse", board_token=uuid.uuid4().hex, company_name="Example", **kwargs)
        db.add(source)
        db.flush()
        return source.id


def enqueue(sessions, source_id, **kwargs):
    with sessions.begin() as db:
        return enqueue_source_sync(db, source_id, **kwargs)


def connector(payload=None, *, status=200, headers=None, network=False):
    def handle(request):
        if network:
            raise httpx.ConnectError("connection failed", request=request)
        return httpx.Response(status, json=payload, headers=headers)
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return GreenhouseConnector(client)


def execute(sessions, provider):
    item = runner.claim_task(sessions)
    assert item is not None
    runner.process_task(*item, session_factory=sessions, connectors={"greenhouse": provider})
    return item


def make_due(sessions, task_id):
    with sessions.begin() as db:
        db.get(BackgroundJob, task_id).run_after = runner.clock(db) - timedelta(seconds=1)


def test_repeat_update_partial_and_missing_postings(sessions):
    source_id = setup_source(sessions)
    record = {"id": 1, "title": "Engineer", "content": "<p>Original description</p>",
              "absolute_url": "https://example.com/1", "updated_at": "2026-01-01T10:00:00Z"}
    for index in range(3):
        enqueue(sessions, source_id)
        current = dict(record, title="Senior Engineer") if index == 2 else record
        payload = {"jobs": [current, {"title": "missing id"}]}
        execute(sessions, connector(payload))
        with sessions() as db:
            jobs = db.scalars(select(JobListing)).all()
            assert len(jobs) == 1
            job = jobs[0]
            if index == 0:
                identity, created, ingested = job.id, job.created_at, job.ingested_at
            assert (job.id, job.created_at, job.ingested_at) == (identity, created, ingested)
            assert job.title == current["title"]
            assert job.raw_metadata == current
            assert job.raw_text == record["content"]
            assert job.description_text == "Original description"
            assert job.source_url == record["absolute_url"]
            assert job.source_updated_at.isoformat() == "2026-01-01T10:00:00+00:00"
            runs = db.scalars(select(SourceSyncRun).order_by(SourceSyncRun.started_at)).all()
            assert len(runs) == index + 1
            run = runs[-1]
            assert run.status == "partial"
            assert (run.jobs_fetched, run.jobs_created, run.jobs_updated, run.jobs_rejected) == (
                2, int(index == 0), int(index != 0), 1)
            assert run.errors[0]["raw_record"] == {"title": "missing id"}
            assert db.get(JobSource, source_id).last_synced_at is not None
    enqueue(sessions, source_id)
    execute(sessions, connector({"jobs": []}))
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 1


@pytest.mark.parametrize("kind,retryable", [("network", True), ("rate_limit", True), ("server", True), ("not_found", False), ("invalid", False)])
def test_failed_fetch_protects_existing_data(sessions, kind, retryable):
    source_id = setup_source(sessions)
    enqueue(sessions, source_id)
    execute(sessions, connector({"jobs": [{"id": 1, "title": "Original"}]}))
    task_id = enqueue(sessions, source_id)
    providers = {
        "network": connector(network=True), "rate_limit": connector({}, status=429, headers={"Retry-After": "120"}),
        "server": connector({}, status=503), "not_found": connector({}, status=404), "invalid": connector({})}
    execute(sessions, providers[kind])
    with sessions() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.status == ("pending" if retryable else "failed")
        assert db.scalar(select(JobListing.title)) == "Original"
        run = db.scalar(select(SourceSyncRun).where(SourceSyncRun.task_id == task_id))
        assert run.status == "failed"
        assert run.jobs_created == 0
        assert run.errors[0]["code"] == task.last_error["code"]
        if kind == "rate_limit":
            assert task.run_after >= run.completed_at + timedelta(seconds=120)


def test_retry_exhaustion_and_backoff(sessions):
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)
    for attempt in range(1, 4):
        execute(sessions, connector(network=True))
        with sessions() as db:
            task = db.get(BackgroundJob, task_id)
            assert task.attempts == attempt
            assert task.status == ("failed" if attempt == 3 else "pending")
            assert task.lease_token is None
            if attempt < 3:
                assert task.run_after > runner.clock(db)
        if attempt < 3:
            assert runner.claim_task(sessions) is None
            make_due(sessions, task_id)
    assert runner.claim_task(sessions) is None
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(SourceSyncRun)) == 3
    assert [runner.retry_delay(n) for n in (1, 2, 3, 20)] == [5, 10, 20, 3600]
    assert runner.retry_delay(1, 120) == 120
    assert runner.retry_delay(1, float("inf")) == 5


def test_enqueue_idempotency_and_validation(sessions):
    source_id = setup_source(sessions)
    first = enqueue(sessions, source_id, idempotency_key="logical-request")
    assert enqueue(sessions, source_id, idempotency_key="logical-request") == first
    other = setup_source(sessions)
    with pytest.raises(ValueError):
        enqueue(sessions, other, idempotency_key="logical-request")
    inactive = setup_source(sessions, is_active=False)
    with pytest.raises(ValueError):
        enqueue(sessions, inactive)
    with pytest.raises(ValueError):
        enqueue(sessions, uuid.uuid4())


def test_concurrent_claims_and_same_source_serialization(sessions):
    source_id = setup_source(sessions)
    task_ids = {enqueue(sessions, source_id), enqueue(sessions, source_id)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: runner.claim_task(sessions), range(2)))
    assert {item[0] for item in claimed} == task_ids
    entered, finish = threading.Event(), threading.Event()

    class Blocking:
        def fetch(self, config):
            entered.set()
            assert finish.wait(10)
            return FetchResult(jobs_fetched=1, jobs=[NormalizedJob(
                provider=config.provider, board_token=config.board_token, external_job_id="1",
                company_name=config.company_name, title="First")])

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(runner.process_task, *claimed[0], session_factory=sessions, connectors={"greenhouse": Blocking()})
        assert entered.wait(5)
        runner.process_task(*claimed[1], session_factory=sessions, connectors={"greenhouse": connector({"jobs": []})})
        finish.set()
        future.result(timeout=10)
    with sessions() as db:
        second = db.get(BackgroundJob, claimed[1][0])
        assert second.status == "pending"
        assert second.last_error["code"] == "SOURCE_BUSY"
        assert db.scalar(select(func.count()).select_from(JobListing)) == 1
        assert db.scalar(select(func.count()).select_from(SourceSyncRun)) == 2
    make_due(sessions, claimed[1][0])
    execute(sessions, connector({"jobs": [{"id": 1, "title": "Second"}]}))
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 1
        assert db.scalar(select(JobListing.title)) == "Second"
        assert db.get(BackgroundJob, claimed[1][0]).status == "completed"


def expire(sessions, task_id):
    with sessions.begin() as db:
        db.get(BackgroundJob, task_id).lease_expires_at = runner.clock(db) - timedelta(seconds=1)


def test_expired_result_and_old_token_cannot_write(sessions):
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)
    item = runner.claim_task(sessions)

    class Expiring:
        def fetch(self, config):
            expire(sessions, task_id)
            return FetchResult(jobs_fetched=1, jobs=[NormalizedJob(
                provider=config.provider, board_token=config.board_token, external_job_id="1",
                company_name=config.company_name, title="Stale")])

    runner.process_task(*item, session_factory=sessions, connectors={"greenhouse": Expiring()})
    assert not runner.renew_lease(*item, sessions)
    assert runner.claim_task(sessions) is None  # recovery schedules backoff
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 0
        run = db.scalar(select(SourceSyncRun))
        assert run.status == "failed"
        assert run.errors[0]["code"] == "LEASE_EXPIRED"
    make_due(sessions, task_id)
    replacement = runner.claim_task(sessions)
    assert replacement[1] != item[1]
    runner.process_task(*item, session_factory=sessions)
    runner.process_task(*replacement, session_factory=sessions, connectors={"greenhouse": connector({"jobs": [{"id": 1, "title": "Current"}]})})
    with sessions() as db:
        assert db.scalar(select(JobListing.title)) == "Current"
        assert db.get(BackgroundJob, task_id).status == "completed"


def test_expired_last_attempt_is_terminal(sessions):
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)
    with sessions.begin() as db:
        db.get(BackgroundJob, task_id).max_attempts = 1
    runner.claim_task(sessions)
    expire(sessions, task_id)
    assert runner.claim_task(sessions) is None
    with sessions() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.status == "failed"
        assert task.lease_token is None


def test_heartbeat_extends_lease_during_fetch(sessions, monkeypatch):
    monkeypatch.setattr(runner, "HEARTBEAT_SECONDS", 0.02)
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)
    item = runner.claim_task(sessions)
    with sessions() as db:
        initial = db.get(BackgroundJob, task_id).lease_expires_at

    class Slow:
        def fetch(self, config):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with sessions() as db:
                    if db.get(BackgroundJob, task_id).lease_expires_at > initial:
                        return FetchResult(jobs_fetched=0)
                time.sleep(0.02)
            raise AssertionError("Heartbeat did not extend lease")

    runner.process_task(*item, session_factory=sessions, connectors={"greenhouse": Slow()})
    with sessions() as db:
        assert db.get(BackgroundJob, task_id).status == "completed"


def test_lease_expiring_inside_persistence_rolls_back(sessions, monkeypatch):
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)
    item = runner.claim_task(sessions)
    original = runner.persist_snapshot

    def slow(db, source, result, now):
        counts = original(db, source, result, now)
        task = db.get(BackgroundJob, task_id)
        task.lease_expires_at = runner.clock(db) - timedelta(seconds=1)
        return counts

    monkeypatch.setattr(runner, "persist_snapshot", slow)
    runner.process_task(*item, session_factory=sessions, connectors={"greenhouse": connector({"jobs": [{"id": 1, "title": "Discard"}]})})
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 0
        assert db.get(BackgroundJob, task_id).status == "processing"
        assert db.get(JobSource, source_id).last_synced_at is None


def test_manual_api_and_unsupported_tasks(sessions):
    def override_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/jobs", json={"raw_text": "Manual description preserved exactly for compatibility", "source_url": "https://example.com/manual"})
            assert response.status_code == 202
            task_id = uuid.UUID(response.json()["task_id"])
            item = runner.claim_task(sessions)
            runner.process_task(*item, session_factory=sessions)
            assert client.get(f"/api/v1/tasks/{task_id}").json()["error"]["code"] == "NOT_IMPLEMENTED"
        with sessions.begin() as db:
            manual = db.scalar(select(JobListing))
            assert manual.provider is None
            assert manual.raw_text == "Manual description preserved exactly for compatibility"
            db.add(BackgroundJob(task_type="job_analyze", payload={}))
        execute(sessions, connector({"jobs": []}))
        with sessions() as db:
            analyze = db.scalar(select(BackgroundJob).where(BackgroundJob.task_type == "job_analyze"))
            assert analyze.status == "failed"
            assert analyze.last_error["code"] == "NOT_IMPLEMENTED"
    finally:
        app.dependency_overrides.clear()


def test_storage_failure_rolls_back_snapshot(sessions, monkeypatch):
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)
    original = runner.persist_snapshot

    def broken(*args):
        original(*args)
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(runner, "persist_snapshot", broken)
    execute(sessions, connector({"jobs": [{"id": 1, "title": "Rollback"}]}))
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 0
        assert db.get(JobSource, source_id).last_synced_at is None
        assert db.get(BackgroundJob, task_id).status == "pending"
        run = db.scalar(select(SourceSyncRun))
        assert run.status == "failed"
        assert run.jobs_created == 0


@pytest.mark.parametrize("payload", [{}, {"source_id": "invalid"}, {"source_id": None}])
def test_invalid_task_payload_is_permanent_failure(sessions, payload):
    with sessions.begin() as db:
        task = BackgroundJob(task_type="source_sync", payload=payload)
        db.add(task)
        db.flush()
        task_id = task.id
    execute(sessions, connector({"jobs": []}))
    with sessions() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.status == "failed"
        assert task.last_error["code"] == "INVALID_PAYLOAD"


def test_source_disabled_during_fetch_protects_data(sessions):
    source_id = setup_source(sessions)
    task_id = enqueue(sessions, source_id)

    class Disabling:
        def fetch(self, config):
            with sessions.begin() as db:
                db.get(JobSource, source_id).is_active = False
            return FetchResult(jobs_fetched=1, jobs=[NormalizedJob(
                provider=config.provider, board_token=config.board_token, external_job_id="1",
                company_name=config.company_name, title="Discard")])

    execute(sessions, Disabling())
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 0
        task = db.get(BackgroundJob, task_id)
        assert task.status == "pending"
        assert task.last_error["code"] == "SOURCE_CHANGED"


def test_distinct_sources_can_fetch_concurrently(sessions):
    ids = [setup_source(sessions), setup_source(sessions)]
    for source_id in ids:
        enqueue(sessions, source_id)
    items = [runner.claim_task(sessions), runner.claim_task(sessions)]
    barrier = threading.Barrier(2)

    class Parallel:
        def fetch(self, config):
            barrier.wait(timeout=5)
            return FetchResult(jobs_fetched=1, jobs=[NormalizedJob(
                provider=config.provider, board_token=config.board_token, external_job_id="same-id",
                company_name=config.company_name, title="Independent")])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(runner.process_task, *item, session_factory=sessions,
                               connectors={"greenhouse": Parallel()}) for item in items]
        for future in futures:
            future.result(timeout=10)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(JobListing)) == 2
        assert all(task.status == "completed" for task in db.scalars(select(BackgroundJob)))


def test_concurrent_enqueue_deduplicates_request(sessions):
    source_id = setup_source(sessions)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = list(pool.map(lambda _: enqueue(sessions, source_id, idempotency_key="concurrent"), range(2)))
    assert tasks[0] == tasks[1]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 1
