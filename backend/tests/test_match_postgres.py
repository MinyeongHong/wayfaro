"""Live PostgreSQL with mocked LLM; separate from optional paid provider smoke test."""
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from app.api.dependencies import get_db
from app.config import settings
from app.main import app
from app.models.core import AnalysisSession, BackgroundJob, CVMatchAnalysis
from app.services.matching.llm import MatchError
from app.services.matching.storage import cleanup_expired, now
from app.workers import runner
from test_match_engine import CV, JD, MockLLM

BODY = {"cv_text": CV, "jd_text": JD, "consent": True, "policy_version": "cv-match-gemini-1"}


@pytest.fixture
def private_client(sessions, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("mock-key"))
    monkeypatch.setattr(settings, "gemini_model", "mock-model")
    monkeypatch.setattr(settings, "cv_match_cookie_secure", False)
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def create(client):
    headers = {}
    csrf = client.cookies.get("wayfaro_cv_csrf")
    if csrf:
        headers["X-CSRF-Token"] = csrf
    response = client.post("/api/v1/analyses", json=BODY, headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


def process(sessions, llm=None):
    item = runner.claim_task(sessions)
    assert item is not None
    runner.process_task(*item, session_factory=sessions, match_llm=llm or MockLLM())
    return item


def test_private_end_to_end(private_client, sessions):
    created = create(private_client)
    assert private_client.get(created["status_url"]).json()["status"] == "pending"
    with sessions() as db:
        task = db.get(BackgroundJob, uuid.UUID(created["task_id"]))
        assert task.payload == {"analysis_id": created["analysis_id"]}
        assert set(CVMatchAnalysis.metadata.tables) == {"background_jobs", "analysis_sessions", "cv_match_analyses"}
    process(sessions)
    body = private_client.get(created["status_url"]).json()
    assert body["status"] == "completed" and body["result"]["score"] is None
    assert body["result"]["assessments"][1]["status"] == "UNVERIFIED"
    task_view = private_client.get(f'/api/v1/tasks/{created["task_id"]}')
    assert task_view.status_code == 200 and task_view.headers["cache-control"] == "no-store"
    with TestClient(app) as other:
        assert other.get(created["status_url"]).status_code == 404
        assert other.get(f'/api/v1/tasks/{created["task_id"]}').status_code == 404
        assert other.delete(created["status_url"]).status_code == 404
    with sessions() as db:
        owner = db.scalar(select(AnalysisSession))
        assert len(owner.token_hash) == len(owner.csrf_hash) == 64
        assert owner.token_hash != private_client.cookies.get("wayfaro_cv_session")


def test_csrf_origin_consent_and_provider_guard(private_client, monkeypatch):
    created = create(private_client)
    assert private_client.post("/api/v1/analyses", json=BODY).status_code == 403
    assert private_client.delete(created["status_url"]).status_code == 403
    headers = {"X-CSRF-Token": created["csrf_token"], "Origin": "https://untrusted.example"}
    assert private_client.post("/api/v1/analyses", json=BODY, headers=headers).status_code == 403
    assert private_client.delete(created["status_url"], headers=headers).status_code == 403
    assert private_client.post("/api/v1/analyses", json={**BODY, "consent": False}).status_code == 422
    monkeypatch.setattr(settings, "gemini_api_key", None)
    assert private_client.post("/api/v1/analyses", json=BODY).status_code == 503


def test_delete_cancels_pending_and_hides_task(private_client, sessions):
    created = create(private_client)
    assert private_client.delete(created["status_url"], headers={"X-CSRF-Token": created["csrf_token"]}).status_code == 204
    assert private_client.get(created["status_url"]).status_code == 404
    assert private_client.get(f'/api/v1/tasks/{created["task_id"]}').status_code == 404
    assert runner.claim_task(sessions) is None
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CVMatchAnalysis)) == 0
        task = db.get(BackgroundJob, uuid.UUID(created["task_id"]))
        assert task.payload == {} and task.status == "failed"


