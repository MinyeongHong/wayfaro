from datetime import datetime, timedelta, timezone
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.api.routes import get_db
from app.main import app
from app.models.core import JobListing, JobSource
from app.services.discovery import safe_source_url


@pytest.fixture
def client(sessions):
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def listings(sessions):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with sessions.begin() as db:
        source = JobSource(provider="greenhouse", board_token="example", company_name="Example")
        unused = JobSource(provider="greenhouse", board_token="unused", company_name="Unused")
        db.add_all([source, unused])
        db.flush()
        records = [
            JobListing(id=uuid.UUID(int=1), raw_text="Manual Python description for compatibility", created_at=now),
            JobListing(id=uuid.UUID(int=2), raw_text="<p>Data engineering</p>", description_text="Data engineering",
                       title="Data Engineer 100%_", company_name="Example", location_text="Rome, Italy — Remote",
                       source_id=source.id, provider="greenhouse", board_token="example", external_job_id="1",
                       source_url="https://example.com/1", published_at=now, created_at=now),
            JobListing(id=uuid.UUID(int=3), raw_text="C++ developer", title="Engineer", company_name="Example",
                       location_text="Paris, France — not remote", source_id=source.id,
                       provider="greenhouse", board_token="example", external_job_id="2",
                       published_at=now + timedelta(days=1), created_at=now),
            JobListing(id=uuid.UUID(int=4), raw_text="Local role", location_text="Rome", title="Office role", created_at=now),
        ]
        db.add_all(records)
        return source.id


def ids(response):
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def test_empty_and_out_of_range_pages(client):
    for page in (1, 99):
        body = client.get("/api/v1/jobs", params={"page": page}).json()
        assert body == {"items": [], "page": page, "page_size": 20, "total": 0,
                        "total_pages": 0, "source_options": []}


def test_pages_sort_and_source_options(client, listings):
    first = client.get("/api/v1/jobs?page_size=2").json()
    second = client.get("/api/v1/jobs?page_size=2&page=2").json()
    assert first["total"] == 4 and first["total_pages"] == 2
    assert [item["id"] for item in first["items"]] == [str(uuid.UUID(int=4)), str(uuid.UUID(int=3))]
    assert len({item["id"] for item in first["items"] + second["items"]}) == 4
    assert first["source_options"] == [{"id": str(listings), "provider": "greenhouse", "company_name": "Example", "board_token": "example"}]
    assert ids(client.get("/api/v1/jobs?page=99")) == []
    assert client.get("/api/v1/jobs?page=99").json()["total"] == 4
    published = client.get("/api/v1/jobs?sort=published_desc").json()["items"]
    assert [item["id"] for item in published[:2]] == [str(uuid.UUID(int=3)), str(uuid.UUID(int=2))]
    assert all(item["published_at"] is None for item in published[2:])
    assert len(ids(client.get("/api/v1/jobs?sort=updated_desc"))) == 4


@pytest.mark.parametrize("query,expected", [
    ({"q": "python"}, [1]), ({"q": "ENGINEER"}, [3, 2]), ({"q": "100%_"}, [2]),
    ({"q": "%"}, [2]), ({"q": "_"}, [2]), ({"q": "Example"}, [3, 2]),
    ({"location": "rome"}, [4, 2]), ({"country_text": "Italy", "region_text": "Rome"}, [2]),
    ({"location": "Berlin"}, []), ({"origin": "manual"}, [4, 1]), ({"origin": "ats"}, [3, 2]),
    ({"remote_mention": "PRESENT"}, [3, 2]), ({"remote_mention": "NOT_MENTIONED"}, [4]),
    ({"remote_mention": "UNKNOWN"}, [1]), ({"q": "engineer", "location": "Italy"}, [2]),
])
def test_search_and_filters(client, listings, query, expected):
    assert ids(client.get("/api/v1/jobs", params=query)) == [str(uuid.UUID(int=value)) for value in expected]


def test_source_filter_and_no_country_inference(client, listings):
    assert len(ids(client.get("/api/v1/jobs", params={"source_id": str(listings)}))) == 2
    assert ids(client.get("/api/v1/jobs", params={"source_id": str(uuid.uuid4())})) == []
    # The Rome-only listing is not inferred to be in Italy.
    assert ids(client.get("/api/v1/jobs?country_text=Italy")) == [str(uuid.UUID(int=2))]


def test_detail_preserves_missing_fields_and_safe_links(client, listings, sessions):
    manual = client.get(f"/api/v1/jobs/{uuid.UUID(int=1)}").json()
    assert manual["title"] is manual["company_name"] is manual["source_id"] is None
    assert manual["remote_mention"] == "UNKNOWN"
    assert manual["raw_text"] == "Manual Python description for compatibility"
    assert manual["origin"] == "manual"
    ats = client.get(f"/api/v1/jobs/{uuid.UUID(int=2)}").json()
    assert ats["description_text"] == "Data engineering"
    assert ats["source_url"] == "https://example.com/1"
    assert "raw_metadata" not in ats and "description_html" not in ats
    with sessions.begin() as db:
        db.scalar(select(JobListing).where(JobListing.id == uuid.UUID(int=2))).source_url = "javascript:alert(1)"
    assert client.get(f"/api/v1/jobs/{uuid.UUID(int=2)}").json()["source_url"] is None
    assert client.get(f"/api/v1/jobs/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/jobs/not-a-uuid").status_code == 422


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101", "sort=invalid", "origin=invalid", "remote_mention=REMOTE", "source_id=invalid", "q=" + "a" * 201])
def test_invalid_query(query):
    with TestClient(app) as client:
        assert client.get(f"/api/v1/jobs?{query}").status_code == 422


@pytest.mark.parametrize("url", [None, "javascript:alert(1)", "data:text/html,bad", "//evil.example", "https://user:password@example.com", "https://example.com\\@evil.example", "https://example.com/\n", "http://[", "https://example.com:invalid"])
def test_unsafe_url_is_not_exposed(url):
    assert safe_source_url(url) is None


def test_valid_source_url():
    assert safe_source_url("https://example.com/job?id=1#details") == "https://example.com/job?id=1#details"


def test_query_compiles_for_postgresql_without_database():
    """Catch query construction failures even when live integration tests skip."""
    from sqlalchemy.dialects import postgresql
    from app.services.discovery import list_jobs

    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class CompileOnly:
        def execute(self, statement):
            compiled = statement.compile(dialect=postgresql.dialect())
            assert "LEFT OUTER JOIN" in str(compiled)
            assert "%100\\%\\_%" in compiled.params.values()
            return Rows([(0, None, "UNKNOWN")])

        def scalars(self, statement):
            statement.compile(dialect=postgresql.dialect())
            return Rows([])

    result = list_jobs(CompileOnly(), page=2, page_size=20, q="100%_", location="Rome", remote_mention="PRESENT")
    assert result.total == 0 and result.items == []
