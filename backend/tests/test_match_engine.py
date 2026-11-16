"""Deterministic mock LLM / mocked HTTP tests; never call external APIs."""
import copy
import json
import logging

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.services.matching.llm import MatchError, GeminiMatchLLM
from app.services.matching.pipeline import run_match
from app.services.matching.schemas import AnalysisCreate, Comparison, Extraction, MatchResult

CV = "Built Python services for a small team.\r\nWorked with café 🚀 projects."
JD = "Required: Python services. Preferred: SQL. Work authorization required."


def span(text, quote):
    start = text.index(quote)
    return {"start": start, "end": start + len(quote), "quote": quote}



def assert_generation_schema(local, transmitted):
    """Independent contract: maxItems alone may differ, at any schema depth."""
    if isinstance(local, dict):
        assert isinstance(transmitted, dict)
        assert set(transmitted) == set(local) - {"maxItems"}
        for key, value in local.items():
            if key != "maxItems":
                assert_generation_schema(value, transmitted[key])
    elif isinstance(local, list):
        assert isinstance(transmitted, list) and len(transmitted) == len(local)
        for expected, actual in zip(local, transmitted):
            assert_generation_schema(expected, actual)
    else:
        assert transmitted == local

def extraction_data():
    return {"requirements": [
        {"id": "r1", "text": "Python services", "importance": "REQUIRED", "jd_evidence": [span(JD, "Python services")]},
        {"id": "r2", "text": "SQL", "importance": "PREFERRED", "jd_evidence": [span(JD, "SQL")]}],
        "excluded_eligibility_evidence": [span(JD, "Work authorization required.")]}


def comparison_data():
    return {"assessments": [
        {"requirement_id": "r1", "status": "MATCHED", "rationale": "Direct CV evidence", "cv_evidence": [span(CV, "Built Python services")]},
        {"requirement_id": "r2", "status": "UNVERIFIED", "rationale": "Not mentioned; experience remains unknown", "cv_evidence": []}]}


class MockLLM:
    model = "mock-model"

    def __init__(self, extraction=None, comparison=None):
        self.extraction = extraction if extraction is not None else extraction_data()
        self.comparison = comparison if comparison is not None else comparison_data()
        self.calls = []

    def generate(self, schema, instruction, document):
        self.calls.append(schema.__name__)
        return schema.model_validate(self.extraction if schema is Extraction else self.comparison)


def test_grounded_matching_and_no_gap_or_score():
    llm = MockLLM()
    result = run_match(CV, JD, llm)
    assert llm.calls == ["Extraction", "Comparison"]
    assert (result.matched_count, result.unverified_count) == (1, 1)
    assert result.provider == "gemini"
    assert result.score is None and result.work_eligibility == "NOT_ASSESSED"
    assert [item.kind for item in result.cv_suggestions] == ["HIGHLIGHT_EXISTING_EVIDENCE", "ASK_CONFIRMATION"]
    assert result.cv_suggestions[1].question
    assert all(item.status in ("MATCHED", "UNVERIFIED") for item in result.assessments)
    assert MatchResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("status", ["CV_GAP", "SKILL_GAP", "INELIGIBLE"])
def test_forbidden_classifications(status):
    data = comparison_data()
    data["assessments"][1]["status"] = status
    with pytest.raises(ValidationError):
        run_match(CV, JD, MockLLM(comparison=data))


@pytest.mark.parametrize("change", ["quote", "coverage", "duplicate", "no_evidence"])
def test_business_rules_reject_invalid_evidence(change):
    data = comparison_data()
    if change == "quote":
        data["assessments"][0]["cv_evidence"][0]["quote"] = "Invented experience"
    elif change == "coverage":
        data["assessments"].pop()
    elif change == "duplicate":
        data["assessments"][1]["requirement_id"] = "r1"
    else:
        data["assessments"][0]["cv_evidence"] = []
    with pytest.raises(MatchError):
        run_match(CV, JD, MockLLM(comparison=data))



