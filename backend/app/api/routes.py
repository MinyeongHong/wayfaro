from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.core import BackgroundJob, JobListing, JobSource
from app.api.dependencies import require_ingestion_admin
from app.api.schemas import JobDetail, JobPage, Origin, RemoteMention, SortOrder, SyncAccepted, SyncRequest
from app.services.discovery import get_job as find_job, list_jobs
from app.services.ingestion.sync import enqueue_source_sync

router = APIRouter(prefix="/api/v1")


def get_db():
    with SessionLocal() as db:
        yield db


class JobCreate(BaseModel):
    raw_text: str = Field(min_length=30)
    source_url: str | None = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/jobs", status_code=202)
def create_job(body: JobCreate, db: Session = Depends(get_db)):
    job = JobListing(raw_text=body.raw_text, source_url=body.source_url)
    db.add(job)
    db.flush()
    task = BackgroundJob(task_type="job_extract", payload={"job_id": str(job.id)})
    db.add(task)
    db.commit()
    return {"job_id": str(job.id), "task_id": str(task.id), "status": "pending"}


@router.get("/tasks/{task_id}")
def get_task(task_id: UUID, request: Request, response: Response, db: Session = Depends(get_db)):
    task = db.get(BackgroundJob, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.task_type == "cv_compare":
        from app.services.matching.storage import owned_analysis
        owned_analysis(db, request, task_id=task.id)
        response.headers["Cache-Control"] = "no-store"
    return {"id": str(task.id), "task_type": task.task_type, "status": task.status,
            "attempts": task.attempts, "max_attempts": task.max_attempts,
            "result_ref": task.result_ref, "error": task.last_error}


@router.get("/jobs", response_model=JobPage)
def discover_jobs(page: int = Query(1, ge=1, le=1000000),
                  page_size: int = Query(20, ge=1, le=100),
                  q: str | None = Query(None, max_length=200),
                  location: str | None = Query(None, max_length=200),
                  country_text: str | None = Query(None, max_length=200),
                  region_text: str | None = Query(None, max_length=200),
                  source_id: UUID | None = None, origin: Origin | None = None,
                  remote_mention: RemoteMention | None = None, sort: SortOrder = "created_desc",
                  db: Session = Depends(get_db)):
    return list_jobs(db, page=page, page_size=page_size, q=q.strip() if q else None,
                     location=location.strip() if location else None,
                     country_text=country_text.strip() if country_text else None,
                     region_text=region_text.strip() if region_text else None,
                     source_id=source_id, origin=origin, remote_mention=remote_mention, sort=sort)


@router.get("/jobs/{job_id}", response_model=JobDetail)
def job_detail(job_id: UUID, db: Session = Depends(get_db)):
    job = find_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/ingestions/sync", status_code=202, response_model=SyncAccepted,
             dependencies=[Depends(require_ingestion_admin)])
def sync_source(body: SyncRequest,
                idempotency_key: str | None = Header(None, min_length=1, max_length=255),
                db: Session = Depends(get_db)):
    source = db.get(JobSource, body.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.is_active:
        raise HTTPException(status_code=409, detail="Source is inactive")
    try:
        task_id = enqueue_source_sync(db, body.source_id, idempotency_key=idempotency_key)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    task = db.get(BackgroundJob, task_id)
    return SyncAccepted(task_id=task.id, source_id=body.source_id, status=task.status,
                        status_url=f"/api/v1/tasks/{task.id}")