def test_delete_while_running_does_not_resurrect(private_client, sessions):
    created = create(private_client)
    class Deleting(MockLLM):
        def generate(self, schema, instruction, document):
            response = super().generate(schema, instruction, document)
            if len(self.calls) == 1:
                assert private_client.delete(created["status_url"], headers={"X-CSRF-Token": created["csrf_token"]}).status_code == 204
            return response
    llm = Deleting()
    process(sessions, llm)
    assert llm.calls == ["Extraction"]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CVMatchAnalysis)) == 0
        assert db.get(BackgroundJob, uuid.UUID(created["task_id"])).status == "failed"


def test_expired_inputs_are_hidden_and_physically_deleted(private_client, sessions):
    created = create(private_client)
    with sessions.begin() as db:
        db.get(CVMatchAnalysis, uuid.UUID(created["analysis_id"])).expires_at = now(db) - timedelta(seconds=1)
    assert private_client.get(created["status_url"]).status_code == 404
    assert cleanup_expired(sessions) == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CVMatchAnalysis)) == 0
        assert db.get(BackgroundJob, uuid.UUID(created["task_id"])).last_error["code"] == "ANALYSIS_EXPIRED"


def test_expiry_after_provider_call_discards_result(private_client, sessions):
    created = create(private_client)
    class Expiring(MockLLM):
        def generate(self, schema, instruction, document):
            result = super().generate(schema, instruction, document)
            if len(self.calls) == 2:
                with sessions.begin() as db:
                    db.get(CVMatchAnalysis, uuid.UUID(created["analysis_id"])).expires_at = now(db) - timedelta(seconds=1)
            return result
    process(sessions, Expiring())
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CVMatchAnalysis)) == 0
        assert db.get(BackgroundJob, uuid.UUID(created["task_id"])).status == "failed"


def test_retry_after_and_final_failure_no_private_logs(private_client, sessions, caplog):
    created = create(private_client)
    class Failing(MockLLM):
        def generate(self, *args):
            raise MatchError("LLM_HTTP_ERROR", retryable=True, retry_after=120)
    for attempt in range(1, 4):
        process(sessions, Failing())
        with sessions.begin() as db:
            task = db.get(BackgroundJob, uuid.UUID(created["task_id"]))
            assert task.attempts == attempt
            assert task.status == ("pending" if attempt < 3 else "failed")
            if attempt < 3:
                assert (task.run_after - now(db)).total_seconds() > 110
                task.run_after = now(db) - timedelta(seconds=1)
    assert CV not in caplog.text and JD not in caplog.text


def test_expired_lease_never_commits(private_client, sessions):
    created = create(private_client)
    class ExpiringLease(MockLLM):
        def generate(self, *args):
            result = super().generate(*args)
            with sessions.begin() as db:
                db.get(BackgroundJob, uuid.UUID(created["task_id"])).lease_expires_at = now(db) - timedelta(seconds=1)
            return result
    process(sessions, ExpiringLease())
    with sessions() as db:
        assert db.get(CVMatchAnalysis, uuid.UUID(created["analysis_id"])).result is None
        assert db.get(BackgroundJob, uuid.UUID(created["task_id"])).status == "processing"


def test_session_limits_are_atomic(private_client, sessions, monkeypatch):
    monkeypatch.setattr(settings, "cv_match_session_limit", 1)
    first = create(private_client)
    headers = {"X-CSRF-Token": first["csrf_token"]}
    def submit(_):
        with TestClient(app) as client:
            client.cookies.update(private_client.cookies)
            return client.post("/api/v1/analyses", json=BODY, headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(submit, range(2))) == [429, 429]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CVMatchAnalysis)) == 1


def test_session_expiry_revokes_reads_and_worker(private_client, sessions):
    created = create(private_client)
    with sessions.begin() as db:
        owner = db.scalar(select(AnalysisSession))
        owner.expires_at = now(db) - timedelta(seconds=1)
    assert private_client.get(created["status_url"]).status_code == 404
    assert private_client.get(f'/api/v1/tasks/{created["task_id"]}').status_code == 404
    process(sessions)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(CVMatchAnalysis)) == 0
    cleanup_expired(sessions)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(AnalysisSession)) == 0