def test_business_rules_recover_unique_exact_quote_offset():
    data = comparison_data()
    expected = copy.deepcopy(data["assessments"][0]["cv_evidence"][0])
    data["assessments"][0]["cv_evidence"][0]["end"] += 1
    result = run_match(CV, JD, MockLLM(comparison=data))
    recovered = result.assessments[0].cv_evidence[0]
    assert recovered.model_dump() == expected
    assert CV[recovered.start:recovered.end] == recovered.quote

def test_unicode_offsets_are_codepoints_not_utf16():
    data = comparison_data()
    data["assessments"][0]["cv_evidence"] = [span(CV, "🚀 projects")]
    # Structural verification is distinct from semantic accuracy.
    assert run_match(CV, JD, MockLLM(comparison=data)).matched_count == 1
    data["assessments"][0]["cv_evidence"][0]["start"] += 1
    recovered = run_match(CV, JD, MockLLM(comparison=data)).assessments[0].cv_evidence[0]
    assert recovered.start == CV.index("🚀 projects")
    assert recovered.end == recovered.start + len("🚀 projects")
    assert CV[recovered.start:recovered.end] == recovered.quote == "🚀 projects"


def test_invalid_extraction_and_duplicate_requirements():
    for kind in ("quote", "duplicate"):
        data = extraction_data()
        if kind == "quote":
            data["requirements"][0]["jd_evidence"][0]["quote"] = "Invented requirement"
        else:
            data["requirements"][1]["id"] = "r1"
        llm = MockLLM(extraction=data)
        with pytest.raises(MatchError):
            run_match(CV, JD, llm)
        assert llm.calls == ["Extraction"]


def test_no_requirements_skips_comparison_and_calls_guard():
    llm = MockLLM(extraction={"requirements": [], "excluded_eligibility_evidence": []})
    guards = []
    result = run_match(CV, JD, llm, before_call=lambda: guards.append(True))
    assert result.assessments == [] and result.score is None
    assert llm.calls == ["Extraction"] and guards == [True]


def test_output_schema_is_strict_and_has_no_gap_classification():
    for schema in (Extraction, Comparison):
        data = schema.model_json_schema()
        assert data["additionalProperties"] is False
        assert set(data["required"]) == set(data["properties"])
    enum = Comparison.model_json_schema()["$defs"]["Assessment"]["properties"]["status"]["enum"]
    assert enum == ["MATCHED", "UNVERIFIED"]


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("mock-key"))
    monkeypatch.setattr(settings, "gemini_model", "mock-model")


def mock_response(payload):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]}


def test_real_adapter_request_contract_with_mock_transport(configured):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/models/mock-model:generateContent"
        assert not request.url.query
        assert "store" not in body and "tools" not in body
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert_generation_schema(Extraction.model_json_schema(), body["generationConfig"]["responseJsonSchema"])
        assert "candidateCount" not in body["generationConfig"]
        assert body["systemInstruction"]["parts"] == [{"text": "instruction"}]
        assert json.loads(body["contents"][0]["parts"][0]["text"]) == {"jd_text": JD}
        assert request.headers["x-goog-api-key"] == "mock-key"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json=mock_response(extraction_data()))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        parsed = GeminiMatchLLM(client).generate(Extraction, "instruction", {"jd_text": JD})
    assert parsed.requirements[0].id == "r1" and len(seen) == 1


@pytest.mark.parametrize("status,retryable", [(401, False), (400, False), (429, True), (503, True)])
def test_adapter_errors_do_not_expose_provider_body(configured, status, retryable):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            status, text=CV, headers={"Retry-After": "120"}))) as client:
        with pytest.raises(MatchError) as captured:
            GeminiMatchLLM(client).generate(Extraction, "instruction", {})
    assert captured.value.retryable is retryable
    assert captured.value.retry_after == 120
    assert CV not in str(captured.value)


@pytest.mark.parametrize("body,code", [
    ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "LLM_INCOMPLETE"),
    ({"promptFeedback": {"blockReason": "SAFETY"}}, "LLM_REFUSED"),
    ({"candidates": [{"finishReason": "SAFETY"}]}, "LLM_REFUSED"),
    ({"candidates": [{"finishReason": "RECITATION"}]}, "LLM_REFUSED"),
    ({"candidates": []}, "LLM_INVALID_OUTPUT"),
    ({"candidates": [{"finishReason": "OTHER"}]}, "LLM_INVALID_OUTPUT"),
    ({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"functionCall": {}}]}}]}, "LLM_INVALID_OUTPUT"),
    ({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not json"}]}}]}, "LLM_INVALID_OUTPUT"),
    (mock_response({"invalid": True}), "LLM_INVALID_OUTPUT")])
