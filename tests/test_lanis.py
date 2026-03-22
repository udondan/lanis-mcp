"""Integration tests for the Lanis MCP server.

Requires environment variables to be set before running:

    export LANIS_SCHOOL_ID=...
    export LANIS_USERNAME=...
    export LANIS_PASSWORD=...

Run with:

    .venv/bin/pytest tests/ -v
"""

import asyncio
import os
import tempfile

import pytest

# LanisAPI writes session.json relative to the current working directory.
# Switch to a writable temp dir before anything else is imported.
_session_dir = os.path.join(tempfile.gettempdir(), "lanis-mcp-test")
os.makedirs(_session_dir, exist_ok=True)
os.chdir(_session_dir)


def _require_env(*names: str) -> None:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        pytest.skip(f"Missing required env vars: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_credentials_present(self):
        """All required env vars must be set."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

    def test_authenticate(self):
        """LanisClient authenticates successfully with the provided credentials."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp import client as client_module

        client_module._client = None

        from lanis_mcp.client import get_client

        lanis = get_client()

        assert lanis is not None
        assert lanis.authenticated, "Client is not authenticated"


# ---------------------------------------------------------------------------
# Tasks / Homework
# ---------------------------------------------------------------------------
# Substitution plan
# ---------------------------------------------------------------------------


class TestSubstitutionPlan:
    def test_get_substitution_plan(self):
        """get_substitution_plan() returns a plan object."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")
        from datetime import date

        if date.today().weekday() >= 5:
            pytest.skip("No substitution plan on weekends")

        from lanis_mcp.client import get_client

        plan = get_client().get_substitution_plan()

        assert plan is not None
        print(f"\n  Date: {plan.date}, substitutions: {len(plan.substitutions or [])}")

    def test_get_substitution_plan_via_mcp_tool(self):
        """The MCP tool lanis_get_substitution_plan returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")
        from datetime import date

        if date.today().weekday() >= 5:
            pytest.skip("No substitution plan on weekends")

        from lanis_mcp.server import lanis_get_substitution_plan, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                lanis_get_substitution_plan(ResponseFormat.MARKDOWN)
            )
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


class TestCalendar:
    def test_get_calendar_of_month(self):
        """get_calendar_of_month() returns a calendar object."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.client import get_client

        calendar = get_client().get_calendar_of_month()

        assert calendar is not None
        print(f"\n  Events this month: {len(calendar.events or [])}")

    def test_get_calendar_via_mcp_tool(self):
        """The MCP tool lanis_get_calendar_of_month returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_calendar_of_month, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                lanis_get_calendar_of_month(ResponseFormat.MARKDOWN)
            )
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")
