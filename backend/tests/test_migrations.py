"""Exercise the actual Alembic environment in unique schemas of a test database."""
import os
import uuid
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
import pytest
from app.db.base import Base
from app.models import core  # noqa: F401
from app.config import settings
from test_migration_contract import ROOT


def test_initial_upgrade_downgrade_and_metadata(monkeypatch):
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires dedicated TEST_DATABASE_URL PostgreSQL database')
    admin = create_engine(url)
    schema = 'wayfaro_migration_test_' + uuid.uuid4().hex
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = make_url(url).update_query_dict({'options': f'-csearch_path={schema}'})
    engine = create_engine(scoped_url)
    monkeypatch.setattr(settings, 'database_url', scoped_url.render_as_string(hide_password=False))
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'alembic'))
    try:
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == 'cv_initial'
            assert set(inspect(db).get_table_names()) == set(Base.metadata.tables) | {'alembic_version'}
            assert compare_metadata(MigrationContext.configure(db), Base.metadata) == []
        command.downgrade(config, 'base')
        with engine.connect() as db:
            assert inspect(db).get_table_names() == ['alembic_version']
        command.upgrade(config, 'head')
        with engine.connect() as db:
            assert compare_metadata(MigrationContext.configure(db), Base.metadata) == []
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