def test_adapter_invalid_response(configured, body, code):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
        with pytest.raises(MatchError, match=code):
            GeminiMatchLLM(client).generate(Extraction, "instruction", {})


def test_network_failure_is_sanitized(configured):
    def handler(request):
        raise httpx.ReadTimeout(CV, request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError, match="LLM_READ_TIMEOUT"):
            GeminiMatchLLM(client).generate(Extraction, "instruction", {})


def test_policy_and_validation_never_echo_input_or_log(caplog):
    with caplog.at_level(logging.INFO), TestClient(app) as client:
        policy = client.get("/api/v1/analyses/policy")
        assert policy.status_code == 200
        assert policy.json()["policy_version"] == "cv-match-gemini-1"
        assert policy.headers["cache-control"] == "no-store"
        response = client.post("/api/v1/analyses", json={"cv_text": CV, "jd_text": "PRIVATE_SENTINEL", "consent": False, "policy_version": "cv-match-gemini-1"})
        assert response.status_code == 422
        assert CV not in response.text and "PRIVATE_SENTINEL" not in response.text
        oversized = client.post("/api/v1/analyses", content="x" * 350001)
        assert oversized.status_code == 413
    assert CV not in caplog.text and JD not in caplog.text


def test_input_snapshot_preserves_exact_text():
    body = AnalysisCreate(cv_text=CV, jd_text=JD, consent=True, policy_version="cv-match-gemini-1")
    assert body.cv_text == CV and "\r\n" in body.cv_text
    with pytest.raises(ValidationError):
        AnalysisCreate(cv_text=" " * 31, jd_text=JD, consent=True, policy_version="cv-match-gemini-1")


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_consent_must_be_explicit_boolean(value):
    with pytest.raises(ValidationError):
        AnalysisCreate(cv_text=CV, jd_text=JD, consent=value, policy_version="cv-match-gemini-1")


def test_malformed_json_and_unknown_fields_do_not_echo_private_values():
    with TestClient(app) as client:
        response = client.post("/api/v1/analyses", content='{"cv_text":"PRIVATE_DOCUMENT",', headers={"Content-Type": "application/json"})
        assert response.status_code == 422 and "PRIVATE_DOCUMENT" not in response.text
        response = client.post("/api/v1/analyses", json={"PRIVATE_DOCUMENT": "value"})
        assert response.status_code == 422 and "PRIVATE_DOCUMENT" not in response.text


def test_private_internal_error_is_sanitized(configured, monkeypatch, caplog):
    from app.api.routes import get_db
    import app.api.analysis as api
    def no_db():
        yield None
    def broken(*args):
        raise RuntimeError("PRIVATE_DOCUMENT_WITH_CV")
    monkeypatch.setattr(api, "create_request", broken)
    app.dependency_overrides[get_db] = no_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/analyses", json={"cv_text": CV, "jd_text": JD, "consent": True, "policy_version": "cv-match-gemini-1"})
        assert response.status_code == 500
        assert "PRIVATE_DOCUMENT" not in response.text and "PRIVATE_DOCUMENT" not in caplog.text
    finally:
        app.dependency_overrides.clear()


def test_analysis_contract_is_exposed_in_openapi():
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert set(schema["paths"]["/api/v1/analyses"]) == {"post"}
    assert {"get", "delete"} <= set(schema["paths"]["/api/v1/analyses/{analysis_id}"])
    assert schema["components"]["schemas"]["Assessment"]["properties"]["status"]["enum"] == ["MATCHED", "UNVERIFIED"]


def test_thinking_parts_are_not_parsed_or_persisted(configured):
    data = mock_response(extraction_data())
    data["candidates"][0]["content"]["parts"].insert(0, {"thought": True, "text": "PRIVATE_THINKING"})
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data))) as client:
        parsed = GeminiMatchLLM(client).generate(Extraction, "instruction", {})
    assert "PRIVATE_THINKING" not in parsed.model_dump_json()


