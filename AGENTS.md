# AGENTS.md — Developer & Agent Guide

This is a Python MCP (Model Context Protocol) server that exposes the German school
portal "Schulportal Hessen (Lanis)" as LLM-callable tools via the FastMCP framework.

## Project Layout

```
src/lanis_mcp/
  __init__.py      # package marker
  client.py        # LanisClient singleton: lazy init, auth, session mgmt, monkey-patch
  server.py        # FastMCP server: all @mcp.tool definitions + shared helpers
tests/
  test_lanis.py    # integration tests (require live credentials)
pyproject.toml     # single source of truth for build, deps, and tool config
```

## Environment Setup

```bash
python -m venv .venv
.venv/bin/pip install -e .
```

Required environment variables (set before running server or tests):

```bash
# Option 1 – username/password
export LANIS_SCHOOL_ID=...
export LANIS_USERNAME=...
export LANIS_PASSWORD=...

# Option 2 – session cookie (faster, no password)
export LANIS_SCHOOL_ID=...
export LANIS_SESSION_ID=...

# Option 3 – school by name/city instead of ID
export LANIS_SCHOOL_NAME=...
export LANIS_SCHOOL_CITY=...
export LANIS_USERNAME=...
export LANIS_PASSWORD=...
```

## Build & Run Commands

| Task           | Command                     |
| -------------- | --------------------------- |
| Run MCP server | `.venv/bin/lanis-mcp`       |
| Build wheel    | `.venv/bin/python -m build` |

## Test Commands

Tests are **integration tests only** — they call the real Lanis API and require
credentials set in the environment. Tests gracefully skip when credentials are absent.

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run a single test class
.venv/bin/pytest tests/test_lanis.py::TestAuthentication -v
.venv/bin/pytest tests/test_lanis.py::TestSubstitutionPlan -v
.venv/bin/pytest tests/test_lanis.py::TestCalendar -v

# Run a single test function
.venv/bin/pytest tests/test_lanis.py::TestAuthentication::test_authenticate -v
.venv/bin/pytest tests/test_lanis.py::TestSubstitutionPlan::test_get_substitution_plan_via_mcp_tool -v
```

Note: `TestSubstitutionPlan` tests skip automatically on weekends (no school plan).

## Lint & Format Commands

Ruff is used for linting and formatting (defaults, no custom config in pyproject.toml):

```bash
.venv/bin/ruff check src/ tests/
.venv/bin/ruff format src/ tests/
```

No other linters or type checkers are currently configured (no mypy, pylint, black, etc.).

## Code Style Guidelines

### Language & Version

- Python ≥ 3.11 required; virtual environment uses Python 3.14
- No TypeScript/JavaScript in the source tree

### Type Annotations

- All functions must have full type annotations (parameters and return types)
- Use `Optional[X]` from `typing` (not `X | None`) for consistency with existing code
- Use `Any` from `typing` when the type is truly dynamic
- Use `tuple[...]` (lowercase) for return tuples, not `Tuple`
- Pydantic `BaseModel` classes are used for all structured MCP tool inputs

### Imports

Order imports in three groups separated by blank lines:

1. Standard library (`os`, `json`, `datetime`, `enum`, `typing`)
2. Third-party (`mcp`, `pydantic`, `lanisapi`, `httpx`)
3. Local (`from lanis_mcp.client import ...`)

Use `import X as _X` for internal/private third-party imports that should not
be part of the public namespace (e.g., `import lanisapi.client as _lanisapi_client`).

### Naming Conventions

- `snake_case` for all functions, variables, and module names
- `PascalCase` for Pydantic models and Enum classes (e.g., `CalendarInput`, `ResponseFormat`)
- Private helpers and module-level singletons: prefix with `_` (e.g., `_client`, `_handle_error`, `_to_str`)
- MCP tool functions: `lanis_<action>` (e.g., `lanis_get_tasks`, `lanis_get_calendar`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `CHARACTER_LIMIT = 25_000`)

### MCP Tool Pattern

Every tool follows this exact structure:

```python
@mcp.tool(
    name="lanis_<action>",
    annotations={
        "title": "Human-Readable Title",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def lanis_<action>(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """One-line summary.

    Full description.

    Args:
        response_format: Output format - 'markdown' (default) or 'json'.

    Returns:
        Description of return value including JSON schema if applicable.

    Error Handling:
        - Returns "Error: ..." on specific failure modes
    """
    try:
        client = get_client()
        # ... fetch data ...
        return _truncate(...)
    except Exception as e:
        return _handle_error(e)
```

For tools with multiple structured inputs, define a Pydantic model:

```python
class MyToolInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    field: str = Field(..., description="...", pattern=r"...")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, ...)

async def lanis_my_tool(params: MyToolInput) -> str: ...
```

### Error Handling

- All tool handlers use a single top-level `try/except Exception as e` block
- Always delegate to `_handle_error(e)` — never format errors inline
- `_handle_error` detects `ForceNewAuthentication` and resets the cached client
- Error strings always start with `"Error: "` (tools and helpers alike)
- Empty-result returns use plain English: `"No tasks found."`, `"No events this month."`
- Swallow exceptions silently only in cleanup paths (e.g., `reset_client` → `client.close()`)

### Output Formatting

- All tool output is passed through `_truncate()` before returning
- Use `_to_str(value)` whenever accessing fields from third-party API objects — never assume non-None
- Markdown output uses `#`/`##`/`###` headings, `**Bold:**` labels, and `- ` list items
- JSON output uses `json.dumps(data, indent=2, ensure_ascii=False)`
- Dates formatted as `YYYY-MM-DD`, datetimes as `YYYY-MM-DD HH:MM`

### Section Dividers in server.py

Separate logical sections (one per tool or group) with a divider comment:

```python
# ---------------------------------------------------------------------------
# Tool: lanis_get_<name>
# ---------------------------------------------------------------------------
```

### Docstrings

- Module-level: describe purpose and required environment variables
- Function-level: one-line summary, then full description, then Args/Returns/Error Handling
- Short private helpers: single-line docstring is sufficient

## Git Workflow

- Never commit directly to the main branch — create a feature branch first
- Use conventional commit messages: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, etc.
- A spell-checker runs on commit; add missing words with `dict-add <word>`
- Always show `git diff` and confirm the commit message before committing
- Never push without explicit confirmation

## Key Architectural Notes

- `_client` in `client.py` is a module-level singleton; use `get_client()` and `reset_client()`
- `client.py` monkey-patches `lanisapi` at import time to fix a cookie-parsing bug — do not remove
- `tests/test_lanis.py` calls `os.chdir()` at module load time (before any imports) so that
  `lanisapi`'s `session.json` is written to a temp directory instead of the project root
- `CHARACTER_LIMIT = 25_000` guards all responses; never bypass `_truncate()`
