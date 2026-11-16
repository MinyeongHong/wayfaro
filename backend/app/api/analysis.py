"""Private CV comparison API. No public JobListing mutation."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.api.routes import get_db
from app.config import settings
from app.models.core import BackgroundJob
from app.services.matching.schemas import AnalysisAccepted, AnalysisCreate, AnalysisView, POLICY_VERSION
from app.services.matching.storage import create_request, owned_analysis, check_csrf, remove_analysis

router = APIRouter(prefix="/api/v1")


@router.get("/analyses/policy")
def analysis_policy(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"policy_version": POLICY_VERSION, "provider": "Gemini", "consent_required": True,
            "retention_hours": settings.cv_match_retention_hours, "session_retention_days": 7,
            "notice": "CV와 JD 원문이 비교 분석을 위해 Google Gemini API로 전송됩니다. 입력과 결과는 지정된 기간 동안만 임시 보관하며 영구 저장하지 않습니다.",
            "provider_retention_notice": "Google Gemini의 데이터 사용·보관은 계정·서비스 이용 조건에 따라 달라집니다. 무보관이나 학습 제외를 보장하지 않습니다. 외부 전송은 삭제 요청으로 취소할 수 없습니다.",
            "provider_policy_url": "https://ai.google.dev/gemini-api/terms",
            "deletion_notice": "만료 즉시 조회와 새 LLM 호출을 차단합니다. Worker가 실행 중이면 주기적으로 DB에서 삭제하며 백업·외부 제공자 보관은 별도입니다.",
            "limits": {"max_document_characters": 40000, "max_request_bytes": 350000,
                       "analyses_per_session": settings.cv_match_session_limit,
                       "global_daily_requests": settings.cv_match_global_daily_limit},
            "score": None, "work_eligibility": "NOT_ASSESSED"}


@router.post("/analyses", status_code=202, response_model=AnalysisAccepted)
def create_analysis(body: AnalysisCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    if (settings.gemini_api_key is None or not settings.gemini_api_key.get_secret_value().strip()
            or not settings.gemini_model.strip()):
        raise HTTPException(503, "LLM is not configured")
    analysis, task, csrf = create_request(db, request, response, body)
    response.headers["Cache-Control"] = "no-store"
    return AnalysisAccepted(analysis_id=analysis.id, task_id=task.id, status=task.status,
        status_url=f"/api/v1/analyses/{analysis.id}", expires_at=analysis.expires_at, csrf_token=csrf)


@router.get("/analyses/{analysis_id}", response_model=AnalysisView)
def get_analysis(analysis_id: UUID, request: Request, response: Response, db: Session = Depends(get_db)):
    analysis, _ = owned_analysis(db, request, analysis_id=analysis_id)
    task = db.get(BackgroundJob, analysis.task_id)
    response.headers["Cache-Control"] = "no-store"
    return AnalysisView(analysis_id=analysis.id, task_id=task.id, status=task.status,
                        expires_at=analysis.expires_at, result=analysis.result, error=task.last_error)


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: UUID, request: Request, db: Session = Depends(get_db)):
    analysis, owner = owned_analysis(db, request, analysis_id=analysis_id)
    check_csrf(request, owner)
    remove_analysis(db, analysis)
    db.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
