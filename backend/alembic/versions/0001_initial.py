"""Original foundation schema, frozen independently of application models."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("user_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("active_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("job_listings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("background_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", JSONB(), nullable=True),
        sa.Column("result_ref", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("profile_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("user_profiles.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("profile_id", "version_number"))
    op.create_table("job_extractions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("job_listings.id"), nullable=False),
        sa.Column("extraction_version", sa.String(64), nullable=False),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("job_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("job_listings.id"), nullable=False),
        sa.Column("extraction_id", UUID(as_uuid=True), sa.ForeignKey("job_extractions.id"), nullable=False),
        sa.Column("profile_version_id", UUID(as_uuid=True), sa.ForeignKey("profile_versions.id"), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))


def downgrade():
    for table in ("job_analyses", "job_extractions", "profile_versions", "background_jobs", "job_listings", "user_profiles"):
        op.drop_table(table)
