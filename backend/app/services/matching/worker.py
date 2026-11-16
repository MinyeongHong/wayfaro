"""CV worker called under the existing queue heartbeat. Private errors are codes only."""
import logging
from sqlalchemy import select
from app.models.core import AnalysisSession, CVMatchAnalysis
from .llm import MatchError, GeminiMatchLLM
from .pipeline import run_match
from .schemas import POLICY_VERSION
from .storage import now, remove_analysis

logger = logging.getLogger(__name__)


def process_match_task(task_id, token, session_factory, llm=None):
    from app.workers.runner import LeaseLost, check_lease, finish_failure, owned_task, release

    def read_live(db):
        task = owned_task(db, task_id, token)
        analysis = db.scalar(select(CVMatchAnalysis).where(
            CVMatchAnalysis.task_id == task_id).with_for_update())
        if analysis is None:
            raise LeaseLost()
        owner = db.get(AnalysisSession, analysis.session_id)
        current = now(db)
        if analysis.expires_at <= current or owner is None or owner.expires_at <= current:
            remove_analysis(db, analysis, code="ANALYSIS_EXPIRED")
            return None, None
        # Existing OpenAI consent does not authorize sending documents to Gemini.
        if analysis.policy_version != POLICY_VERSION:
            raise MatchError("CONSENT_RENEWAL_REQUIRED")
        return task, analysis

    def check_before_call():
        with session_factory.begin() as db:
            task, analysis = read_live(db)
        if analysis is None:
            raise LeaseLost()

    try:
        with session_factory.begin() as db:
            task, analysis = read_live(db)
            if analysis is None:
                return
            cv_text, jd_text = analysis.cv_text, analysis.jd_text
        result = run_match(cv_text, jd_text, llm or GeminiMatchLLM(), before_call=check_before_call)
        with session_factory.begin() as db:
            task, analysis = read_live(db)
            if analysis is None:
                return
            analysis.result = result.model_dump(mode="json")
            db.flush()
            check_lease(db, task, token)
            # Use wall clock after serialization / flush too, so expired data cannot complete.
            if analysis.expires_at <= now(db):
                remove_analysis(db, analysis, code="ANALYSIS_EXPIRED")
                return
            task.status, task.last_error = "completed", None
            task.result_ref = {"analysis_id": str(analysis.id)}
            release(task)
    except LeaseLost:
        logger.info("CV task ownership lost; result discarded")
    except Exception as exc:
        known = isinstance(exc, MatchError)
        code = exc.code if known else "MATCH_PROCESSING_ERROR"
        diagnostic = exc.diagnostics() if known else {"code": code}
        logger.warning("CV task failed: %s", exc if known else code)
        try:
            finish_failure(task_id, token, {**diagnostic, "message": "CV comparison could not be completed"},
                retryable=exc.retryable if known else True,
                retry_after=exc.retry_after if known else None, session_factory=session_factory)
        except LeaseLost:
            pass
        except Exception:
            # Avoid an exception chain reaching the generic worker logger with private SQL data.
            logger.warning("CV task failure could not be recorded; lease recovery will handle it")
