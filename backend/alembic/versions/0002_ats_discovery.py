"""ATS source identity, posting data, and synchronization history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

IDENTITY_CHECK = "((provider IS NULL AND board_token IS NULL AND external_job_id IS NULL AND source_id IS NULL) OR (provider IS NOT NULL AND board_token IS NOT NULL AND external_job_id IS NOT NULL AND source_id IS NOT NULL))"
TEXT_FIELDS = ("provider", "board_token", "external_job_id", "company_name", "title", "location_text", "department", "description_html", "description_text")


def upgrade():
    op.create_table("job_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("board_token", sa.Text(), nullable=False),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "board_token", name="uq_job_sources_identity"))
    op.add_column("job_listings", sa.Column("source_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_job_listings_source", "job_listings", "job_sources", ["source_id"], ["id"])
    for field in TEXT_FIELDS:
        op.add_column("job_listings", sa.Column(field, sa.Text(), nullable=True))
    op.add_column("job_listings", sa.Column("raw_metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    for field in ("published_at", "source_updated_at"):
        op.add_column("job_listings", sa.Column(field, sa.DateTime(timezone=True), nullable=True))
    for field in ("ingested_at", "updated_at"):
        op.add_column("job_listings", sa.Column(field, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    # Existing records were ingested when created, not when this migration runs.
    op.execute("UPDATE job_listings SET ingested_at = created_at, updated_at = created_at")
    op.create_unique_constraint("uq_job_listings_ats_identity", "job_listings", ["provider", "board_token", "external_job_id"])
    op.create_check_constraint("ck_job_listings_ats_identity", "job_listings", IDENTITY_CHECK)
    op.create_index("ix_job_listings_created_id", "job_listings", ["created_at", "id"])
    op.create_index("ix_job_listings_source", "job_listings", ["source_id"])
    op.create_table("source_sync_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("job_sources.id"), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("background_jobs.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *[sa.Column(name, sa.Integer(), nullable=False, server_default="0") for name in ("jobs_fetched", "jobs_created", "jobs_updated", "jobs_rejected")],
        sa.Column("errors", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_source_sync_runs_attempt"))
    op.create_index("ix_source_sync_runs_source_started", "source_sync_runs", ["source_id", "started_at"])


def downgrade():
    op.drop_table("source_sync_runs")
    op.drop_index("ix_job_listings_source", table_name="job_listings")
    op.drop_index("ix_job_listings_created_id", table_name="job_listings")
    op.drop_constraint("ck_job_listings_ats_identity", "job_listings", type_="check")
    op.drop_constraint("uq_job_listings_ats_identity", "job_listings", type_="unique")
    op.drop_constraint("fk_job_listings_source", "job_listings", type_="foreignkey")
    for name in (*TEXT_FIELDS, "source_id", "raw_metadata", "published_at", "source_updated_at", "ingested_at", "updated_at"):
        op.drop_column("job_listings", name)
    op.drop_table("job_sources")
