"""Versioned contracts. The first engine cannot assert a CV or skill gap."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

POLICY_VERSION = "cv-match-gemini-1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, strict=True)


class AnalysisCreate(StrictModel):
    cv_text: str = Field(min_length=30, max_length=40000, repr=False)
    jd_text: str = Field(min_length=30, max_length=40000, repr=False)
    consent: Literal[True]
    policy_version: Literal["cv-match-gemini-1"]

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Explicit boolean consent is required")
        return value

    @field_validator("cv_text", "jd_text")
    @classmethod
    def valid_document(cls, value):
        if len(value.strip()) < 30 or "\x00" in value:
            raise ValueError("Document must contain at least 30 non-padding characters and no NUL")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Document must be valid Unicode") from None
        return value  # Never normalize Unicode or line endings: offsets refer to this exact string.


class Evidence(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=8000)


class Requirement(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)
    importance: Literal["REQUIRED", "PREFERRED", "UNSPECIFIED"]
    jd_evidence: list[Evidence] = Field(min_length=1, max_length=5)


class Extraction(StrictModel):
    requirements: list[Requirement] = Field(max_length=60)
    excluded_eligibility_evidence: list[Evidence] = Field(max_length=30)


class Assessment(StrictModel):
    requirement_id: str
    status: Literal["MATCHED", "UNVERIFIED"]
    rationale: str = Field(min_length=1, max_length=2000)
    cv_evidence: list[Evidence] = Field(max_length=8)


class Comparison(StrictModel):
    assessments: list[Assessment] = Field(max_length=60)


class Suggestion(StrictModel):
    requirement_id: str
    kind: Literal["HIGHLIGHT_EXISTING_EVIDENCE", "ASK_CONFIRMATION"]
    text: str
    cv_evidence: list[Evidence]
    question: str | None


class MatchResult(StrictModel):
    schema_version: Literal["1"]
    requirements: list[Requirement]
    assessments: list[Assessment]
    excluded_eligibility_evidence: list[Evidence]
    cv_suggestions: list[Suggestion]
    matched_count: int
    unverified_count: int
    score: None
    work_eligibility: Literal["NOT_ASSESSED"]
    limitations: list[str]
    provider: Literal["openai", "gemini"]
    model: str
    prompt_version: Literal["1"]


class AnalysisAccepted(StrictModel):
    analysis_id: UUID
    task_id: UUID
    status: str
    status_url: str
    expires_at: datetime
    csrf_token: str


class AnalysisView(StrictModel):
    analysis_id: UUID
    task_id: UUID
    status: str
    expires_at: datetime
    result: MatchResult | None
    error: dict[str, str] | None
