from datetime import datetime, timezone
from app.services.ingestion.base import NormalizedJob
from app.services.ingestion.normalizer import description_text, source_date


def test_text_keeps_words_and_ignores_scripts():
    assert description_text("<p>Hello &amp; welcome</p><script>bad()</script><p>World</p>") == "Hello & welcome\nWorld"
    assert description_text(None) is None


def test_dates_never_guess_timezone():
    assert source_date("2026-01-01T10:00:00") is None
    assert source_date("invalid") is None
    assert source_date(None) is None
    assert source_date("2026-01-01T10:00:00Z").tzinfo == timezone.utc


def test_normalized_dates_are_utc_and_unknown_is_null():
    job = NormalizedJob(provider="test", board_token="board", external_job_id="1", company_name="Company", title="Title",
                        published_at=datetime(2026, 1, 1), updated_at="2026-01-01T10:00:00+02:00")
    assert job.published_at is None
    assert job.updated_at == datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