@pytest.mark.parametrize("model", ["../bad", "mock-model?key=secret", "https://untrusted.example", "mock/model"])
def test_model_cannot_inject_url_components(configured, monkeypatch, model):
    monkeypatch.setattr(settings, "gemini_model", model)
    def handler(request):
        pytest.fail("Invalid models must not trigger HTTP calls")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError, match="LLM_INVALID_MODEL"):
            GeminiMatchLLM(client).generate(Extraction, "instruction", {})


def test_models_prefix_is_normalized(configured, monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "models/mock-model")
    assert GeminiMatchLLM().model == "mock-model"


def test_legacy_results_remain_readable_but_legacy_consent_is_rejected():
    result = run_match(CV, JD, MockLLM()).model_dump(mode="json")
    result["provider"] = "openai"
    assert MatchResult.model_validate(result).provider == "openai"
    with pytest.raises(ValidationError):
        AnalysisCreate(cv_text=CV, jd_text=JD, consent=True, policy_version="cv-match-1")


def test_key_and_documents_are_absent_from_adapter_logs(configured, caplog):
    with caplog.at_level(logging.INFO):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=mock_response(extraction_data())))) as client:
            GeminiMatchLLM(client).generate(Extraction, "instruction", {"jd_text": JD})
    assert "mock-key" not in caplog.text and CV not in caplog.text and JD not in caplog.text


def test_missing_gemini_key_does_not_fall_back_to_other_provider(configured, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-other-provider-key")
    def handler(request):
        pytest.fail("Missing Gemini credentials must not trigger any provider call")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError, match="LLM_NOT_CONFIGURED"):
            GeminiMatchLLM(client).generate(Extraction, "instruction", {})


def test_policy_identifies_gemini_and_has_no_openai_storage_claim():
    with TestClient(app) as client:
        policy = client.get("/api/v1/analyses/policy").json()
    assert policy["provider"] == "Gemini"
    assert policy["provider_policy_url"] == "https://ai.google.dev/gemini-api/terms"
    assert "store=false" not in policy["provider_retention_notice"]


def test_two_stage_pipeline_through_gemini_mock_http(configured):
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        document = json.loads(body["contents"][0]["parts"][0]["text"])
        if len(requests) == 1:
            assert document == {"jd_text": JD}
            payload = extraction_data()
        else:
            assert document["cv_text"] == CV and len(document["requirements"]) == 2
            assert_generation_schema(Comparison.model_json_schema(), body["generationConfig"]["responseJsonSchema"])
            payload = comparison_data()
        return httpx.Response(200, json=mock_response(payload))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run_match(CV, JD, GeminiMatchLLM(client))
    assert len(requests) == 2 and result.provider == "gemini"
    assert result.score is None and result.work_eligibility == "NOT_ASSESSED"
    assert result.assessments[0].cv_evidence[0].quote == "Built Python services"


@pytest.mark.parametrize("status,error_type,retryable", [
    (400, "HTTP_BAD_REQUEST", False), (401, "HTTP_UNAUTHENTICATED", False),
    (403, "HTTP_PERMISSION_DENIED", False), (404, "HTTP_NOT_FOUND", False),
    (408, "HTTP_REQUEST_TIMEOUT", True), (429, "HTTP_RATE_LIMITED", True),
    (503, "HTTP_SERVER_ERROR", True), (307, "HTTP_REDIRECT", False),
    (418, "HTTP_OTHER_ERROR", False)])
def test_http_diagnostics_use_status_only(configured, caplog, status, error_type, retryable):
    class PrivateResponse(httpx.Response):
        def json(self, **kwargs):
            pytest.fail("HTTP errors must not parse provider response bodies")
    def handler(request):
        return PrivateResponse(status, content=f"{CV} {JD} mock-key Authorization PRIVATE_PROVIDER_BODY".encode(),
                               headers={"x-private-provider-header": "PRIVATE_HEADER"})
    with caplog.at_level(logging.INFO), httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError) as caught:
            GeminiMatchLLM(client).generate(Extraction, "instruction", {"jd_text": JD})
    error = caught.value
    assert error.http_status == status and error.retryable is retryable
    assert error.diagnostics() == {"code": "LLM_HTTP_ERROR", "http_status": str(status), "error_type": error_type}
    visible = str(error) + repr(error) + json.dumps(error.diagnostics()) + caplog.text
    for private in (CV, JD, "mock-key", "Authorization", "PRIVATE_PROVIDER_BODY", "PRIVATE_HEADER"):
        assert private not in visible


