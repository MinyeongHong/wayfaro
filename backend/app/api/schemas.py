"""Public discovery contracts; absent evidence stays absent."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict

RemoteMention = Literal["PRESENT", "NOT_MENTIONED", "UNKNOWN"]
SortOrder = Literal["created_desc", "published_desc", "updated_desc"]
Origin = Literal["manual", "ats"]


class JobSummary(BaseModel):
    id: UUID
    title: str | None
    company_name: str | None
    location_text: str | None
    department: str | None
    origin: Origin
    source_id: UUID | None
    provider: str | None
    board_token: str | None
    external_job_id: str | None
    source_url: str | None
    remote_mention: RemoteMention
    created_at: datetime
    published_at: datetime | None
    ingested_at: datetime
    updated_at: datetime


class JobDetail(JobSummary):
    raw_text: str
    description_text: str | None
    source_updated_at: datetime | None


class SourceOption(BaseModel):
    id: UUID
    provider: str
    company_name: str
    board_token: str


class JobPage(BaseModel):
    items: list[JobSummary]
    page: int
    page_size: int
    total: int
    total_pages: int
    source_options: list[SourceOption]


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID


class SyncAccepted(BaseModel):
    task_id: UUID
    source_id: UUID
    status: str
    status_url: str
