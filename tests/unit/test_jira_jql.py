"""Unit tests for jira_jql.py."""
# pylint: disable-next=import-error
import base64

import pytest

from extensions.eda.plugins.event_source.jira_jql import (
    _build_auth_headers,
    _issue_event_key,
)


def test_build_auth_headers_basic():
    headers = _build_auth_headers("user@example.com", "apitoken")
    expected = base64.b64encode(b"user@example.com:apitoken").decode("ascii")
    assert headers == {"Authorization": f"Basic {expected}"}


def test_build_auth_headers_bearer():
    headers = _build_auth_headers(None, "oauth-token")
    assert headers == {"Authorization": "Bearer oauth-token"}


def test_issue_event_key():
    issue = {
        "key": "OPS-1",
        "fields": {"updated": "2026-01-01T10:00:00.000+0000"},
    }
    assert _issue_event_key(issue) == "OPS-1:2026-01-01T10:00:00.000+0000"
