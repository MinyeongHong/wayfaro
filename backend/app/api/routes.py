from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.models.core import BackgroundJob

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/tasks/{task_id}")
def get_task(task_id: UUID, request: Request, response: Response, db: Session = Depends(get_db)):
    task = db.get(BackgroundJob, task_id)
    if task is None or task.task_type != "cv_compare":
        raise HTTPException(status_code=404, detail="Task not found")
    from app.services.matching.storage import owned_analysis
    owned_analysis(db, request, task_id=task.id)
    response.headers["Cache-Control"] = "no-store"
    return {"id": str(task.id), "task_type": task.task_type, "status": task.status,
            "attempts": task.attempts, "max_attempts": task.max_attempts,
            "result_ref": task.result_ref, "error": task.last_error}
