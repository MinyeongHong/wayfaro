"""PostgreSQL queue with renewable leases and fenced ATS synchronization."""
import hashlib
import logging
import math
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError
from app.db.session import SessionLocal
from app.models.core import BackgroundJob, JobSource, SourceSyncRun
from app.services.ingestion.base import ConnectorError
from app.services.ingestion.greenhouse import GreenhouseConnector
from app.services.ingestion.sync import persist_snapshot, source_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
WORKER_ID = f"worker-{uuid.uuid4()}"
LEASE_SECONDS = 300
HEARTBEAT_SECONDS = 30


class LeaseLost(Exception):
    pass


def clock(db):
    return db.scalar(select(text("clock_timestamp()")))


def release(task):
    task.locked_by = task.lease_token = task.lease_expires_at = None


def retry_delay(attempt, retry_after=None):
    delay = min(3600, 5 * 2 ** min(max(attempt - 1, 0), 10))
    if retry_after is not None and math.isfinite(retry_after):
        delay = max(delay, min(max(0, retry_after), 86400))
    return delay


def claim_task(session_factory=SessionLocal):
    with session_factory.begin() as db:
        now = clock(db)
        expired = db.scalars(select(BackgroundJob).where(or_(
            (BackgroundJob.status == "processing") & or_(
                BackgroundJob.lease_expires_at <= now, BackgroundJob.lease_expires_at.is_(None)),
            (BackgroundJob.status == "pending") & (BackgroundJob.attempts >= BackgroundJob.max_attempts)
        )).with_for_update(skip_locked=True)).all()
        for task in expired:
            error = {"code": "LEASE_EXPIRED" if task.status == "processing" else "MAX_ATTEMPTS",
                     "message": "Worker lease expired" if task.status == "processing" else "Maximum attempts reached"}
            for run in db.scalars(select(SourceSyncRun).where(
                    SourceSyncRun.task_id == task.id, SourceSyncRun.status == "processing")):
                run.status, run.completed_at, run.errors = "failed", now, [error]
            task.last_error = error
            task.status = "failed" if task.attempts >= task.max_attempts else "pending"
            if task.status == "pending":
                task.run_after = now + timedelta(seconds=retry_delay(task.attempts))
            release(task)
        db.flush()
        task = db.scalar(select(BackgroundJob).where(
            BackgroundJob.status == "pending", BackgroundJob.run_after <= now,
            BackgroundJob.attempts < BackgroundJob.max_attempts
        ).order_by(BackgroundJob.created_at, BackgroundJob.id).with_for_update(skip_locked=True).limit(1))
        if task is None:
            return None
        task.status, task.locked_by, task.lease_token = "processing", WORKER_ID, uuid.uuid4()
        task.attempts += 1
        task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        return task.id, task.lease_token


def owned_task(db, task_id, token):
    task = db.scalar(select(BackgroundJob).where(BackgroundJob.id == task_id).with_for_update())
    check_lease(db, task, token)
    return task


def check_lease(db, task, token):
    if (task is None or task.status != "processing" or task.lease_token != token
            or task.lease_expires_at is None or task.lease_expires_at <= clock(db)):
        raise LeaseLost()


def renew_lease(task_id, token, session_factory=SessionLocal):
    try:
        with session_factory.begin() as db:
            task = owned_task(db, task_id, token)
            task.lease_expires_at = clock(db) + timedelta(seconds=LEASE_SECONDS)
        return True
    except LeaseLost:
        return False


@contextmanager
def heartbeat(task_id, token, session_factory):
    stop = threading.Event()

    def renew():
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                if not renew_lease(task_id, token, session_factory):
                    return
            except Exception:
                logger.exception("Lease heartbeat failed for %s", task_id)
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def finish_failure(task_id, token, error, *, retryable=False, retry_after=None,
                   run_id=None, session_factory=SessionLocal):
    with session_factory.begin() as db:
        task = owned_task(db, task_id, token)
        now = clock(db)
        if run_id is not None:
            run = db.get(SourceSyncRun, run_id)
            run.status, run.completed_at, run.errors = "failed", now, [error]
        db.flush()
        check_lease(db, task, token)
        task.last_error = error
        task.result_ref = {"sync_run_id": str(run_id)} if run_id else None
        task.status = "pending" if retryable and task.attempts < task.max_attempts else "failed"
        if task.status == "pending":
            task.run_after = now + timedelta(seconds=retry_delay(task.attempts, retry_after))
        release(task)


def fail_unsupported(task_id, token, session_factory=SessionLocal):
    finish_failure(task_id, token, {"code": "NOT_IMPLEMENTED",
                   "message": "LLM extraction and analysis are scheduled for a later phase"},
                   session_factory=session_factory)


