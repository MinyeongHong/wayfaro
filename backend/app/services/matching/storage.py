"""Private temporary storage. Lock order is always task -> analysis."""
import hashlib
import secrets
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, text
from app.config import settings
from app.models.core import AnalysisSession, BackgroundJob, CVMatchAnalysis

COOKIE = "wayfaro_cv_session"
CSRF_COOKIE = "wayfaro_cv_csrf"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now(db):
    return db.scalar(select(func.clock_timestamp()))


def session_for(db, request):
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 200:
        return None
    return db.scalar(select(AnalysisSession).where(
        AnalysisSession.token_hash == digest(token), AnalysisSession.expires_at > now(db)))


def check_origin(request):
    origin = request.headers.get("origin")
    if (origin is not None and origin not in settings.cv_match_allowed_origins
            or request.headers.get("sec-fetch-site") == "cross-site"):
        raise HTTPException(403, "Origin is not allowed")


def check_csrf(request, session):
    check_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or len(supplied) > 200 or not secrets.compare_digest(digest(supplied), session.csrf_hash):
        raise HTTPException(403, "Invalid CSRF token")


def create_request(db, request, response, body):
    check_origin(request)
    # Serialize budget checks across API processes without Redis.
    db.execute(text("SELECT pg_advisory_xact_lock(723914602)"))
    owner = session_for(db, request)
    if owner:
        check_csrf(request, owner)
        csrf = request.headers["x-csrf-token"]
    else:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        owner = AnalysisSession(token_hash=digest(token), csrf_hash=digest(csrf),
                                expires_at=now(db) + timedelta(days=7))
        db.add(owner)
        db.flush()
        response.set_cookie(COOKIE, token, max_age=7 * 86400, httponly=True,
                            secure=settings.cv_match_cookie_secure, samesite="strict", path="/api/v1")
        response.set_cookie(CSRF_COOKIE, csrf, max_age=7 * 86400, httponly=False,
                            secure=settings.cv_match_cookie_secure, samesite="strict", path="/")
    count = db.scalar(select(func.count()).select_from(CVMatchAnalysis).where(
        CVMatchAnalysis.session_id == owner.id, CVMatchAnalysis.expires_at > now(db)))
    pending = db.scalar(select(func.count()).select_from(BackgroundJob).where(
        BackgroundJob.task_type == "cv_compare", BackgroundJob.status.in_(["pending", "processing"])))
    daily = db.scalar(select(func.count()).select_from(BackgroundJob).where(
        BackgroundJob.task_type == "cv_compare", BackgroundJob.created_at >= now(db) - timedelta(hours=24)))
    if (count >= settings.cv_match_session_limit or pending >= settings.cv_match_global_pending_limit
            or daily >= settings.cv_match_global_daily_limit):
        raise HTTPException(429, "Temporary analysis limit reached")
    task = BackgroundJob(task_type="cv_compare", payload={})
    db.add(task)
    db.flush()
    analysis = CVMatchAnalysis(session_id=owner.id, task_id=task.id, cv_text=body.cv_text,
        jd_text=body.jd_text, cv_hash=digest(body.cv_text), jd_hash=digest(body.jd_text),
        policy_version=body.policy_version,
        expires_at=min(owner.expires_at, now(db) + timedelta(hours=settings.cv_match_retention_hours)))
    db.add(analysis)
    db.flush()
    task.payload = {"analysis_id": str(analysis.id)}
    db.commit()
    return analysis, task, csrf


def owned_analysis(db, request, analysis_id=None, task_id=None):
    owner = session_for(db, request)
    if owner is None:
        raise HTTPException(404, "Analysis not found")
    query = select(CVMatchAnalysis).where(CVMatchAnalysis.session_id == owner.id,
                                         CVMatchAnalysis.expires_at > now(db))
    query = query.where(CVMatchAnalysis.id == analysis_id) if analysis_id else query.where(CVMatchAnalysis.task_id == task_id)
    analysis = db.scalar(query)
    if analysis is None:
        raise HTTPException(404, "Analysis not found")
    return analysis, owner


def remove_analysis(db, analysis, *, code="ANALYSIS_DELETED"):
    task = db.scalar(select(BackgroundJob).where(BackgroundJob.id == analysis.task_id).with_for_update())
    # The worker locks this task before saving, so deletion cannot resurrect data.
    current = db.scalar(select(CVMatchAnalysis).where(CVMatchAnalysis.id == analysis.id).with_for_update())
    if current is not None:
        db.delete(current)
    task.status, task.last_error, task.result_ref = "failed", {"code": code}, None
    task.payload = {}
    task.locked_by = task.lease_token = task.lease_expires_at = None


def cleanup_expired(session_factory, limit=100):
    with session_factory() as db:
        candidates = db.execute(select(CVMatchAnalysis.id, CVMatchAnalysis.task_id)
            .join(AnalysisSession, AnalysisSession.id == CVMatchAnalysis.session_id)
            .where(or_(CVMatchAnalysis.expires_at <= now(db), AnalysisSession.expires_at <= now(db)))
            .order_by(CVMatchAnalysis.expires_at).limit(limit)).all()
    removed = 0
    for analysis_id, task_id in candidates:
        with session_factory.begin() as db:
            task = db.scalar(select(BackgroundJob).where(BackgroundJob.id == task_id).with_for_update(skip_locked=True))
            if task is None:
                continue
            analysis = db.get(CVMatchAnalysis, analysis_id)
            if analysis is not None:
                remove_analysis(db, analysis, code="ANALYSIS_EXPIRED")
                removed += 1
    with session_factory.begin() as db:
        db.execute(delete(AnalysisSession).where(AnalysisSession.expires_at <= now(db),
            ~select(CVMatchAnalysis.id).where(CVMatchAnalysis.session_id == AnalysisSession.id).exists()))
    return removed
