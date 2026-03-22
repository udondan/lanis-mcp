#!/usr/bin/env python3
"""MCP server for Schulportal Hessen (Lanis).

Exposes Lanis portal features as MCP tools so that LLMs can interact
with the German school portal Schulportal Hessen.

Required environment variables (one of the two authentication modes):

  Mode 1 – username + password:
    LANIS_SCHOOL_ID   (or LANIS_SCHOOL_NAME + LANIS_SCHOOL_CITY)
    LANIS_USERNAME
    LANIS_PASSWORD

  Mode 2 – session cookie (no password needed, faster):
    LANIS_SCHOOL_ID
    LANIS_SESSION_ID
"""

import json
import re
from datetime import datetime, date
from enum import Enum
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, ConfigDict
from selectolax.parser import HTMLParser as _HTMLParser

import lanisapi.functions.schools as _lanisapi_schools
from lanisapi.helpers.request import Request as _Request

from lanis_mcp.client import get_client, reset_client

_LANIS_BASE = "https://start.schulportal.hessen.de"


mcp = FastMCP("lanis_mcp")

CHARACTER_LIMIT = 25_000


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


def _handle_error(e: Exception) -> str:
    """Return a consistent, human-readable error string."""
    if "ForceNewAuthentication" in type(e).__name__:
        reset_client()
        return (
            "Error: Session expired. The client has been reset. "
            "Please retry the request."
        )
    return f"Error: {type(e).__name__}: {e}"


def _to_str(value: Any) -> str:
    """Safely convert any value to a non-None string."""
    return str(value) if value is not None else ""


def _truncate(text: str) -> str:
    """Truncate the response if it exceeds CHARACTER_LIMIT."""
    if len(text) > CHARACTER_LIMIT:
        return (
            text[:CHARACTER_LIMIT]
            + "\n\n[Response truncated. Use filters to narrow results.]"
        )
    return text


