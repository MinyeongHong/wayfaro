"""Private, expiring CV match inputs; existing public and profile tables untouched."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("analysis_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_analysis_sessions_expires_at", "analysis_sessions", ["expires_at"])
    op.create_table("cv_match_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("analysis_sessions.id"), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("background_jobs.id"), nullable=False, unique=True),
        sa.Column("cv_text", sa.Text(), nullable=False),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("cv_hash", sa.String(64), nullable=False),
        sa.Column("jd_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_cv_match_analyses_session_id", "cv_match_analyses", ["session_id"])
    op.create_index("ix_cv_match_analyses_expires_at", "cv_match_analyses", ["expires_at"])


def downgrade():
    op.drop_table("cv_match_analyses")
    op.drop_table("analysis_sessions")
