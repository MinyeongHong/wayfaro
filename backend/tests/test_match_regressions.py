"""Generation-only schema simplification and conservative exact-quote recovery."""
import copy
import json

import httpx
import pytest
from pydantic import Field, SecretStr, ValidationError

from app.config import settings
from app.services.matching.llm import GeminiMatchLLM, MatchError, _gemini_schema
from app.services.matching.pipeline import run_match, verify_evidence
from app.services.matching.schemas import Comparison, Evidence, Extraction, StrictModel
from test_match_engine import CV, JD, MockLLM, comparison_data, extraction_data, mock_response, span


@pytest.mark.parametrize("original,quote", [
    ("🚀 café\r\nPython services in production.", "Python services"),
    ("Intro.\r\nA unique experience.\r\nEnd.", "A unique experience."),
    ("경험: 🧭 파이썬 서비스를 개발했습니다.", "파이썬 서비스를 개발했습니다."),
    ("Prefix cafe\u0301 experience suffix", "cafe\u0301 experience"),
])
@pytest.mark.parametrize("offset", [(0, 1), (1000, 1001), (5, 2)])
def test_unique_exact_quote_recovers_to_python_codepoints(original, quote, offset):
    evidence = Evidence(start=offset[0], end=offset[1], quote=quote)
    unchanged = original
    verify_evidence([evidence], original)
    expected_start = original.index(quote)
    assert evidence.start == expected_start
    assert evidence.end == expected_start + len(quote)
    assert original[evidence.start:evidence.end] == evidence.quote == quote
    assert original == unchanged


@pytest.mark.parametrize("original,quote", [
    ("Python services for a team", "Invented Python leadership"),
    ("Python services", "python services"),
    ("Python  services", "Python services"),
    ("Line one\r\nLine two", "Line one\nLine two"),
    ("cafe\u0301", "café"),
    ("café", "cafe\u0301"),
    ("Python services; Python services", "Python services"),
    ("aaaa", "aa"),  # Overlapping matches are ambiguous too.
])
def test_missing_modified_or_ambiguous_quote_is_rejected_without_mutation(original, quote):
    evidence = Evidence(start=100, end=101, quote=quote)
    before = evidence.model_dump()
    with pytest.raises(MatchError, match="EVIDENCE_MISMATCH"):
        verify_evidence([evidence], original)
    assert evidence.model_dump() == before


@pytest.mark.parametrize("original,quote,start", [
    ("Python services; Python services", "Python services", 0),
    ("Python services; Python services", "Python services", 17),
    ("aaaa", "aa", 1),
])
def test_repeated_quote_is_allowed_when_original_offsets_are_exact(original, quote, start):
    evidence = Evidence(start=start, end=start + len(quote), quote=quote)
    before = evidence.model_dump()
    verify_evidence([evidence], original)
    assert evidence.model_dump() == before
    assert original[evidence.start:evidence.end] == quote


@pytest.mark.parametrize("stage", ["extraction", "comparison"])
def test_pipeline_returns_recovered_offsets_but_never_changes_quotes(stage):
    extraction, comparison = extraction_data(), comparison_data()
    spans = extraction["requirements"][0]["jd_evidence"] if stage == "extraction" else comparison["assessments"][0]["cv_evidence"]
    quote = spans[0]["quote"]
    spans[0].update(start=1000, end=1001)
    result = run_match(CV, JD, MockLLM(extraction, comparison))
    evidence = result.requirements[0].jd_evidence[0] if stage == "extraction" else result.assessments[0].cv_evidence[0]
    original = JD if stage == "extraction" else CV
    assert evidence.quote == quote
    assert original[evidence.start:evidence.end] == quote


@pytest.mark.parametrize("data", [
    {"start": -1, "end": 2, "quote": "Python"},
    {"start": 0, "end": 0, "quote": "Python"},
    {"start": 0, "end": 1, "quote": ""},
    {"start": "0", "end": 1, "quote": "Python"},
    {"start": 0, "end": 1, "quote": "Python", "invented": "field"},
])
def test_evidence_pydantic_validation_is_not_bypassed(data):
    with pytest.raises(ValidationError):
        Evidence.model_validate(data)


