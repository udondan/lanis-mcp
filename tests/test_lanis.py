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

    def test_get_calendar_of_month_via_mcp_tool(self):
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

    def test_get_calendar_with_date_range_via_mcp_tool(self):
        """The MCP tool lanis_get_calendar returns events for an explicit date range."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_calendar, CalendarInput, ResponseFormat

        params = CalendarInput(
            start="2026-01-01",
            end="2026-12-31",
            response_format=ResponseFormat.MARKDOWN,
        )

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_calendar(params))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")

    def test_get_calendar_invalid_date_returns_error(self):
        """lanis_get_calendar returns an error string for invalid date formats."""
        from lanis_mcp.server import CalendarInput

        with pytest.raises(Exception):
            CalendarInput(start="not-a-date", end="2026-12-31")


# ---------------------------------------------------------------------------
# Tasks / Homework
# ---------------------------------------------------------------------------


class TestTasks:
    def test_get_tasks_via_mcp_tool(self):
        """The MCP tool lanis_get_tasks returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_tasks, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_tasks(ResponseFormat.MARKDOWN))
        finally:
            loop.close()

        assert isinstance(result, str)
        if "AppNotAvailableError" in result:
            pytest.skip("Mein Unterricht is not available at this school")
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")

    def test_get_tasks_json_format(self):
        """lanis_get_tasks returns valid JSON with expected keys."""
        import json as _json

        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_tasks, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_tasks(ResponseFormat.JSON))
        finally:
            loop.close()

        assert isinstance(result, str)
        if "AppNotAvailableError" in result:
            pytest.skip("Mein Unterricht is not available at this school")
        assert not result.startswith("Error:"), f"Tool returned error: {result}"

        if result == "No tasks found.":
            pytest.skip("No tasks available to validate JSON structure")

        data = _json.loads(result)
        assert "count" in data
        assert "tasks" in data
        print(f"\n  Tasks found: {data['count']}")


# ---------------------------------------------------------------------------
# Conversations / Messages
# ---------------------------------------------------------------------------


class TestConversations:
    def test_get_conversations_via_mcp_tool(self):
        """The MCP tool lanis_get_conversations returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import (
            lanis_get_conversations,
            ConversationsInput,
            ResponseFormat,
        )

        params = ConversationsInput(number=5, response_format=ResponseFormat.MARKDOWN)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_conversations(params))
        finally:
            loop.close()

        assert isinstance(result, str)
        if "AppNotAvailableError" in result:
            pytest.skip("Nachrichten is not available at this school")
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")

    def test_get_conversations_json_format(self):
        """lanis_get_conversations returns valid JSON with expected keys."""
        import json as _json

        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import (
            lanis_get_conversations,
            ConversationsInput,
            ResponseFormat,
        )

        params = ConversationsInput(number=3, response_format=ResponseFormat.JSON)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_conversations(params))
        finally:
            loop.close()

        assert isinstance(result, str)
        if "AppNotAvailableError" in result:
            pytest.skip("Nachrichten is not available at this school")
        assert not result.startswith("Error:"), f"Tool returned error: {result}"

        if result == "No conversations found.":
            pytest.skip("No conversations available to validate JSON structure")

        data = _json.loads(result)
        assert "count" in data
        assert "conversations" in data
        print(f"\n  Conversations found: {data['count']}")


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------


class TestApps:
    def test_get_apps_via_mcp_tool(self):
        """The MCP tool lanis_get_apps returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_apps, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_apps(ResponseFormat.MARKDOWN))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")

    def test_get_available_apps_via_mcp_tool(self):
        """The MCP tool lanis_get_available_apps returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_available_apps

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_available_apps())
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Result: {result}")


# ---------------------------------------------------------------------------
# Schools
# ---------------------------------------------------------------------------


class TestSchools:
    def test_get_schools_via_mcp_tool(self):
        """The MCP tool lanis_get_schools returns a non-error string without auth."""
        from lanis_mcp.server import lanis_get_schools, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_schools(ResponseFormat.MARKDOWN))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")

    def test_get_schools_json_format(self):
        """lanis_get_schools returns a non-empty JSON response (may be truncated)."""
        from lanis_mcp.server import lanis_get_schools, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_schools(ResponseFormat.JSON))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        # The school list is large and may be truncated; verify it starts with JSON
        assert result.startswith("{"), "Expected JSON output to start with '{'"
        assert '"schools"' in result, "Expected 'schools' key in output"
        assert '"count"' in result, "Expected 'count' key in output"
        print(f"\n  Output length: {len(result)} chars")


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


class TestFolders:
    def test_get_folders_via_mcp_tool(self):
        """The MCP tool lanis_get_folders returns a non-error string."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_folders, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_folders(ResponseFormat.MARKDOWN))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        print(f"\n  Preview: {result[:200]}")


# ---------------------------------------------------------------------------
# App availability check
# ---------------------------------------------------------------------------


class TestAppAvailability:
    def test_check_valid_app_availability(self):
        """lanis_check_app_availability returns a clear yes/no for a valid app name."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_check_app_availability

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_check_app_availability("Kalender"))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert not result.startswith("Error:"), f"Tool returned error: {result}"
        assert "Kalender" in result
        assert "available" in result
        print(f"\n  Result: {result}")

    def test_check_invalid_app_name_returns_error(self):
        """lanis_check_app_availability returns an error for an unknown app name."""
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_check_app_availability

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                lanis_check_app_availability("NonExistentApp")
            )
        finally:
            loop.close()

        assert isinstance(result, str)
        assert result.startswith("Error:"), f"Expected error, got: {result}"
        assert "NonExistentApp" in result
        print(f"\n  Result: {result}")
