"""Offline PostgreSQL DDL equivalence; complements live migration tests."""
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location("schema_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0001_postgresql_ddl_exactly_matches_original_models(monkeypatch):
    original = load(Path(__file__).parent / "fixtures" / "original_models.py").Base.metadata
    migration = load(ROOT / "alembic" / "versions" / "0001_initial.py")
    frozen = sa.MetaData()

    def create_table(name, *columns, **kwargs):
        return sa.Table(name, frozen, *columns, **kwargs)

    monkeypatch.setattr(migration.op, "create_table", create_table)
    migration.upgrade()
    assert set(original.tables) == set(frozen.tables)
    dialect = postgresql.dialect()
    for name in original.tables:
        expected, actual = original.tables[name], frozen.tables[name]
        assert list(expected.columns.keys()) == list(actual.columns.keys()), name
        # Constraint iteration order is immaterial; every DDL clause must match.
        def clauses(table):
            return sorted(line.strip().rstrip(",") for line in str(CreateTable(table).compile(dialect=dialect)).splitlines() if line.strip())
        assert clauses(actual) == clauses(expected), name


def test_0003_matches_private_models_without_changing_old_tables(monkeypatch):
    from app.models.core import AnalysisSession, CVMatchAnalysis
    from app.db.base import Base
    migration = load(ROOT / "alembic" / "versions" / "0003_cv_match.py")
    frozen = sa.MetaData()
    # Resolve the unchanged background task foreign key for DDL compilation.
    Base.metadata.tables["background_jobs"].to_metadata(frozen)
    indexes = []
    monkeypatch.setattr(migration.op, "create_table", lambda name, *columns, **kwargs: sa.Table(name, frozen, *columns, **kwargs))
    monkeypatch.setattr(migration.op, "create_index", lambda name, table, columns: indexes.append((name, table, columns)))
    migration.upgrade()
    assert set(frozen.tables) == {"background_jobs", "analysis_sessions", "cv_match_analyses"}
    dialect = postgresql.dialect()
    for model in (AnalysisSession, CVMatchAnalysis):
        expected, actual = model.__table__, frozen.tables[model.__tablename__]
        def clauses(table):
            return sorted(line.strip().rstrip(",") for line in str(CreateTable(table).compile(dialect=dialect)).splitlines() if line.strip())
        assert clauses(actual) == clauses(expected)
        assert {(index.name, model.__tablename__, tuple(column.name for column in index.columns)) for index in expected.indexes} == {
            (name, table, tuple(columns)) for name, table, columns in indexes if table == model.__tablename__}