@pytest.mark.parametrize("schema", [Extraction, Comparison])
def test_generation_transform_does_not_mutate_local_schema(schema):
    local = schema.model_json_schema()
    before = copy.deepcopy(local)
    generated = _gemini_schema(schema)
    def compare(original, actual):
        if isinstance(original, dict):
            assert set(actual) == set(original) - {"maxItems"}
            for key in original.keys() - {"maxItems"}:
                compare(original[key], actual[key])
        elif isinstance(original, list):
            assert len(actual) == len(original)
            for old, new in zip(original, actual):
                compare(old, new)
        else:
            assert original == actual
    compare(local, generated)
    generated["properties"].clear()
    assert local == before and schema.model_json_schema() == before


def test_transformation_preserves_data_property_named_max_items():
    class NamedProperty(StrictModel):
        maxItems: int
        values: list[int] = Field(max_length=2)
    generated = _gemini_schema(NamedProperty)
    assert generated["properties"]["maxItems"] == NamedProperty.model_json_schema()["properties"]["maxItems"]
    assert "maxItems" in generated["required"]
    assert "maxItems" not in generated["properties"]["values"]


@pytest.mark.parametrize("schema,payload,error_location", [
    (Extraction, {**extraction_data(), "requirements": [extraction_data()["requirements"][0]] * 61}, ("requirements",)),
    (Extraction, {**extraction_data(), "excluded_eligibility_evidence": [span(JD, "SQL")] * 31}, ("excluded_eligibility_evidence",)),
    (Extraction, {"requirements": [{**extraction_data()["requirements"][0], "jd_evidence": [span(JD, "SQL")] * 6}], "excluded_eligibility_evidence": []}, ("requirements", 0, "jd_evidence")),
    (Comparison, {"assessments": [comparison_data()["assessments"][0]] * 61}, ("assessments",)),
    (Comparison, {"assessments": [{**comparison_data()["assessments"][0], "cv_evidence": [span(CV, "Built Python services")] * 9}]}, ("assessments", 0, "cv_evidence")),
])
def test_local_array_limits_reject_oversized_model_output(monkeypatch, schema, payload, error_location):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("mock-key"))
    monkeypatch.setattr(settings, "gemini_model", "mock-model")
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(payload)
    assert any(error["loc"] == error_location and error["type"] == "too_long" for error in caught.value.errors())
    def handler(request):
        generated = json.loads(request.content)["generationConfig"]["responseJsonSchema"]
        assert "maxItems" not in generated["properties"][error_location[0]]
        return httpx.Response(200, json=mock_response(payload))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MatchError, match="LLM_INVALID_OUTPUT"):
            GeminiMatchLLM(client).generate(schema, "instruction", {})


def test_schema_transform_preserves_literal_defaults_and_custom_annotations():
    original = {
        "type": "object", "properties": {"maxItems": {"type": "integer"}},
        "required": ["maxItems"], "dependentRequired": {"maxItems": ["other"]},
        "default": {"maxItems": 7}, "examples": [{"maxItems": 8}],
        "enum": [{"maxItems": 9}], "const": {"maxItems": 10},
        "x-metadata": {"maxItems": 11},
        "$defs": {"maxItems": {"type": "array", "minItems": 1, "maxItems": 2}},
        "anyOf": [{"type": "array", "maxItems": 3}, {"type": "null"}],
    }
    before = copy.deepcopy(original)
    class SharedSchema:
        @staticmethod
        def model_json_schema():
            return original
    expected = copy.deepcopy(original)
    del expected["$defs"]["maxItems"]["maxItems"]
    del expected["anyOf"][0]["maxItems"]
    assert _gemini_schema(SharedSchema) == expected
    assert original == before