@pytest.mark.parametrize("exception,code,error_type", [
    (httpx.ReadTimeout, "LLM_READ_TIMEOUT", "READ_TIMEOUT"),
    (httpx.ConnectTimeout, "LLM_TIMEOUT", "TIMEOUT"),
    (httpx.ConnectError, "LLM_NETWORK_ERROR", "NETWORK_ERROR")])
def test_timeout_is_distinct_from_http_error(configured, exception, code, error_type):
    def handler(request):
        raise exception(f"mock-key {CV} {JD}", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError) as caught:
            GeminiMatchLLM(client).generate(Extraction, "instruction", {})
    assert caught.value.http_status is None and caught.value.retryable
    assert caught.value.diagnostics() == {"code": code, "error_type": error_type}
    assert CV not in str(caught.value) and "mock-key" not in str(caught.value)


@pytest.mark.parametrize("stage", ["extraction", "comparison"])
@pytest.mark.parametrize("failure", ["http", "read_timeout"])
def test_pipeline_reports_safe_failure_stage(configured, stage, failure):
    requests = []
    def handler(request):
        requests.append(request)
        if stage == "comparison" and len(requests) == 1:
            return httpx.Response(200, json=mock_response(extraction_data()))
        if failure == "read_timeout":
            raise httpx.ReadTimeout(f"{CV} {JD} mock-key", request=request)
        return httpx.Response(400, text=f"{CV} {JD} mock-key")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError) as caught:
            run_match(CV, JD, GeminiMatchLLM(client))
    diagnostic = caught.value.diagnostics()
    assert diagnostic["stage"] == stage
    assert len(requests) == (1 if stage == "extraction" else 2)
    if failure == "http":
        assert diagnostic["http_status"] == "400" and diagnostic["error_type"] == "HTTP_BAD_REQUEST"
    else:
        assert diagnostic["code"] == "LLM_READ_TIMEOUT" and "http_status" not in diagnostic
    assert f"stage={stage}" in str(caught.value)
    assert CV not in str(caught.value) and JD not in str(caught.value) and "mock-key" not in str(caught.value)


@pytest.mark.parametrize("stage", ["extraction", "comparison"])
def test_evidence_validation_failure_retains_stage(stage):
    extraction, comparison = extraction_data(), comparison_data()
    if stage == "extraction":
        extraction["requirements"][0]["jd_evidence"][0]["quote"] = "Invented quote"
    else:
        comparison["assessments"][0]["cv_evidence"][0]["quote"] = "Invented quote"
    with pytest.raises(MatchError) as caught:
        run_match(CV, JD, MockLLM(extraction=extraction, comparison=comparison))
    assert caught.value.code == "EVIDENCE_MISMATCH" and caught.value.retryable
    assert caught.value.diagnostics()["stage"] == stage


def test_gemini_31_request_omits_candidate_count_and_keeps_local_schema_bounds(configured, monkeypatch):
    monkeypatch.setattr(settings, "gemini_model", "gemini-3.1-flash-lite")
    expected = Extraction.model_json_schema()
    original = copy.deepcopy(expected)
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path.endswith('/models/gemini-3.1-flash-lite:generateContent')
        config = body["generationConfig"]
        assert "candidateCount" not in config
        assert_generation_schema(expected, config["responseJsonSchema"])
        assert "maxItems" not in config["responseJsonSchema"]["properties"]["requirements"]
        assert Extraction.model_json_schema() == original
        assert original["properties"]["requirements"]["maxItems"] == 60
        return httpx.Response(200, json=mock_response(extraction_data()))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert GeminiMatchLLM(client).generate(Extraction, "instruction", {"jd_text": JD}).requirements
