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
from datetime import datetime, date
from enum import Enum
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

import lanisapi.functions.schools as _lanisapi_schools

from lanis_mcp.client import get_client, reset_client


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
    name="lanis_get_schools",
    annotations={
        "title": "Get All Lanis Schools",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_substitution_plan",
    annotations={
        "title": "Get Substitution Plan (Vertretungsplan)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_calendar",
    annotations={
        "title": "Get Calendar Events",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_calendar_of_month",
    annotations={
        "title": "Get Current Month Calendar Events",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_tasks",
    annotations={
        "title": "Get Tasks / Homework (Mein Unterricht)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_conversations",
    annotations={
        "title": "Get Conversations / Messages (Nachrichten)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_apps",
    annotations={
        "title": "Get All Lanis Web Applets",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_available_apps",
    annotations={
        "title": "Get Supported Apps Available at This School",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_get_folders",
    annotations={
        "title": "Get Lanis Dashboard Folders",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
    name="lanis_check_app_availability",
    annotations={
        "title": "Check If a Specific App Is Available",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
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
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server via stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
