"""Public Greenhouse Job Board API: one content-inclusive request per board."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx
from pydantic import ValidationError
from .base import ConnectorError, FetchResult, NormalizedJob, RecordError, SourceConfig
from .normalizer import description_text, source_date


def _optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected a string or null")
    return value or None


def _retry_after(value):
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


class GreenhouseConnector:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client

    def fetch(self, source: SourceConfig) -> FetchResult:
        if source.provider != "greenhouse":
            raise ConnectorError("INVALID_SOURCE", "Expected a Greenhouse source")
        if self.client is None:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as client:
                return self._fetch(client, source)
        return self._fetch(self.client, source)

    def _fetch(self, client, source):
        try:
            response = client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{source.board_token}/jobs",
                params={"content": "true"}, timeout=httpx.Timeout(30, connect=10))
        except httpx.RequestError as exc:
            raise ConnectorError("NETWORK_ERROR", "Greenhouse request failed", retryable=True) from exc
        if not response.is_success:
            raise ConnectorError("HTTP_ERROR", f"Greenhouse returned HTTP {response.status_code}",
                                 retryable=response.status_code in (429, 500, 502, 503, 504),
                                 retry_after_seconds=_retry_after(response.headers.get("Retry-After")))
        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectorError("INVALID_RESPONSE", "Greenhouse returned invalid JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ConnectorError("INVALID_RESPONSE", "Expected a jobs array")
        result = FetchResult(jobs_fetched=len(data["jobs"]), source_metadata={"meta": data.get("meta")})
        seen = set()
        for index, record in enumerate(data["jobs"]):
            try:
                job = self.normalize(record, source)
                if job.external_job_id in seen:
                    raise ValueError("Duplicate posting identity in response")
                seen.add(job.external_job_id)
                result.jobs.append(job)
            except (ValueError, TypeError, ValidationError) as exc:
                result.errors.append(RecordError(index=index, message=str(exc), raw_record=record))
        return result

    @staticmethod
    def normalize(record, source):
        if not isinstance(record, dict):
            raise ValueError("Expected a job object")
        identity = record.get("id")
        if isinstance(identity, bool) or not isinstance(identity, (str, int)) or not str(identity).strip():
            raise ValueError("Missing or invalid posting id")
        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Missing or invalid title")
        location = record.get("location")
        if location is not None and not isinstance(location, dict):
            raise ValueError("Invalid location")
        departments = record.get("departments")
        if departments is not None and not isinstance(departments, list):
            raise ValueError("Invalid departments")
        names = []
        for item in departments or []:
            if not isinstance(item, dict):
                raise ValueError("Invalid department")
            name = _optional_text(item.get("name"))
            if name:
                names.append(name)
        content = _optional_text(record.get("content"))
        return NormalizedJob(
            provider="greenhouse", board_token=source.board_token, external_job_id=str(identity),
            company_name=source.company_name, title=title,
            source_url=_optional_text(record.get("absolute_url")),
            location_text=_optional_text(location.get("name")) if location else None,
            department="; ".join(names) or None, description_html=content,
            description_text=description_text(content), published_at=source_date(record.get("first_published")),
            updated_at=source_date(record.get("updated_at")), raw_metadata=record)
