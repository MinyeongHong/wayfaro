"""Database persistence for ATS snapshots; no eligibility inference or deletion."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.core import BackgroundJob, JobListing, JobSource
from .base import SourceConfig


def source_config(source):
    return SourceConfig(provider=source.provider, board_token=source.board_token,
                        company_name=source.company_name, is_active=source.is_active)


def enqueue_source_sync(db, source_id, *, idempotency_key=None):
    """Caller owns the transaction; a key deduplicates a logical request."""
    source = db.get(JobSource, source_id)
    if source is None or not source.is_active:
        raise ValueError("Source does not exist or is inactive")
    source_config(source)
    if source.provider != "greenhouse":
        raise ValueError("Unsupported provider")
    statement = insert(BackgroundJob).values(
        task_type="source_sync", payload={"source_id": str(source.id)},
        idempotency_key=idempotency_key)
    if idempotency_key is not None:
        statement = statement.on_conflict_do_nothing(index_elements=["idempotency_key"])
    task_id = db.scalar(statement.returning(BackgroundJob.id))
    if task_id is None:
        task = db.scalar(select(BackgroundJob).where(BackgroundJob.idempotency_key == idempotency_key))
        if task.task_type != "source_sync" or task.payload != {"source_id": str(source.id)}:
            raise ValueError("Idempotency key belongs to a different request")
        return task.id
    return task_id


def persist_snapshot(db, source, result, now):
    """Called only while holding both the source lock and a valid task lease."""
    created = updated = 0
    for job in result.jobs:
        if (job.provider, job.board_token) != (source.provider, source.board_token):
            raise ValueError("Connector returned a different source identity")
        values = job.model_dump(exclude={"updated_at"})
        values.update(source_id=source.id, source_updated_at=job.updated_at,
                      raw_text=job.description_html or job.description_text or "", updated_at=now)
        statement = insert(JobListing).values(**values)
        inserted = db.scalar(statement.on_conflict_do_nothing(
            constraint="uq_job_listings_ats_identity").returning(JobListing.id))
        if inserted is not None:
            created += 1
        else:
            changes = {key: value for key, value in values.items()
                       if key not in ("provider", "board_token", "external_job_id")}
            db.execute(statement.on_conflict_do_update(
                constraint="uq_job_listings_ats_identity", set_=changes))
            updated += 1
    source.last_synced_at = now
    source.updated_at = now
    return created, updated
