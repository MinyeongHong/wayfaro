"""Use unique schemas only; never drop/reset an existing database or public schema."""
import importlib.util
import os
from pathlib import Path
import uuid
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from app.db.base import Base
from app.models import core  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location("schema_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connection():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    engine = create_engine(url)
    schema = "goi_test_" + uuid.uuid4().hex
    with engine.connect() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
        db.execute(text(f'SET search_path TO "{schema}"'))
        db.commit()
        try:
            yield db
        finally:
            db.rollback()
            db.execute(text('SET search_path TO public'))
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            db.commit()
    engine.dispose()


def migrate(db, revision):
    module = load(ROOT / "alembic" / "versions" / revision)
    with Operations.context(MigrationContext.configure(db)):
        module.upgrade()


def original_metadata():
    return load(Path(__file__).parent / "fixtures" / "original_models.py").Base.metadata


def test_frozen_0001_matches_original_schema(connection):
    migrate(connection, "0001_initial.py")
    assert compare_metadata(MigrationContext.configure(connection), original_metadata()) == []


def test_fresh_schema_matches_current_models(connection):
    migrate(connection, "0001_initial.py")
    migrate(connection, "0002_ats_discovery.py")
    migrate(connection, "0003_cv_match.py")
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_upgrade_preserves_existing_manual_job_and_queue(connection):
    original_metadata().create_all(connection)
    job_id, task_id = uuid.uuid4(), uuid.uuid4()
    connection.execute(text("INSERT INTO job_listings (id,raw_text,source_url) VALUES (:id,:raw,:url)"),
                       {"id": job_id, "raw": "Original manual description", "url": "https://example.com/job"})
    connection.execute(text("INSERT INTO background_jobs (id,task_type,payload) VALUES (:id,'job_extract',CAST(:payload AS jsonb))"),
                       {"id": task_id, "payload": '{"original":true}'})
    migrate(connection, "0002_ats_discovery.py")
    job = connection.execute(text("SELECT * FROM job_listings WHERE id=:id"), {"id": job_id}).mappings().one()
    assert job["raw_text"] == "Original manual description"
    assert job["source_url"] == "https://example.com/job"
    assert job["provider"] is None
    assert job["ingested_at"] == job["created_at"]
    task = connection.execute(text("SELECT * FROM background_jobs WHERE id=:id"), {"id": task_id}).mappings().one()
    assert task["task_type"] == "job_extract"
    assert task["status"] == "pending"
    assert task["payload"] == {"original": True}
    migrate(connection, "0003_cv_match.py")
    assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_source_and_listing_uniqueness_allow_manual_jobs(connection):
    from sqlalchemy.exc import IntegrityError
    migrate(connection, "0001_initial.py")
    migrate(connection, "0002_ats_discovery.py")
    source_id = uuid.uuid4()
    connection.execute(text("INSERT INTO job_sources (id,provider,board_token,company_name) VALUES (:id,'greenhouse','example','Example')"), {"id": source_id})
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(text("INSERT INTO job_sources (id,provider,board_token,company_name) VALUES (:id,'greenhouse','example','Example')"), {"id": uuid.uuid4()})
    statement = text("INSERT INTO job_listings (id,raw_text,source_id,provider,board_token,external_job_id) VALUES (:id,'Posting',:source,'greenhouse','example','123')")
    connection.execute(statement, {"id": uuid.uuid4(), "source": source_id})
    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(statement, {"id": uuid.uuid4(), "source": source_id})
    for _ in range(2):
        connection.execute(text("INSERT INTO job_listings (id,raw_text) VALUES (:id,'Manual posting')"), {"id": uuid.uuid4()})
    assert connection.scalar(text("SELECT count(*) FROM job_listings")) == 3