# ---------------------------------------------------------------------------
# Tool: lanis_get_schools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_schools",
    annotations=ToolAnnotations(
        title="Get All Lanis Schools",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_schools(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return all schools registered in Schulportal Hessen (Lanis).

    Fetches the complete list of schools with their ID, name, and city.
    This tool does NOT require authentication and can be used to look up
    the school ID needed for configuring Lanis credentials.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of schools. JSON schema:
        {
            "count": int,
            "schools": [
                {
                    "id": str,
                    "name": str,
                    "city": str
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API failure
        - Returns "No schools found." if the list is empty
    """
    try:
        schools = _lanisapi_schools._get_schools()

        if not schools:
            return "No schools found."

        if response_format == ResponseFormat.JSON:
            data = {
                "count": len(schools),
                "schools": [
                    {
                        "id": _to_str(s.get("Id")),
                        "name": _to_str(s.get("Name")),
                        "city": _to_str(s.get("Ort")),
                    }
                    for s in schools
                ],
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [
            "# Schulen im Schulportal Hessen",
            "",
            f"_{len(schools)} Schule(n)_",
            "",
        ]
        for s in schools:
            name = _to_str(s.get("Name"))
            city = _to_str(s.get("Ort"))
            school_id = _to_str(s.get("Id"))
            lines.append(f"- **{name}** ({city}) — ID: `{school_id}`")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_substitution_plan
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_substitution_plan",
    annotations=ToolAnnotations(
        title="Get Substitution Plan (Vertretungsplan)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_substitution_plan(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return today's substitution plan (Vertretungsplan) from Lanis.

    Fetches all substitutions for the current school day including class,
    subject, room, teacher/substitute, and any notices.

    Args:
        response_format: Output format - 'markdown' (default, human-readable)
                         or 'json' (machine-readable).

    Returns:
        Substitution plan data with the following structure per substitution:
        - substitute: Abbreviation of the substitute teacher
        - teacher: Abbreviation of the original teacher
        - hours: Which school hours are affected (e.g. "3-4")
        - class_name: Affected class(es)
        - subject: Subject name (may be empty)
        - room: Room number/name
        - notice: Additional information

        JSON schema:
        {
            "date": "YYYY-MM-DD",
            "info": str,           # General info box ("Allgemein"), may be empty
            "substitutions": [
                {
                    "substitute": str,
                    "teacher": str,
                    "hours": str,
                    "class_name": str,
                    "subject": str,
                    "room": str,
                    "notice": str
                }
            ]
        }

    Error Handling:
        - Returns "Error: Session expired..." if session needs renewal
        - Returns "No substitutions today." if there are none
    """
    try:
        client = get_client()
        plan = client.get_substitution_plan()

        subs = plan.substitutions or []
        plan_date = plan.date.strftime("%Y-%m-%d") if plan.date else "unknown"
        info = _to_str(plan.info)

        if not subs:
            return f"No substitutions today ({plan_date})."

        if response_format == ResponseFormat.JSON:
            data = {
                "date": plan_date,
                "info": info,
                "substitutions": [
                    {
                        "substitute": _to_str(s.substitute),
                        "teacher": _to_str(s.teacher),
                        "hours": _to_str(s.hours),
                        "class_name": _to_str(s.class_name),
                        "subject": _to_str(s.subject),
                        "room": _to_str(s.room),
                        "notice": _to_str(s.notice),
                    }
                    for s in subs
                ],
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [f"# Vertretungsplan – {plan_date}", ""]
        if info:
            lines += [f"**Allgemein:** {info}", ""]
        lines.append(f"_{len(subs)} Vertretung(en)_")
        lines.append("")

        for s in subs:
            parts = []
            if s.class_name:
                parts.append(f"**Klasse:** {s.class_name}")
            if s.hours:
                parts.append(f"**Stunde:** {s.hours}")
            if s.subject:
                parts.append(f"**Fach:** {s.subject}")
            if s.room:
                parts.append(f"**Raum:** {s.room}")
            if s.teacher:
                parts.append(f"**Lehrer:** {s.teacher}")
            if s.substitute:
                parts.append(f"**Vertretung:** {s.substitute}")
            if s.notice:
                parts.append(f"**Hinweis:** {s.notice}")
            lines.append("- " + " | ".join(parts))

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_calendar
# ---------------------------------------------------------------------------


class CalendarInput(BaseModel):
    """Input for fetching calendar events in a date range."""

    model_config = ConfigDict(str_strip_whitespace=True)

    start: str = Field(
        ...,
        description="Start date in YYYY-MM-DD format (e.g. '2024-01-01')",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    end: str = Field(
        ...,
        description="End date in YYYY-MM-DD format (e.g. '2024-01-31')",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )
    include_responsible: bool = Field(
        default=False,
        description=(
            "If True, fetch the responsible person for each event. "
            "Warning: makes one extra API call per event and may be slow."
        ),
    )


@mcp.tool(
    name="get_calendar",
    annotations=ToolAnnotations(
        title="Get Calendar Events",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_calendar(params: CalendarInput) -> str:
    """Return calendar events from Lanis for a given date range.

    Fetches school calendar events (Kalender) between the specified
    start and end dates.

    Args:
        params (CalendarInput): Validated input parameters:
            - start (str): Start date as YYYY-MM-DD
            - end (str): End date as YYYY-MM-DD
            - response_format (str): 'markdown' (default) or 'json'
            - include_responsible (bool): If True, fetch the responsible person
              for each event. Warning: makes one extra API call per event.

    Returns:
        Calendar events for the date range. JSON schema:
        {
            "start": "YYYY-MM-DD",
            "end": "YYYY-MM-DD",
            "count": int,
            "events": [
                {
                    "title": str,
                    "description": str,
                    "place": str,
                    "start": "YYYY-MM-DD HH:MM",
                    "end": "YYYY-MM-DD HH:MM",
                    "whole_day": bool,
                    "responsible": str   # only present when include_responsible=True
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No events found ..." if calendar is empty
    """
    try:
        start_dt = datetime.strptime(params.start, "%Y-%m-%d")
        end_dt = datetime.strptime(params.end, "%Y-%m-%d")
    except ValueError as e:
        return f"Error: Invalid date format – {e}"

    try:
        client = get_client()
        calendar = client.get_calendar(start_dt, end_dt)

        events = calendar.events or []
        if not events:
            return f"No events found between {params.start} and {params.end}."

        def _fmt_dt(dt: Any) -> str:
            if isinstance(dt, datetime):
                return dt.strftime("%Y-%m-%d %H:%M")
            if isinstance(dt, date):
                return dt.strftime("%Y-%m-%d")
            return _to_str(dt)

        def _get_responsible(ev: Any) -> str:
            try:
                return _to_str(ev.responsible())
            except Exception:
                return ""

        if params.response_format == ResponseFormat.JSON:
            event_list = []
            for ev in events:
                entry = {
                    "title": _to_str(ev.title),
                    "description": _to_str(ev.description),
                    "place": _to_str(ev.place),
                    "start": _fmt_dt(ev.start),
                    "end": _fmt_dt(ev.end),
                    "whole_day": bool(ev.whole_day),
                }
                if params.include_responsible:
                    entry["responsible"] = _get_responsible(ev)
                event_list.append(entry)
            data = {
                "start": params.start,
                "end": params.end,
                "count": len(events),
                "events": event_list,
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [
            f"# Kalender: {params.start} – {params.end}",
            "",
            f"_{len(events)} Termin(e)_",
            "",
        ]
        for ev in events:
            header = _to_str(ev.title) or "(kein Titel)"
            lines.append(f"## {header}")
            if ev.whole_day:
                lines.append(f"- **Datum:** {_fmt_dt(ev.start)} (ganztägig)")
            else:
                lines.append(f"- **Von:** {_fmt_dt(ev.start)}")
                lines.append(f"- **Bis:** {_fmt_dt(ev.end)}")
            if ev.place:
                lines.append(f"- **Ort:** {_to_str(ev.place)}")
            if ev.description:
                lines.append(f"- **Beschreibung:** {_to_str(ev.description)}")
            if params.include_responsible:
                responsible = _get_responsible(ev)
                if responsible:
                    lines.append(f"- **Verantwortlich:** {responsible}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="get_calendar_of_month",
    annotations=ToolAnnotations(
        title="Get Current Month Calendar Events",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_calendar_of_month(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
    include_responsible: bool = False,
) -> str:
    """Return all calendar events for the current month from Lanis.

    Convenience shortcut for lanis_get_calendar that automatically uses
    the current month's date range.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.
        include_responsible: If True, fetch the responsible person for each
            event. Warning: makes one extra API call per event and may be slow.

    Returns:
        Same structure as lanis_get_calendar for the current month.
        When include_responsible=True, each event also includes a
        'responsible' field with the responsible person's name.

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No events this month." if calendar is empty
    """
    try:
        client = get_client()
        calendar = client.get_calendar_of_month()

        events = calendar.events or []
        if not events:
            return "No events this month."

        def _fmt_dt(dt: Any) -> str:
            if isinstance(dt, datetime):
                return dt.strftime("%Y-%m-%d %H:%M")
            if isinstance(dt, date):
                return dt.strftime("%Y-%m-%d")
            return _to_str(dt)

        def _get_responsible(ev: Any) -> str:
            try:
                return _to_str(ev.responsible())
            except Exception:
                return ""

        now = datetime.now()
        month_label = now.strftime("%B %Y")

        if response_format == ResponseFormat.JSON:
            event_list = []
            for ev in events:
                entry = {
                    "title": _to_str(ev.title),
                    "description": _to_str(ev.description),
                    "place": _to_str(ev.place),
                    "start": _fmt_dt(ev.start),
                    "end": _fmt_dt(ev.end),
                    "whole_day": bool(ev.whole_day),
                }
                if include_responsible:
                    entry["responsible"] = _get_responsible(ev)
                event_list.append(entry)
            data = {
                "month": now.strftime("%Y-%m"),
                "count": len(events),
                "events": event_list,
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [f"# Kalender – {month_label}", "", f"_{len(events)} Termin(e)_", ""]
        for ev in events:
            header = _to_str(ev.title) or "(kein Titel)"
            lines.append(f"## {header}")
            if ev.whole_day:
                lines.append(f"- **Datum:** {_fmt_dt(ev.start)} (ganztägig)")
            else:
                lines.append(f"- **Von:** {_fmt_dt(ev.start)}")
                lines.append(f"- **Bis:** {_fmt_dt(ev.end)}")
            if ev.place:
                lines.append(f"- **Ort:** {_to_str(ev.place)}")
            if ev.description:
                lines.append(f"- **Beschreibung:** {_to_str(ev.description)}")
            if include_responsible:
                responsible = _get_responsible(ev)
                if responsible:
                    lines.append(f"- **Verantwortlich:** {responsible}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_tasks
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_tasks",
    annotations=ToolAnnotations(
        title="Get Tasks / Homework (Mein Unterricht)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_tasks(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return all tasks and homework from the 'Mein Unterricht' section of Lanis.

    Fetches tasks assigned to the user including subject, teacher, description,
    and download links for attachments.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of tasks. JSON schema:
        {
            "count": int,
            "tasks": [
                {
                    "title": str,
                    "date": "YYYY-MM-DD",
                    "subject_name": str,
                    "teacher": str,
                    "description": str,       # may be empty
                    "details": str,           # may be empty
                    "attachments": [str],     # list of attachment filenames
                    "attachment_url": str     # zip download URL, may be empty
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No tasks found." if there are none
    """
    try:
        client = get_client()
        tasks = client.get_tasks()

        if not tasks:
            return "No tasks found."

        def _fmt_date(dt: Any) -> str:
            if isinstance(dt, (datetime, date)):
                return dt.strftime("%Y-%m-%d")
            return _to_str(dt)

        if response_format == ResponseFormat.JSON:
            data = {
                "count": len(tasks),
                "tasks": [
                    {
                        "title": _to_str(t.title),
                        "date": _fmt_date(t.date),
                        "subject_name": _to_str(t.subject_name),
                        "teacher": _to_str(t.teacher),
                        "description": _to_str(t.description),
                        "details": _to_str(t.details),
                        "attachments": list(t.attachment or []),
                        "attachment_url": _to_str(t.attachment_url),
                    }
                    for t in tasks
                ],
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = ["# Mein Unterricht – Aufgaben", "", f"_{len(tasks)} Aufgabe(n)_", ""]
        for t in tasks:
            lines.append(f"## {_to_str(t.title) or '(kein Titel)'}")
            lines.append(f"- **Datum:** {_fmt_date(t.date)}")
            lines.append(f"- **Fach:** {_to_str(t.subject_name)}")
            lines.append(f"- **Lehrer:** {_to_str(t.teacher)}")
            if t.description:
                lines.append(f"- **Beschreibung:** {_to_str(t.description)}")
            if t.details:
                lines.append(f"- **Details:** {_to_str(t.details)}")
            if t.attachment:
                lines.append(f"- **Anhänge:** {', '.join(t.attachment)}")
            if t.attachment_url:
                lines.append(f"- **Download:** {_to_str(t.attachment_url)}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_conversations
# ---------------------------------------------------------------------------


class ConversationsInput(BaseModel):
    """Input for fetching conversations."""

    model_config = ConfigDict()

    number: int = Field(
        default=10,
        description=(
            "Number of conversations to fetch (default: 10). "
            "Use -1 to fetch all (may be slow and spam Lanis servers)."
        ),
        ge=-1,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )


@mcp.tool(
    name="get_conversations",
    annotations=ToolAnnotations(
        title="Get Conversations / Messages (Nachrichten)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_conversations(params: ConversationsInput) -> str:
    """Return conversations from the 'Nachrichten' section of Lanis.

    Fetches message threads including sender, receivers, subject, and content.

    Args:
        params (ConversationsInput): Validated input parameters:
            - number (int): How many conversations to fetch (default: 10, -1 = all)
            - response_format (str): 'markdown' (default) or 'json'

    Returns:
        List of conversations. JSON schema:
        {
            "count": int,
            "conversations": [
                {
                    "id": str,
                    "title": str,
                    "teacher": str,
                    "creation_date": str,
                    "newest_date": str,
                    "unread": bool,
                    "receivers": [str],
                    "special_receivers": [str],
                    "content": str
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No conversations found." if there are none
    """
    try:
        client = get_client()
        conversations = client.get_conversations(number=params.number)

        if not conversations:
            return "No conversations found."

        if params.response_format == ResponseFormat.JSON:
            data = {
                "count": len(conversations),
                "conversations": [
                    {
                        "id": _to_str(c.id),
                        "title": _to_str(c.title),
                        "teacher": _to_str(c.teacher),
                        "creation_date": _to_str(c.creation_date),
                        "newest_date": _to_str(c.newest_date),
                        "unread": bool(c.unread),
                        "receivers": list(c.receivers or []),
                        "special_receivers": list(c.special_receivers or []),
                        "content": _to_str(c.content),
                    }
                    for c in conversations
                ],
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = ["# Nachrichten", "", f"_{len(conversations)} Nachricht(en)_", ""]
        for c in conversations:
            unread_marker = " 🔵" if c.unread else ""
            lines.append(f"## {_to_str(c.title)}{unread_marker}")
            lines.append(f"- **Von:** {_to_str(c.teacher)}")
            lines.append(f"- **Erstellt:** {_to_str(c.creation_date)}")
            lines.append(f"- **Neueste Antwort:** {_to_str(c.newest_date)}")
            if c.receivers:
                lines.append(f"- **Empfänger:** {', '.join(c.receivers)}")
            if c.special_receivers:
                lines.append(f"- **Gruppen:** {', '.join(c.special_receivers)}")
            if c.content:
                # Limit individual message content to avoid overwhelming output
                content = _to_str(c.content)
                if len(content) > 500:
                    content = content[:500] + "…"
                lines.append(f"\n  {content}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_apps
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_apps",
    annotations=ToolAnnotations(
        title="Get All Lanis Web Applets",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_apps(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return all web applets (Apps) available in the user's Lanis portal.

    Lists every app tile visible on the Lanis dashboard including name,
    link, colour, icon symbol, and which folder/category it belongs to.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of apps. JSON schema:
        {
            "count": int,
            "apps": [
                {
                    "name": str,
                    "link": str,
                    "colour": str,
                    "symbol": str,
                    "folders": [str]   # category/folder names
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No apps found." if none are available
    """
    try:
        client = get_client()
        apps = client.get_apps()

        if not apps:
            return "No apps found."

        if response_format == ResponseFormat.JSON:
            data = {
                "count": len(apps),
                "apps": [
                    {
                        "name": _to_str(a.name),
                        "link": _to_str(a.link),
                        "colour": _to_str(a.colour),
                        "symbol": _to_str(a.symbol),
                        "folders": [_to_str(f.name) for f in (a.folder or [])],
                    }
                    for a in apps
                ],
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = ["# Lanis Apps", "", f"_{len(apps)} App(s)_", ""]
        for a in apps:
            folders = ", ".join(_to_str(f.name) for f in (a.folder or []))
            lines.append(f"### {_to_str(a.name)}")
            if folders:
                lines.append(f"- **Kategorie:** {folders}")
            if a.link:
                lines.append(f"- **Link:** {_to_str(a.link)}")
            if a.colour:
                lines.append(f"- **Farbe:** {_to_str(a.colour)}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


@mcp.tool(
    name="get_available_apps",
    annotations=ToolAnnotations(
        title="Get Supported Apps Available at This School",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_available_apps() -> str:
    """Return the list of LanisAPI-supported apps that are available at this school.

    The LanisAPI library supports a specific subset of Lanis applets:
    Kalender, Mein Unterricht, Nachrichten - Beta-Version, Vertretungsplan.
    This tool checks which of those are enabled for the authenticated user's school.

    Returns:
        Plain text list of supported app names available at this school,
        or a message indicating none are supported.

    Error Handling:
        - Returns "Error: ..." on API or auth failure
    """
    try:
        client = get_client()
        available = client.get_available_apps()
        if not available:
            return "No supported apps are available at your school."
        lines = ["Supported apps available at your school:", ""]
        for app in available:
            lines.append(f"- {app}")
        return "\n".join(lines)
    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_folders
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_folders",
    annotations=ToolAnnotations(
        title="Get Lanis Dashboard Folders",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_folders(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return all folder/category groupings from the Lanis dashboard.

    Fetches the organizational folders that group apps on the Lanis portal.
    Each folder has a name, a symbol (Font Awesome / Glyphicons icon), and
    an optional colour.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of folders. JSON schema:
        {
            "count": int,
            "folders": [
                {
                    "name": str,
                    "symbol": str,
                    "colour": str   # may be empty if no colour is set
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No folders found." if none are available
    """
    try:
        client = get_client()
        folders = client.get_folders()

        if not folders:
            return "No folders found."

        if response_format == ResponseFormat.JSON:
            data = {
                "count": len(folders),
                "folders": [
                    {
                        "name": _to_str(f.name),
                        "symbol": _to_str(f.symbol),
                        "colour": _to_str(f.colour),
                    }
                    for f in folders
                ],
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = ["# Lanis Ordner", "", f"_{len(folders)} Ordner_", ""]
        for f in folders:
            parts = [f"**{_to_str(f.name)}**"]
            if f.symbol:
                parts.append(f"Symbol: {_to_str(f.symbol)}")
            if f.colour:
                parts.append(f"Farbe: {_to_str(f.colour)}")
            lines.append("- " + " | ".join(parts))

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_check_app_availability
# ---------------------------------------------------------------------------

_SUPPORTED_APPS = [
    "Kalender",
    "Mein Unterricht",
    "Nachrichten - Beta-Version",
    "Vertretungsplan",
]


@mcp.tool(
    name="check_app_availability",
    annotations=ToolAnnotations(
        title="Check If a Specific App Is Available",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_check_app_availability(
    app_name: str,
) -> str:
    """Check whether a specific Lanis app is available at the user's school.

    Checks one of the four LanisAPI-supported apps to see if it is enabled
    at the authenticated user's school.

    Args:
        app_name: The app to check. Must be one of:
            - "Kalender"
            - "Mein Unterricht"
            - "Nachrichten - Beta-Version"
            - "Vertretungsplan"

    Returns:
        A plain-text message indicating whether the app is available.

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "Error: Unknown app ..." for invalid app names
    """
    if app_name not in _SUPPORTED_APPS:
        valid = ", ".join(f'"{a}"' for a in _SUPPORTED_APPS)
        return f'Error: Unknown app "{app_name}". Valid options are: {valid}'

    try:
        client = get_client()
        available = client.get_app_availability(app_name)
        if available:
            return f'"{app_name}" is available at your school.'
        return f'"{app_name}" is not available at your school.'

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_timetable
# ---------------------------------------------------------------------------

_DAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]


@mcp.tool(
    name="get_timetable",
    annotations=ToolAnnotations(
        title="Get Timetable (Stundenplan)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_timetable(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return the weekly timetable (Stundenplan) from Lanis.

    Fetches the current class timetable showing which subjects are taught
    on which day and hour, including room and teacher information.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        Timetable data. JSON schema:
        {
            "class_name": str,
            "valid_from": "YYYY-MM-DD",
            "entries": [
                {
                    "hour": str,        # e.g. "erste Stunde"
                    "time": str,        # e.g. "08:00 - 08:45"
                    "day": str,         # e.g. "Montag"
                    "subject": str,     # subject code
                    "room": str,        # room number/name
                    "teacher": str,     # teacher abbreviation
                    "info": str         # full info from title attribute
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No timetable entries found." if the timetable is empty
    """
    try:
        get_client()  # ensure authenticated
        resp = _Request.client.get(
            f"{_LANIS_BASE}/stundenplan.php",
            follow_redirects=True,
        )
        tree = _HTMLParser(resp.text)

        # Extract class name from title
        title_node = tree.css_first("title")
        title_text = title_node.text(strip=True) if title_node else ""
        class_name = title_text.split(" - ")[0].strip() if " - " in title_text else ""

        # Extract plan validity date
        plan_div = tree.css_first("div.plan[data-date]")
        valid_from = plan_div.attributes.get("data-date", "") if plan_div else ""

        # Parse timetable rows
        entries: list[dict[str, str]] = []
        rows = tree.css("table.table-hoverRowspan tbody tr")

        for row in rows:
            cells = row.css("td")
            if not cells:
                continue

            # First cell: hour label and time
            hour_cell = cells[0]
            hour_name_node = hour_cell.css_first("b")
            hour_name = hour_name_node.text(strip=True) if hour_name_node else ""
            time_node = hour_cell.css_first("small")
            time_text = time_node.text(strip=True) if time_node else ""

            if not hour_name:
                continue

            # Remaining cells: Mon–Fri (index 1–5)
            for day_idx, cell in enumerate(cells[1:], 0):
                if day_idx >= len(_DAYS):
                    break
                stunde = cell.css_first("div.stunde")
                if not stunde:
                    continue

                subject_node = stunde.css_first("b")
                subject = subject_node.text(strip=True) if subject_node else ""
                teacher_node = stunde.css_first("small")
                teacher = teacher_node.text(strip=True) if teacher_node else ""
                info = _to_str(stunde.attributes.get("title", ""))

                # Extract room: text between subject and teacher
                full_text = stunde.text(strip=True)
                room = ""
                if subject and teacher and full_text:
                    # Remove subject and teacher from full text to get room
                    room_raw = full_text.replace(subject, "", 1).replace(teacher, "", 1)
                    room = room_raw.strip()

                entries.append(
                    {
                        "hour": hour_name,
                        "time": time_text,
                        "day": _DAYS[day_idx],
                        "subject": subject,
                        "room": room,
                        "teacher": teacher,
                        "info": info,
                    }
                )

        if not entries:
            return "No timetable entries found."

        if response_format == ResponseFormat.JSON:
            data = {
                "class_name": class_name,
                "valid_from": valid_from,
                "entries": entries,
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [
            f"# Stundenplan – {class_name}",
            "",
        ]
        if valid_from:
            lines.append(f"_Gültig ab: {valid_from}_")
            lines.append("")

        # Group by day for readable output
        for day in _DAYS:
            day_entries = [e for e in entries if e["day"] == day]
            if not day_entries:
                continue
            lines.append(f"## {day}")
            for e in day_entries:
                parts = [f"**{e['hour']}**"]
                if e["time"]:
                    parts.append(f"({e['time']})")
                if e["subject"]:
                    parts.append(f"– {e['subject']}")
                if e["room"]:
                    parts.append(f"Raum {e['room']}")
                if e["teacher"]:
                    parts.append(f"bei {e['teacher']}")
                lines.append("- " + " ".join(parts))
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_learning_groups
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_learning_groups",
    annotations=ToolAnnotations(
        title="Get Learning Groups (Lerngruppen)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_learning_groups(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return the learning groups (Lerngruppen) the user belongs to.

    Fetches all learning groups/courses the authenticated user is enrolled in,
    including subject name, course code, semester, and teacher information.

    Use this tool to:
    - List all courses/subjects the user is enrolled in
    - Look up which teacher is responsible for a given subject or course
    - Resolve teacher abbreviations to full names (the teacher field contains
      both the full name and the abbreviation used in substitution plans)

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of learning groups. JSON schema:
        {
            "count": int,
            "groups": [
                {
                    "id": str,
                    "semester": str,
                    "course_name": str,
                    "course_code": str,
                    "teacher": str   # full name and/or abbreviation
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No learning groups found." if there are none
    """
    try:
        get_client()  # ensure authenticated
        resp = _Request.client.get(
            f"{_LANIS_BASE}/lerngruppen.php",
            follow_redirects=True,
        )
        tree = _HTMLParser(resp.text)

        table = tree.css_first("table#LGs")
        if not table:
            return "No learning groups found."

        rows = table.css("tbody tr")
        groups: list[dict[str, str]] = []

        for row in rows:
            cells = row.css("td")
            if len(cells) < 3:
                continue

            group_id = _to_str(row.attributes.get("data-id", ""))
            semester = cells[0].text(strip=True)

            # Course cell: name text + code in <small>
            # HTML: "Deutsch 05e <small>(052D05 - GYM)</small>"
            course_cell = cells[1]
            small_node = course_cell.css_first("small")
            course_code_raw = small_node.text(strip=True) if small_node else ""
            # Strip surrounding parentheses from code: "(052D05 - GYM)" → "052D05 - GYM"
            course_code = re.sub(r"^\s*\(\s*|\s*\)\s*$", "", course_code_raw).strip()
            # Remove the small tag text to get just the course name
            course_name = course_cell.text(strip=True)
            if course_code_raw:
                course_name = course_name.replace(course_code_raw, "").strip()
            # Clean up any trailing parentheses that may remain
            course_name = re.sub(r"\s*\(\s*\)\s*$", "", course_name).strip()

            # Teacher cell: button with title="Full Name (Abbrev)"
            teacher_btn = cells[2].css_first("button[title]")
            teacher = (
                _to_str(teacher_btn.attributes.get("title", "")) if teacher_btn else ""
            )

            groups.append(
                {
                    "id": group_id,
                    "semester": semester,
                    "course_name": course_name,
                    "course_code": course_code,
                    "teacher": teacher,
                }
            )

        if not groups:
            return "No learning groups found."

        if response_format == ResponseFormat.JSON:
            data = {"count": len(groups), "groups": groups}
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = ["# Lerngruppen", "", f"_{len(groups)} Lerngruppe(n)_", ""]
        for g in groups:
            lines.append(f"## {g['course_name']}")
            if g["course_code"]:
                lines.append(f"- **Kurs:** {g['course_code']}")
            lines.append(f"- **Halbjahr:** {g['semester']}")
            if g["teacher"]:
                lines.append(f"- **Lehrkraft:** {g['teacher']}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_file_storage
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_file_storage",
    annotations=ToolAnnotations(
        title="Get File Storage (Dateispeicher)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_file_storage(
    folder_id: Optional[str] = None,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return the contents of the school file storage (Dateispeicher).

    Lists folders and files in the Lanis file storage system. By default
    returns the root level. Use folder_id to navigate into sub-folders.

    Args:
        folder_id: Optional folder ID to navigate into. Omit for root level.
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        Folder contents. JSON schema:
        {
            "folder_id": str,
            "folder_name": str,
            "folders": [
                {
                    "id": str,
                    "name": str,
                    "description": str
                }
            ],
            "files": [
                {
                    "id": str,
                    "name": str,
                    "description": str,
                    "download_url": str
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No items found." if the folder is empty
    """
    try:
        get_client()  # ensure authenticated

        if folder_id:
            url = f"{_LANIS_BASE}/dateispeicher.php"
            params: dict[str, str] = {"a": "view", "folder": folder_id}
        else:
            url = f"{_LANIS_BASE}/dateispeicher.php"
            params = {}

        resp = _Request.client.get(url, params=params, follow_redirects=True)
        tree = _HTMLParser(resp.text)

        # Get current folder name from h1
        h1 = tree.css_first("#content h1")
        current_folder_name = h1.text(strip=True) if h1 else "Start"
        # Clean up icon text from h1
        current_folder_name = re.sub(r"^\s*\S+\s*", "", current_folder_name).strip()
        if not current_folder_name:
            current_folder_name = "Start"

        current_folder_id = folder_id or "0"

        # Parse sub-folders
        folders: list[dict[str, str]] = []
        for folder_div in tree.css("div.thumbnail.folder"):
            fid = _to_str(folder_div.attributes.get("data-id", ""))
            fname = _to_str(folder_div.attributes.get("data-name", ""))
            desc_node = folder_div.css_first("p.desc small")
            fdesc = desc_node.text(strip=True) if desc_node else ""
            if fid and fname:
                folders.append({"id": fid, "name": fname, "description": fdesc})

        # Parse files (non-folder thumbnails with data-id)
        files: list[dict[str, str]] = []
        for file_row in tree.css("tr[data-id][data-name]"):
            fid = _to_str(file_row.attributes.get("data-id", ""))
            fname = _to_str(file_row.attributes.get("data-name", ""))
            # Try to find download link
            dl_link = file_row.css_first(
                "a[href*='download'], a[href*='dateispeicher']"
            )
            dl_url = _to_str(dl_link.attributes.get("href", "")) if dl_link else ""
            if dl_url and not dl_url.startswith("http"):
                dl_url = f"{_LANIS_BASE}/{dl_url.lstrip('/')}"
            if fid and fname:
                files.append(
                    {
                        "id": fid,
                        "name": fname,
                        "description": "",
                        "download_url": dl_url,
                    }
                )

        if not folders and not files:
            return f"No items found in folder '{current_folder_name}'."

        if response_format == ResponseFormat.JSON:
            data = {
                "folder_id": current_folder_id,
                "folder_name": current_folder_name,
                "folders": folders,
                "files": files,
            }
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [
            f"# Dateispeicher – {current_folder_name}",
            "",
        ]
        if folders:
            lines.append(f"## Ordner ({len(folders)})")
            for f in folders:
                lines.append(f"- **{f['name']}** (ID: `{f['id']}`)")
                if f["description"]:
                    lines.append(f"  _{f['description']}_")
            lines.append("")
        if files:
            lines.append(f"## Dateien ({len(files)})")
            for f in files:
                if f["download_url"]:
                    lines.append(f"- [{f['name']}]({f['download_url']})")
                else:
                    lines.append(f"- **{f['name']}**")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_file_distribution
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_file_distribution",
    annotations=ToolAnnotations(
        title="Get File Distribution / Announcements (Dateiverteilung)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_file_distribution(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return distributed files and announcements (Dateiverteilung / GRB Infos).

    Fetches files that have been distributed to the user via the Lanis
    file distribution system (Dateiverteilung). These are typically
    school-wide announcements or documents shared with specific groups.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of distributed files. JSON schema:
        {
            "count": int,
            "files": [
                {
                    "name": str,
                    "description": str,
                    "download_url": str,
                    "date": str
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No distributed files available." if there are none
    """
    try:
        get_client()  # ensure authenticated
        resp = _Request.client.get(
            f"{_LANIS_BASE}/dateiverteilung.php",
            follow_redirects=True,
        )
        tree = _HTMLParser(resp.text)

        # Check for "no files" alert
        alert = tree.css_first(".alert-error, .alert-danger, .alert-warning")
        if alert:
            alert_text = alert.text(strip=True)
            if "keine" in alert_text.lower() or "nicht" in alert_text.lower():
                return "No distributed files available."

        # Try to parse file listings (table rows or list items)
        files: list[dict[str, str]] = []

        # Look for table rows with file data
        for row in tree.css("table tbody tr[data-id]"):
            cells = row.css("td")
            fname = cells[0].text(strip=True) if cells else ""
            fdesc = cells[1].text(strip=True) if len(cells) > 1 else ""
            fdate = cells[2].text(strip=True) if len(cells) > 2 else ""
            dl_link = row.css_first("a[href]")
            dl_url = _to_str(dl_link.attributes.get("href", "")) if dl_link else ""
            if dl_url and not dl_url.startswith("http"):
                dl_url = f"{_LANIS_BASE}/{dl_url.lstrip('/')}"
            if fname:
                files.append(
                    {
                        "name": fname,
                        "description": fdesc,
                        "download_url": dl_url,
                        "date": fdate,
                    }
                )

        if not files:
            return "No distributed files available."

        if response_format == ResponseFormat.JSON:
            data = {"count": len(files), "files": files}
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [
            "# Dateiverteilung – GRB Infos",
            "",
            f"_{len(files)} Datei(en)_",
            "",
        ]
        for f in files:
            if f["download_url"]:
                lines.append(f"- [{f['name']}]({f['download_url']})")
            else:
                lines.append(f"- **{f['name']}**")
            if f["description"]:
                lines.append(f"  _{f['description']}_")
            if f["date"]:
                lines.append(f"  Datum: {f['date']}")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Tool: lanis_get_votes
# ---------------------------------------------------------------------------


@mcp.tool(
    name="get_votes",
    annotations=ToolAnnotations(
        title="Get Active Votes / Elections (Wahlen)",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def lanis_get_votes(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Return active votes and elections (Wahlen / GRB Wahlen) from Lanis.

    Fetches currently active school votes and elections, such as student
    council elections or other school-wide voting events.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        List of active votes. JSON schema:
        {
            "count": int,
            "votes": [
                {
                    "id": str,
                    "title": str,
                    "description": str,
                    "status": str
                }
            ]
        }

    Error Handling:
        - Returns "Error: ..." on API or auth failure
        - Returns "No active votes." if there are none
    """
    try:
        get_client()  # ensure authenticated
        resp = _Request.client.get(
            f"{_LANIS_BASE}/wahl.php",
            follow_redirects=True,
        )
        tree = _HTMLParser(resp.text)

        # Check for "no active events" message
        wahl_div = tree.css_first("div.modWahl")
        if wahl_div:
            wahl_text = wahl_div.text(strip=True)
            if "keine" in wahl_text.lower() and "aktiv" in wahl_text.lower():
                return "No active votes."

        # Parse vote listings
        votes: list[dict[str, str]] = []

        # Look for vote items (panels, cards, or list items)
        for item in tree.css(
            "div.modWahl .panel, div.modWahl .card, div.modWahl li[data-id], div.modWahl tr[data-id]"
        ):
            vid = _to_str(item.attributes.get("data-id", ""))
            title_node = item.css_first(
                "h3, h4, .panel-title, .card-title, td:first-child"
            )
            vtitle = title_node.text(strip=True) if title_node else ""
            desc_node = item.css_first("p, .description, td:nth-child(2)")
            vdesc = desc_node.text(strip=True) if desc_node else ""
            votes.append(
                {
                    "id": vid,
                    "title": vtitle,
                    "description": vdesc,
                    "status": "active",
                }
            )

        if not votes:
            return "No active votes."

        if response_format == ResponseFormat.JSON:
            data = {"count": len(votes), "votes": votes}
            return _truncate(json.dumps(data, indent=2, ensure_ascii=False))

        lines = [
            "# GRB Wahlen – Aktive Veranstaltungen",
            "",
            f"_{len(votes)} Wahl(en)_",
            "",
        ]
        for v in votes:
            lines.append(f"## {v['title'] or '(kein Titel)'}")
            if v["description"]:
                lines.append(f"_{v['description']}_")
            lines.append(f"- **Status:** {v['status']}")
            lines.append("")

        return _truncate("\n".join(lines))

    except Exception as e:
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server via stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
