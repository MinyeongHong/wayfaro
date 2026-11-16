import httpx
import pytest
from app.services.ingestion.base import ConnectorError, SourceConfig
from app.services.ingestion.greenhouse import GreenhouseConnector

SOURCE = SourceConfig(provider="greenhouse", board_token="example", company_name="Example Co")


def fetch(payload, status=200, headers=None):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=payload, headers=headers)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GreenhouseConnector(client).fetch(SOURCE)
    assert len(requests) == 1
    assert requests[0].url.params["content"] == "true"
    return result


def test_success_and_stable_post_identity():
    record = {"id": 123, "internal_job_id": 999, "title": "Engineer", "content": "&lt;p&gt;Build things&lt;/p&gt;",
              "absolute_url": "https://example.com/jobs/123", "location": {"name": "Rome"},
              "departments": [{"name": "Engineering"}], "updated_at": "2026-01-01T12:00:00+02:00"}
    job = fetch({"jobs": [record]}).jobs[0]
    assert job.external_job_id == "123"
    assert job.board_token == "example"
    assert job.company_name == "Example Co"
    assert job.raw_metadata == record
    assert job.description_html == record["content"]
    assert job.description_text == "Build things"
    assert job.updated_at.hour == 10
    assert job.published_at is None
    assert job.external_job_id == fetch({"jobs": [record]}).jobs[0].external_job_id


def test_missing_optional_fields():
    job = fetch({"jobs": [{"id": 1, "title": "Engineer"}]}).jobs[0]
    assert job.source_url is None
    assert job.location_text is None
    assert job.department is None
    assert job.description_html is None
    assert job.description_text is None
    assert job.updated_at is None


@pytest.mark.parametrize("payload", [{}, [], {"jobs": None}, {"jobs": {}}])
def test_invalid_envelope(payload):
    with pytest.raises(ConnectorError, match="jobs array"):
        fetch(payload)


def test_partial_failure_and_duplicate_identity():
    result = fetch({"jobs": [{"id": 1, "title": "Good"}, {"id": 1, "title": "Duplicate"}, {"title": "No ID"}, None]})
    assert result.jobs_fetched == 4
    assert len(result.jobs) == 1
    assert len(result.errors) == 3
    assert result.errors[1].raw_record == {"title": "No ID"}


@pytest.mark.parametrize("status,retryable", [(404, False), (429, True), (503, True)])
def test_http_errors(status, retryable):
    with pytest.raises(ConnectorError) as error:
        fetch({}, status, {"Retry-After": "120"})
    assert error.value.retryable is retryable
    assert error.value.retry_after_seconds == 120


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ConnectorError) as error:
            GreenhouseConnector(client).fetch(SOURCE)
    assert error.value.retryable


def test_invalid_json():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"invalid"))) as client:
        with pytest.raises(ConnectorError, match="invalid JSON"):
            GreenhouseConnector(client).fetch(SOURCE)