def test_retry_then_success(private_client, sessions):
    created = create(private_client)
    class Once(MockLLM):
        failed = False
        def generate(self, *args):
            if not self.failed:
                self.failed = True
                raise MatchError("LLM_NETWORK_ERROR", retryable=True)
            return super().generate(*args)
    llm = Once()
    process(sessions, llm)
    with sessions.begin() as db:
        task = db.get(BackgroundJob, uuid.UUID(created["task_id"]))
        task.run_after = now(db) - timedelta(seconds=1)
    process(sessions, llm)
    body = private_client.get(created["status_url"]).json()
    assert body["status"] == "completed" and body["error"] is None


def test_global_daily_limit_survives_deletion(private_client, sessions, monkeypatch):
    monkeypatch.setattr(settings, "cv_match_global_daily_limit", 1)
    created = create(private_client)
    assert private_client.delete(created["status_url"], headers={"X-CSRF-Token": created["csrf_token"]}).status_code == 204
    with TestClient(app) as other:
        assert other.post("/api/v1/analyses", json=BODY).status_code == 429


def test_old_pending_consent_never_sends_documents_to_gemini(private_client, sessions):
    created = create(private_client)
    with sessions.begin() as db:
        db.get(CVMatchAnalysis, uuid.UUID(created["analysis_id"])).policy_version = "cv-match-1"
    llm = MockLLM()
    process(sessions, llm)
    assert llm.calls == []
    with sessions() as db:
        analysis = db.get(CVMatchAnalysis, uuid.UUID(created["analysis_id"]))
        task = db.get(BackgroundJob, analysis.task_id)
        assert task.status == "failed"
        assert task.last_error["code"] == "CONSENT_RENEWAL_REQUIRED"
        assert analysis.cv_text == CV and analysis.jd_text == JD


def test_old_completed_openai_analysis_can_be_read_without_rewriting(private_client, sessions):
    from app.services.matching.pipeline import run_match
    created = create(private_client)
    old_result = run_match(CV, JD, MockLLM()).model_dump(mode="json")
    old_result["provider"] = "openai"
    with sessions.begin() as db:
        analysis = db.get(CVMatchAnalysis, uuid.UUID(created["analysis_id"]))
        analysis.policy_version, analysis.result = "cv-match-1", old_result
        db.get(BackgroundJob, analysis.task_id).status = "completed"
    response = private_client.get(created["status_url"])
    assert response.status_code == 200
    assert response.json()["result"]["provider"] == "openai"


def test_http_diagnostics_reach_private_result_and_safe_worker_log(private_client, sessions, caplog):
    import httpx
    from app.services.matching.llm import GeminiMatchLLM
    from test_match_engine import extraction_data, mock_response
    created = create(private_client)
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=mock_response(extraction_data()))
        return httpx.Response(400, text=f"{CV} {JD} mock-key PRIVATE_PROVIDER_BODY")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        process(sessions, GeminiMatchLLM(client))
    response = private_client.get(created["status_url"])
    assert response.status_code == 200
    error = response.json()["error"]
    assert response.json()["status"] == "failed"
    assert error["code"] == "LLM_HTTP_ERROR"
    assert error["http_status"] == "400" and error["error_type"] == "HTTP_BAD_REQUEST"
    assert error["stage"] == "comparison"
    assert "http_status=400" in caplog.text and "stage=comparison" in caplog.text
    for private in (CV, JD, "mock-key", "PRIVATE_PROVIDER_BODY"):
        assert private not in caplog.text and private not in response.text


def test_lease_expiring_during_result_flush_rolls_back(private_client, sessions):
    from sqlalchemy import event
    created = create(private_client)
    task_id = uuid.UUID(created['task_id'])
    analysis_id = uuid.UUID(created['analysis_id'])
    fired = []
    def expire_after_result_flush(db, context):
        if fired:
            return
        analyses = [obj for obj in db.identity_map.values()
                    if isinstance(obj, CVMatchAnalysis) and obj.result is not None]
        if analyses:
            fired.append(True)
            db.get(BackgroundJob, task_id).lease_expires_at = now(db) - timedelta(seconds=1)
    event.listen(sessions.class_, 'after_flush_postexec', expire_after_result_flush)
    try:
        process(sessions)
    finally:
        event.remove(sessions.class_, 'after_flush_postexec', expire_after_result_flush)
    assert fired
    with sessions() as db:
        assert db.get(CVMatchAnalysis, analysis_id).result is None
        assert db.get(BackgroundJob, task_id).status == 'processing'
