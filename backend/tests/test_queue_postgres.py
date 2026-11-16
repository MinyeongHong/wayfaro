"""Common queue invariants, independent of external providers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import uuid
import pytest
from app.models.core import BackgroundJob
from app.workers import runner


def enqueue(sessions, **fields):
    with sessions.begin() as db:
        task = BackgroundJob(task_type='cv_compare', payload={}, **fields)
        db.add(task)
        db.flush()
        return task.id


def test_parallel_claims_are_unique(sessions):
    ids = {enqueue(sessions) for _ in range(8)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: runner.claim_task(sessions), range(8)))
    assert {item[0] for item in claims} == ids
    assert runner.claim_task(sessions) is None
    with sessions() as db:
        assert all(db.get(BackgroundJob, task_id).attempts == 1 for task_id in ids)


def test_expiry_reclaim_fences_old_worker(sessions):
    task_id = enqueue(sessions)
    _, old_token = runner.claim_task(sessions)
    with sessions.begin() as db:
        db.get(BackgroundJob, task_id).lease_expires_at = runner.clock(db) - timedelta(seconds=1)
    assert not runner.renew_lease(task_id, old_token, sessions)
    assert runner.claim_task(sessions) is None
    with sessions.begin() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.status == 'pending' and task.last_error['code'] == 'LEASE_EXPIRED'
        assert task.run_after > runner.clock(db)
        task.run_after = runner.clock(db) - timedelta(seconds=1)
    _, token = runner.claim_task(sessions)
    assert token != old_token
    with pytest.raises(runner.LeaseLost):
        runner.finish_failure(task_id, old_token, {'code': 'STALE'}, session_factory=sessions)
    with sessions() as db:
        assert db.get(BackgroundJob, task_id).lease_token == token


@pytest.mark.parametrize('status', ['pending', 'processing'])
def test_exhausted_attempts_are_terminal(sessions, status):
    task_id = enqueue(sessions, status=status, attempts=3, max_attempts=3)
    assert runner.claim_task(sessions) is None
    with sessions() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.status == 'failed' and task.lease_token is None


def test_heartbeat_renews_only_owned_lease(sessions, monkeypatch):
    task_id = enqueue(sessions)
    _, token = runner.claim_task(sessions)
    monkeypatch.setattr(runner, 'HEARTBEAT_SECONDS', .01)
    original = runner.renew_lease
    renewed = threading.Event()
    def renew(*args):
        result = original(*args)
        if result:
            renewed.set()
        return result
    monkeypatch.setattr(runner, 'renew_lease', renew)
    with sessions.begin() as db:
        db.get(BackgroundJob, task_id).lease_expires_at = runner.clock(db) + timedelta(seconds=2)
    with runner.heartbeat(task_id, token, sessions):
        assert renewed.wait(3)
    with sessions() as db:
        assert (db.get(BackgroundJob, task_id).lease_expires_at - runner.clock(db)).total_seconds() > 250
    assert not original(task_id, uuid.uuid4(), sessions)


def test_unknown_task_is_terminal_without_retry(sessions):
    with sessions.begin() as db:
        task = BackgroundJob(task_type='invalid', payload={})
        db.add(task)
        db.flush()
        task_id = task.id
    runner.process_task(*runner.claim_task(sessions), session_factory=sessions)
    with sessions() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.status == 'failed'
        assert task.last_error['code'] == 'UNSUPPORTED_TASK_TYPE'
        assert task.lease_token is None


def test_live_lease_is_not_reclaimed(sessions):
    task_id = enqueue(sessions)
    _, token = runner.claim_task(sessions)
    assert runner.claim_task(sessions) is None
    with sessions() as db:
        task = db.get(BackgroundJob, task_id)
        assert task.lease_token == token and task.attempts == 1


def test_claim_skips_locked_task(sessions):
    from sqlalchemy import select
    first = enqueue(sessions)
    second = enqueue(sessions)
    with sessions.begin() as db:
        db.scalar(select(BackgroundJob).where(BackgroundJob.id == first).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            claimed = pool.submit(runner.claim_task, sessions).result(timeout=5)
        assert claimed[0] == second
    assert runner.claim_task(sessions)[0] == first
