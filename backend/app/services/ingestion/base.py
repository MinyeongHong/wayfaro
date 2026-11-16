"""Provider-independent types; connectors do not access the database."""
from datetime import datetime, timezone
from typing import Any, Protocol
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    provider: str = Field(min_length=1)
    board_token: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    company_name: str = Field(min_length=1)
    is_active: bool = True


class NormalizedJob(BaseModel):
    provider: str = Field(min_length=1)
    board_token: str = Field(min_length=1)
    external_job_id: str = Field(min_length=1)
    source_url: str | None = None
    company_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    location_text: str | None = None
    department: str | None = None
    description_html: str | None = None
    description_text: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at", "updated_at")
    @classmethod
    def aware_dates(cls, value):
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)


class RecordError(BaseModel):
    index: int
    external_job_id: str | None = None
    message: str
    raw_record: Any = None


class FetchResult(BaseModel):
    jobs_fetched: int
    jobs: list[NormalizedJob] = Field(default_factory=list)
    errors: list[RecordError] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 retry_after_seconds: float | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class Connector(Protocol):
    def fetch(self, source: SourceConfig) -> FetchResult: ...
