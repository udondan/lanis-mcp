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
from unittest.mock import patch, MagicMock

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
# Unit tests: app availability detection (no live credentials needed)
# ---------------------------------------------------------------------------


class TestAppAvailabilityDetection:
    """Unit tests for the monkey-patched _get_available_apps function.

    These tests verify that app availability is detected by URL path in addition
    to app name similarity, so schools that rename apps (e.g. 'Meine Kurse'
    instead of 'Mein Unterricht') are still correctly detected.
    """

    def _make_app(self, name: str, link: str) -> MagicMock:
        """Create a mock App object with the given name and link."""
        app = MagicMock()
        app.name = name
        app.link = link
        return app

    def _clear_cache(self, fn: object) -> None:
        """Clear the function cache if it has one (e.g. @cache decorated functions)."""
        if hasattr(fn, "cache_clear"):
            fn.cache_clear()  # type: ignore[union-attr]

    def test_exact_name_match_detected(self):
        """App with exact name 'Mein Unterricht' is detected as available."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app("Mein Unterricht", "https://example.com/meinunterricht.php")
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert "Mein Unterricht" in result

    def test_renamed_app_detected_by_url(self):
        """App named 'Meine Kurse' linking to meinunterricht.php is detected as 'Mein Unterricht'."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app(
                "Meine Kurse", "https://start.schulportal.hessen.de/meinunterricht.php"
            )
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert "Mein Unterricht" in result, (
                f"Expected 'Mein Unterricht' in available apps, got: {result}"
            )

    def test_kalender_detected_by_url(self):
        """App with different name linking to kalender.php is detected as 'Kalender'."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app(
                "Schulkalender", "https://start.schulportal.hessen.de/kalender.php"
            )
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert "Kalender" in result, (
                f"Expected 'Kalender' in available apps, got: {result}"
            )

    def test_vertretungsplan_detected_by_url(self):
        """App with different name linking to vertretungsplan.php is detected."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app(
                "Vertretungen",
                "https://start.schulportal.hessen.de/vertretungsplan.php",
            )
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert "Vertretungsplan" in result, (
                f"Expected 'Vertretungsplan' in available apps, got: {result}"
            )

    def test_nachrichten_detected_by_url(self):
        """App with different name linking to nachrichten.php is detected."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app(
                "Meine Nachrichten",
                "https://start.schulportal.hessen.de/nachrichten.php",
            )
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert "Nachrichten - Beta-Version" in result, (
                f"Expected 'Nachrichten - Beta-Version' in available apps, got: {result}"
            )

    def test_unrelated_app_not_detected(self):
        """App with unrelated name and URL is not detected as any supported app."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app(
                "Moodle", "https://start.schulportal.hessen.de/schulmoodle.php"
            )
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert "Mein Unterricht" not in result
            assert "Kalender" not in result
            assert "Vertretungsplan" not in result
            assert "Nachrichten - Beta-Version" not in result

    def test_no_duplicate_when_both_name_and_url_match(self):
        """App that matches both by name and URL is only listed once."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        apps = [
            self._make_app(
                "Mein Unterricht",
                "https://start.schulportal.hessen.de/meinunterricht.php",
            )
        ]
        with patch.object(apps_module, "_get_apps", return_value=apps):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert result.count("Mein Unterricht") == 1, (
                f"Expected exactly one 'Mein Unterricht' entry, got: {result}"
            )

    def test_empty_app_list_returns_empty(self):
        """Empty app list returns no available apps."""
        import lanis_mcp.client  # noqa: F401 — trigger monkey-patch
        import lanisapi.functions.apps as apps_module

        with patch.object(apps_module, "_get_apps", return_value=[]):
            self._clear_cache(apps_module._get_available_apps)
            result = apps_module._get_available_apps()
            assert result == []


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
        """The MCP tool lanis_get_tasks returns a non-error string.

        After the fix, AppNotAvailableError must never be returned even when
        the school uses a renamed app (e.g. 'Meine Kurse' instead of 'Mein Unterricht').
        """
        _require_env("LANIS_SCHOOL_ID", "LANIS_USERNAME", "LANIS_PASSWORD")

        from lanis_mcp.server import lanis_get_tasks, ResponseFormat

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(lanis_get_tasks(ResponseFormat.MARKDOWN))
        finally:
            loop.close()

        assert isinstance(result, str)
        assert "AppNotAvailableError" not in result, (
            "lanis_get_tasks returned AppNotAvailableError — "
            "the URL-based availability detection is not working correctly"
        )
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
        assert "AppNotAvailableError" not in result, (
            "lanis_get_tasks returned AppNotAvailableError — "
            "the URL-based availability detection is not working correctly"
        )
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


# ---------------------------------------------------------------------------
# Unit tests: MCP tool name registration (no live credentials needed)
# ---------------------------------------------------------------------------


class TestToolNames:
    """Unit tests verifying that registered MCP tool names are correct.

    These tests do NOT require live credentials — they only inspect the
    FastMCP tool registry to ensure no tool name starts with 'lanis_'.
    Since the MCP server is registered under the name 'lanis', a tool
    named 'lanis_get_tasks' would be exposed to clients as
    'lanis_lanis_get_tasks' (double prefix), which is wrong.
    """

    EXPECTED_TOOL_NAMES = {
        "get_schools",
        "get_substitution_plan",
        "get_calendar",
        "get_calendar_of_month",
        "get_tasks",
        "get_conversations",
        "get_apps",
        "get_available_apps",
        "get_folders",
        "check_app_availability",
        "get_timetable",
        "get_learning_groups",
        "get_file_storage",
        "get_file_distribution",
        "get_votes",
    }

    def _get_registered_tool_names(self) -> set:
        """Return the set of tool names registered with the FastMCP instance."""
        from lanis_mcp.server import mcp

        loop = asyncio.new_event_loop()
        try:
            tools = loop.run_until_complete(mcp.list_tools())
        finally:
            loop.close()
        return {t.name for t in tools}

    def test_no_tool_name_starts_with_lanis_prefix(self):
        """No registered tool name should start with 'lanis_'.

        The MCP server is named 'lanis', so tool names must NOT include
        the 'lanis_' prefix — otherwise clients see 'lanis_lanis_...'
        (double prefix).
        """
        tool_names = self._get_registered_tool_names()
        bad_names = [n for n in tool_names if n.startswith("lanis_")]
        assert not bad_names, (
            f"The following tool names incorrectly start with 'lanis_' "
            f"(would cause double-prefix for clients): {sorted(bad_names)}"
        )

    def test_all_expected_tools_are_registered(self):
        """All 15 expected tools are registered with the correct names."""
        tool_names = self._get_registered_tool_names()
        missing = self.EXPECTED_TOOL_NAMES - tool_names
        assert not missing, (
            f"The following expected tools are missing from the registry: "
            f"{sorted(missing)}"
        )

    def test_no_unexpected_tools_registered(self):
        """No extra tools beyond the expected 15 are registered."""
        tool_names = self._get_registered_tool_names()
        extra = tool_names - self.EXPECTED_TOOL_NAMES
        assert not extra, f"Unexpected tools found in registry: {sorted(extra)}"

    def test_tool_count_is_correct(self):
        """Exactly 15 tools are registered."""
        tool_names = self._get_registered_tool_names()
        assert len(tool_names) == len(self.EXPECTED_TOOL_NAMES), (
            f"Expected {len(self.EXPECTED_TOOL_NAMES)} tools, "
            f"got {len(tool_names)}: {sorted(tool_names)}"
        )


# ---------------------------------------------------------------------------
# Unit tests: timetable rowspan / duration parsing (no live credentials)
# ---------------------------------------------------------------------------


class TestTimetableParsing:
    """Unit tests for the timetable HTML parser.

    These tests exercise the virtual-grid algorithm that handles rowspan cells.
    They do NOT require live credentials — they feed synthetic HTML directly
    into the same parsing logic used by lanis_get_timetable.
    """

    def _parse(self, html: str) -> list[dict]:
        """Run the timetable parsing logic on the given HTML fragment.

        Replicates the inner parsing loop from lanis_get_timetable so we can
        test it in isolation without an HTTP request.
        """
        from selectolax.parser import HTMLParser
        from typing import Any

        _DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]

        tree = HTMLParser(html)
        rows = tree.css("table.table-hoverRowspan tbody tr")
        occupied: dict[tuple[int, int], bool] = {}
        entries: list[dict[str, Any]] = []

        for row_idx, row in enumerate(rows):
            cells = row.css("td")
            if not cells:
                continue

            hour_cell = cells[0]
            hour_name_node = hour_cell.css_first("b")
            hour_name = hour_name_node.text(strip=True) if hour_name_node else ""
            time_node = hour_cell.css_first("small")
            time_text = time_node.text(strip=True) if time_node else ""

            if not hour_name:
                continue

            col = 0
            for cell in cells[1:]:
                while occupied.get((row_idx, col)):
                    col += 1
                if col >= len(_DAYS):
                    break

                rowspan = int(cell.attributes.get("rowspan", 1))
                for span_row in range(row_idx + 1, row_idx + rowspan):
                    occupied[(span_row, col)] = True

                stunde = cell.css_first("div.stunde")
                if stunde:
                    subject_node = stunde.css_first("b")
                    subject = subject_node.text(strip=True) if subject_node else ""
                    teacher_node = stunde.css_first("small")
                    teacher = teacher_node.text(strip=True) if teacher_node else ""
                    entries.append(
                        {
                            "hour": hour_name,
                            "time": time_text,
                            "day": _DAYS[col],
                            "subject": subject,
                            "teacher": teacher,
                            "duration": rowspan,
                        }
                    )
                col += 1

        return entries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap(rows_html: str) -> str:
        """Wrap table rows in the expected outer HTML structure."""
        return (
            "<html><body>"
            '<table class="table-hoverRowspan"><tbody>' + rows_html + "</tbody></table>"
            "</body></html>"
        )

    @staticmethod
    def _hour_cell(name: str, time: str) -> str:
        return f"<td><b>{name}</b><small>{time}</small></td>"

    @staticmethod
    def _lesson(subject: str, teacher: str, rowspan: int = 1) -> str:
        rs = f' rowspan="{rowspan}"' if rowspan > 1 else ""
        return (
            f'<td{rs}><div class="stunde" title="{subject}">'
            f"<b>{subject}</b><small>{teacher}</small></div></td>"
        )

    @staticmethod
    def _empty() -> str:
        return "<td></td>"

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_single_hour_lessons_correct_days(self):
        """Single-hour lessons (no rowspan) are assigned to the correct days."""
        html = self._wrap(
            "<tr>"
            + self._hour_cell("1. Stunde", "07:45 - 08:30")
            + self._lesson("MAT", "Mül")  # Montag
            + self._empty()  # Dienstag
            + self._lesson("DEU", "Sch")  # Mittwoch
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
        )
        entries = self._parse(html)
        assert len(entries) == 2
        assert entries[0] == {
            "hour": "1. Stunde",
            "time": "07:45 - 08:30",
            "day": "Montag",
            "subject": "MAT",
            "teacher": "Mül",
            "duration": 1,
        }
        assert entries[1]["day"] == "Mittwoch"
        assert entries[1]["subject"] == "DEU"
        assert entries[1]["duration"] == 1

    def test_double_period_correct_day(self):
        """A double-period lesson (rowspan=2) gets the correct day and duration=2."""
        html = self._wrap(
            "<tr>"
            + self._hour_cell("2. Stunde", "08:35 - 09:20")
            + self._empty()  # Montag empty
            + self._lesson("ENG", "Web", rowspan=2)  # Dienstag, spans 2 hours
            + self._empty()  # Mittwoch
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
            + "<tr>"
            + self._hour_cell("3. Stunde", "09:25 - 10:10")
            # Dienstag slot is occupied by rowspan → only 4 day cells here
            + self._empty()  # Montag
            + self._empty()  # Mittwoch
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
        )
        entries = self._parse(html)
        eng = next(e for e in entries if e["subject"] == "ENG")
        assert eng["day"] == "Dienstag", f"Expected Dienstag, got {eng['day']}"
        assert eng["duration"] == 2

    def test_subsequent_entries_correct_day_after_rowspan(self):
        """Entries after a rowspan cell in the same row are on the correct day.

        This is the main regression: without the fix, PHY would be mapped to
        Montag instead of Dienstag because the rowspan cell shifts indices.
        """
        html = self._wrap(
            "<tr>"
            + self._hour_cell("2. Stunde", "08:35 - 09:20")
            + self._lesson("ENG", "Web", rowspan=2)  # Montag, spans 2 hours
            + self._empty()  # Dienstag
            + self._empty()  # Mittwoch
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
            + "<tr>"
            + self._hour_cell("3. Stunde", "09:25 - 10:10")
            # Montag is occupied by ENG rowspan → only 4 day cells
            + self._lesson("PHY", "Kle")  # should be Dienstag
            + self._empty()  # Mittwoch
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
        )
        entries = self._parse(html)
        phy = next(e for e in entries if e["subject"] == "PHY")
        assert phy["day"] == "Dienstag", (
            f"PHY should be on Dienstag after ENG rowspan on Montag, "
            f"but got: {phy['day']}"
        )
        assert phy["duration"] == 1

    def test_triple_period(self):
        """A triple-period lesson (rowspan=3) has duration=3."""
        html = self._wrap(
            "<tr>"
            + self._hour_cell("1. Stunde", "07:45 - 08:30")
            + self._lesson("SPO", "Bau", rowspan=3)  # Montag, 3 hours
            + self._empty() * 4
            + "</tr>"
            + "<tr>"
            + self._hour_cell("2. Stunde", "08:35 - 09:20")
            + self._empty() * 4
            + "</tr>"
            + "<tr>"
            + self._hour_cell("3. Stunde", "09:25 - 10:10")
            + self._empty() * 4
            + "</tr>"
        )
        entries = self._parse(html)
        spo = next(e for e in entries if e["subject"] == "SPO")
        assert spo["duration"] == 3
        assert spo["day"] == "Montag"

    def test_multiple_rowspans_same_row(self):
        """Two rowspan cells in the same row both get correct days."""
        html = self._wrap(
            "<tr>"
            + self._hour_cell("1. Stunde", "07:45 - 08:30")
            + self._lesson("MAT", "Mül", rowspan=2)  # Montag
            + self._empty()  # Dienstag
            + self._lesson("DEU", "Sch", rowspan=2)  # Mittwoch
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
            + "<tr>"
            + self._hour_cell("2. Stunde", "08:35 - 09:20")
            # Montag and Mittwoch occupied → 3 day cells remain
            + self._empty()  # Dienstag
            + self._empty()  # Donnerstag
            + self._empty()  # Freitag
            + "</tr>"
        )
        entries = self._parse(html)
        mat = next(e for e in entries if e["subject"] == "MAT")
        deu = next(e for e in entries if e["subject"] == "DEU")
        assert mat["day"] == "Montag"
        assert mat["duration"] == 2
        assert deu["day"] == "Mittwoch"
        assert deu["duration"] == 2
