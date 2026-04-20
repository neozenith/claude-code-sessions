"""
Tests for domain filtering functionality.

Tests config helpers (extract_domain, is_project_blocked),
SQL filter generation, build_filters integration, and the /api/domains endpoint.

API endpoint tests are parametrized via ``db_backend`` fixture.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.config import (
    extract_domain,
    is_project_blocked,
)
from claude_code_sessions.main import app

client = TestClient(app)


class TestExtractDomain:
    """Test extract_domain() config helper."""

    @pytest.mark.parametrize(
        "project_id,expected",
        [
            ("-Users-joshpeak-work-project", "work"),
            ("-Users-joshpeak-play-myapp", "play"),
            ("-Users-joshpeak-clients-acme", "clients"),
            ("-Users-joshpeak-foss-openproject", "foss"),
        ],
    )
    def test_standard_domains(self, project_id: str, expected: str) -> None:
        """Common domains are extracted correctly."""
        assert extract_domain(project_id) == expected

    def test_dot_directory(self) -> None:
        """Dot-prefixed directories (like .config) are extracted."""
        assert extract_domain("-Users-joshpeak-.config-foo") == ".config"

    def test_no_home_prefix(self) -> None:
        """Project IDs not starting with HOME_PREFIX return None."""
        assert extract_domain("-Users-someone-else-work-project") is None

    def test_empty_string(self) -> None:
        """Empty project ID returns None."""
        assert extract_domain("") is None

    def test_home_prefix_only(self) -> None:
        """HOME_PREFIX with no domain segment returns None."""
        from claude_code_sessions.config import HOME_PREFIX

        assert extract_domain(HOME_PREFIX) is None

    def test_home_prefix_with_trailing_dash_only(self) -> None:
        """HOME_PREFIX with just a trailing dash returns None."""
        from claude_code_sessions.config import HOME_PREFIX

        assert extract_domain(HOME_PREFIX + "-") is None


class TestIsProjectBlocked:
    """Test is_project_blocked() config helper."""

    @patch("claude_code_sessions.config.BLOCKED_DOMAINS", ["work", "clients"])
    def test_blocked_domain(self) -> None:
        """Projects in blocked domains return True."""
        assert is_project_blocked("-Users-joshpeak-work-project") is True
        assert is_project_blocked("-Users-joshpeak-clients-acme") is True

    @patch("claude_code_sessions.config.BLOCKED_DOMAINS", ["work", "clients"])
    def test_unblocked_domain(self) -> None:
        """Projects in non-blocked domains return False."""
        assert is_project_blocked("-Users-joshpeak-play-myapp") is False
        assert is_project_blocked("-Users-joshpeak-foss-openproject") is False

    @patch("claude_code_sessions.config.BLOCKED_DOMAINS", [])
    def test_empty_blocked_list(self) -> None:
        """Empty BLOCKED_DOMAINS never blocks anything."""
        assert is_project_blocked("-Users-joshpeak-work-project") is False

    @patch("claude_code_sessions.config.BLOCKED_DOMAINS", ["work"])
    def test_no_domain_not_blocked(self) -> None:
        """Projects without a domain (no home prefix) are not blocked."""
        assert is_project_blocked("some-random-id") is False


@pytest.mark.usefixtures("db_backend")
class TestDomainsEndpoint:
    """Test GET /api/domains endpoint."""

    def test_domains_returns_structure(self) -> None:
        """Domains endpoint returns available, blocked, and all lists."""
        response = client.get("/api/domains")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "blocked" in data
        assert "all" in data
        assert isinstance(data["available"], list)
        assert isinstance(data["blocked"], list)
        assert isinstance(data["all"], list)

    def test_domains_all_is_superset(self) -> None:
        """The 'all' list is the union of available and blocked."""
        response = client.get("/api/domains")
        data = response.json()
        assert set(data["all"]) == set(data["available"]) | set(data["blocked"])

    def test_domains_lists_are_sorted(self) -> None:
        """All domain lists are sorted alphabetically."""
        response = client.get("/api/domains")
        data = response.json()
        assert data["available"] == sorted(data["available"])
        assert data["blocked"] == sorted(data["blocked"])
        assert data["all"] == sorted(data["all"])


@pytest.mark.usefixtures("db_backend")
class TestDomainGuardEndpoints:
    """Test that direct-access endpoints enforce domain blocking.

    Uses the ``project_blocked`` parametrized fixture (True/False) combined
    with ``db_backend`` (duckdb/sqlite) — each test runs 4 times automatically.
    """

    def test_timeline_events_domain_guard(self, project_blocked: bool) -> None:
        """Timeline events returns 404 when blocked, succeeds when not."""
        response = client.get("/api/timeline/events/-Users-joshpeak-work-secret")
        if project_blocked:
            assert response.status_code == 404
        else:
            # Not blocked — should not get a domain-guard 404
            assert response.status_code != 404 or "not found" not in response.json().get(
                "detail", ""
            ).lower()

    def test_session_events_domain_guard(self, project_blocked: bool) -> None:
        """Session events returns 404 when blocked, succeeds when not."""
        response = client.get("/api/sessions/-Users-joshpeak-work-secret/fake-session-id")
        if project_blocked:
            assert response.status_code == 404
        else:
            assert response.status_code != 404 or "not found" not in response.json().get(
                "detail", ""
            ).lower()
