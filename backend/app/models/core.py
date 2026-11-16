import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, Index, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


def uid():
    return uuid.uuid4()


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfileVersion(Base):
    __tablename__ = "profile_versions"
    __table_args__ = (UniqueConstraint("profile_id", "version_number"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_profiles.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobListing(Base):
    __tablename__ = "job_listings"
    __table_args__ = (
        UniqueConstraint("provider", "board_token", "external_job_id", name="uq_job_listings_ats_identity"),
        CheckConstraint("((provider IS NULL AND board_token IS NULL AND external_job_id IS NULL AND source_id IS NULL) OR (provider IS NOT NULL AND board_token IS NOT NULL AND external_job_id IS NOT NULL AND source_id IS NOT NULL))", name="ck_job_listings_ats_identity"),
        Index("ix_job_listings_created_id", "created_at", "id"),
        Index("ix_job_listings_source", "source_id"),
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_sources.id", name="fk_job_listings_source"))
    provider: Mapped[str | None] = mapped_column(Text)
    board_token: Mapped[str | None] = mapped_column(Text)
    external_job_id: Mapped[str | None] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    description_html: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    raw_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    raw_text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobExtraction(Base):
    __tablename__ = "job_extractions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_listings.id"))
    extraction_version: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobAnalysis(Base):
    __tablename__ = "job_analyses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_listings.id"))
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_extractions.id"))
    profile_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profile_versions.id"))
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    task_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    payload: Mapped[dict] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(100))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict | None] = mapped_column(JSONB)
    result_ref: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (UniqueConstraint("provider", "board_token", name="uq_job_sources_identity"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    provider: Mapped[str] = mapped_column(Text)
    board_token: Mapped[str] = mapped_column(Text)
    company_name: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceSyncRun(Base):
    __tablename__ = "source_sync_runs"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_number", name="uq_source_sync_runs_attempt"),
        Index("ix_source_sync_runs_source_started", "source_id", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_sources.id"))
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("background_jobs.id"))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    jobs_fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    jobs_rejected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")


class AnalysisSession(Base):
    """Anonymous capability owner; no CV content or recoverable credential."""
    __tablename__ = "analysis_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CVMatchAnalysis(Base):
    """Private, temporary, immutable inputs. No public JobListing is created."""
    __tablename__ = "cv_match_analyses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_sessions.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("background_jobs.id"), unique=True)
    cv_text: Mapped[str] = mapped_column(Text)
    jd_text: Mapped[str] = mapped_column(Text)
    cv_hash: Mapped[str] = mapped_column(String(64))
    jd_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(40))
    result: Mapped[dict | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