def process_task(task_id, token, session_factory=SessionLocal, connectors=None, match_llm=None):
    run_id = None
    try:
        with heartbeat(task_id, token, session_factory):
            with session_factory.begin() as db:
                task = owned_task(db, task_id, token)
                task_type = task.task_type
                try:
                    source_id = uuid.UUID(task.payload["source_id"]) if task_type == "source_sync" else None
                except (KeyError, TypeError, ValueError, AttributeError) as exc:
                    raise ConnectorError("INVALID_PAYLOAD", "Expected a valid source_id UUID") from exc
                if source_id is not None:
                    source = db.get(JobSource, source_id)
                    if source is None:
                        raise ConnectorError("INVALID_SOURCE", "Source does not exist")
                    run = SourceSyncRun(source_id=source.id, task_id=task.id,
                                        attempt_number=task.attempts, status="processing")
                    db.add(run)
                    db.flush()
                    check_lease(db, task, token)
            if task_type == "cv_compare":
                from app.services.matching.worker import process_match_task
                process_match_task(task_id, token, session_factory, llm=match_llm)
                return
            if task_type != "source_sync":
                fail_unsupported(task_id, token, session_factory)
                return
            run_id = run.id
            try:
                config = source_config(source)
            except ValidationError as exc:
                raise ConnectorError("INVALID_SOURCE", "Invalid source configuration") from exc
            # A dedicated session-level advisory lock spans HTTP without an open transaction.
            # The same source is serialized across processes; other sources remain independent.
            with session_factory.kw["bind"].connect() as lock_db:
                lock_key = int.from_bytes(hashlib.blake2b(
                    source_id.bytes, digest_size=8, person=b"wayfaro-sync").digest(), "big", signed=True)
                acquired = lock_db.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
                lock_db.commit()
                if not acquired:
                    raise ConnectorError("SOURCE_BUSY", "Source is already synchronizing", retryable=True)
                try:
                    if not config.is_active:
                        raise ConnectorError("INACTIVE_SOURCE", "Source is inactive")
                    registry = connectors if connectors is not None else {"greenhouse": GreenhouseConnector()}
                    if config.provider not in registry:
                        raise ConnectorError("UNSUPPORTED_PROVIDER", "Unsupported source provider")
                    result = registry[config.provider].fetch(config)
                    # Persist on the connection that owns the advisory lock. A lost
                    # connection cannot leave a writer running without its source lock.
                    with sessionmaker(bind=lock_db, expire_on_commit=False).begin() as db:
                        task = owned_task(db, task_id, token)
                        source = db.scalar(select(JobSource).where(JobSource.id == source_id).with_for_update())
                        if source is None or not source.is_active or source_config(source) != config:
                            raise ConnectorError("SOURCE_CHANGED", "Source changed during synchronization", retryable=True)
                        check_lease(db, task, token)
                        now = clock(db)
                        created, updated = persist_snapshot(db, source, result, now)
                        run = db.get(SourceSyncRun, run_id)
                        run.status = "partial" if result.errors else "completed"
                        run.completed_at, run.jobs_fetched = now, result.jobs_fetched
                        run.jobs_created, run.jobs_updated = created, updated
                        run.jobs_rejected = len(result.errors)
                        run.errors = [error.model_dump(mode="json") for error in result.errors]
                        db.flush()
                        check_lease(db, task, token)
                        task.status, task.last_error = "completed", None
                        task.result_ref = {"sync_run_id": str(run_id)}
                        release(task)
                finally:
                    try:
                        lock_db.rollback()
                        lock_db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                        lock_db.commit()
                    except Exception:
                        # Never return a connection with a session lock to the pool.
                        lock_db.invalidate()
                        raise
    except LeaseLost:
        logger.info("Discarded stale worker result for %s", task_id)
    except Exception as exc:
        known = isinstance(exc, ConnectorError)
        error = {"code": exc.code if known else "SYNC_ERROR",
                 "message": str(exc) if known else "Synchronization failed"}
        if not known:
            logger.exception("Task %s failed", task_id)
        try:
            finish_failure(task_id, token, error, retryable=exc.retryable if known else True,
                           retry_after=exc.retry_after_seconds if known else None,
                           run_id=run_id, session_factory=session_factory)
        except LeaseLost:
            logger.info("Discarded stale failure for %s", task_id)


def main():
    logger.info("Worker started: %s", WORKER_ID)
    last_cleanup = 0.0
    while True:
        try:
            if time.monotonic() - last_cleanup >= 60:
                from app.services.matching.storage import cleanup_expired
                cleanup_expired(SessionLocal)
                last_cleanup = time.monotonic()
            item = claim_task()
            if item is None:
                time.sleep(2)
            else:
                process_task(*item)
        except Exception:
            logger.exception("Worker iteration failed")
            time.sleep(2)


if __name__ == "__main__":
    main()
