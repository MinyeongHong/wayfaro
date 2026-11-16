"""PostgreSQL queue with renewable leases and fenced CV comparison."""
import logging
import math
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import or_, select, text
from app.db.session import SessionLocal
from app.models.core import BackgroundJob

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
                logger.warning("Lease heartbeat failed")
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()


def finish_failure(task_id, token, error, *, retryable=False, retry_after=None,
                   session_factory=SessionLocal):
    with session_factory.begin() as db:
        task = owned_task(db, task_id, token)
        now = clock(db)
        db.flush()
        check_lease(db, task, token)
        task.last_error = error
        task.result_ref = None
        task.status = "pending" if retryable and task.attempts < task.max_attempts else "failed"
        if task.status == "pending":
            task.run_after = now + timedelta(seconds=retry_delay(task.attempts, retry_after))
        release(task)


def process_task(task_id, token, session_factory=SessionLocal, match_llm=None):
    try:
        with heartbeat(task_id, token, session_factory):
            with session_factory.begin() as db:
                task_type = owned_task(db, task_id, token).task_type
            if task_type != "cv_compare":
                finish_failure(task_id, token, {"code": "UNSUPPORTED_TASK_TYPE",
                    "message": "Unsupported task type"}, session_factory=session_factory)
                return
            from app.services.matching.worker import process_match_task
            process_match_task(task_id, token, session_factory, llm=match_llm)
    except LeaseLost:
        logger.info("Worker ownership lost; result discarded")


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
            logger.warning("Worker iteration failed")
            time.sleep(2)


if __name__ == "__main__":
    main()
