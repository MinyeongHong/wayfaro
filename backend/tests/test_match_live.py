"""Optional Gemini provider check, synthetic data only. Never runs in the default suite."""
import os
import pytest
from app.config import settings
from app.services.matching.llm import GeminiMatchLLM
from app.services.matching.pipeline import run_match


def test_gemini_live_synthetic_smoke():
    if os.environ.get("RUN_GEMINI_SMOKE") != "1":
        pytest.skip("Real provider calls require RUN_GEMINI_SMOKE=1")
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value().strip() or not settings.gemini_model:
        pytest.skip("Set GEMINI_API_KEY and GEMINI_MODEL for the opt-in live test")
    result = run_match(
        "Developed Python web services and SQL queries for an internal reporting project.",
        "Required: experience developing Python web services. Preferred: experience with SQL queries.",
        GeminiMatchLLM())
    assert result.requirements
    assert result.score is None and result.work_eligibility == "NOT_ASSESSED"
    assert all(item.status in ("MATCHED", "UNVERIFIED") for item in result.assessments)
