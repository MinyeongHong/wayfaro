"""Offline contract for the single private-comparison initial revision."""
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.db.base import Base
from app.models import core  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def load_migration():
    path = ROOT / 'alembic' / 'versions' / '0001_cv_comparison.py'
    spec = importlib.util.spec_from_file_location('initial_schema', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_matches_private_models(monkeypatch):
    migration = load_migration()
    assert migration.down_revision is None
    assert migration.revision == 'cv_initial'
    assert len(list((ROOT / 'alembic' / 'versions').glob('*.py'))) == 1
    frozen = sa.MetaData()
    indexes = []
    monkeypatch.setattr(migration.op, 'create_table', lambda name, *columns, **kwargs: sa.Table(name, frozen, *columns, **kwargs))
    monkeypatch.setattr(migration.op, 'create_index', lambda name, table, columns: indexes.append((name, table, tuple(columns))))
    migration.upgrade()
    assert set(frozen.tables) == set(Base.metadata.tables) == {
        'background_jobs', 'analysis_sessions', 'cv_match_analyses'}
    dialect = postgresql.dialect()
    def clauses(table):
        return sorted(line.strip().rstrip(',') for line in str(CreateTable(table).compile(dialect=dialect)).splitlines() if line.strip())
    for name, expected in Base.metadata.tables.items():
        assert clauses(frozen.tables[name]) == clauses(expected), name
        assert {(i.name, name, tuple(c.name for c in i.columns)) for i in expected.indexes} == {
            i for i in indexes if i[1] == name}


def test_alembic_environment_generates_initial_sql_without_database(monkeypatch):
    from io import StringIO
    from alembic import command
    from alembic.config import Config
    from app.config import settings
    # Encoded query values exercise ConfigParser URL interpolation too.
    monkeypatch.setattr(settings, 'database_url',
        'postgresql+psycopg://offline:offline@127.0.0.1/offline?options=-csearch_path%3Dtest')
    output = StringIO()
    config = Config(str(ROOT / 'alembic.ini'), output_buffer=output)
    config.set_main_option('script_location', str(ROOT / 'alembic'))
    command.upgrade(config, 'head', sql=True)
    sql = output.getvalue()
    assert "'cv_initial'" in sql
    for name in Base.metadata.tables:
        assert f'CREATE TABLE {name}' in sql
    assert sql.count('CREATE TABLE ') == 4  # Three models plus Alembic version table.
