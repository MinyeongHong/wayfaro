"""Queue timing and HTTP retry policies that do not require a database."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
from app.services.matching.llm import _retry_after
from app.workers.runner import retry_delay


@pytest.mark.parametrize("attempt,expected", [(1, 5), (2, 10), (3, 20), (11, 3600), (1000000, 3600)])
def test_exponential_backoff_is_bounded(attempt, expected):
    assert retry_delay(attempt) == expected


@pytest.mark.parametrize("header,expected", [(None, 5), (-1, 5), (2, 5), (120, 120), (1000000, 86400), (float("inf"), 5), (float("nan"), 5)])
def test_retry_after_respects_backoff_and_safety_bound(header, expected):
    assert retry_delay(1, header) == expected


def test_http_date_retry_after():
    future = datetime.now(timezone.utc) + timedelta(minutes=2)
    assert 118 <= _retry_after(format_datetime(future, usegmt=True)) <= 120
    assert _retry_after("not a date") is None
    assert _retry_after("-5") == 0
