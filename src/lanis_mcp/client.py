"""Lanis client wrapper with lazy initialization and session management."""

import os
from typing import Optional

import httpx
from lanisapi import LanisClient, LanisAccount, LanisCookie, School
from lanisapi.helpers import authentication as _auth
from lanisapi.helpers.request import Request as _Request
from lanisapi.constants import LOGGER as _LOGGER


def _fixed_get_authentication_sid(
    url: str,
    cookies: httpx.Cookies,
    schoolid: str,
) -> httpx.Cookies:
    """Fixed version of lanisapi's get_authentication_sid.

    The original crashes with an IndexError because it parses the set-cookie
    header with hardcoded string splits that break when httpx returns the
    cookies in a different format.  This version uses httpx's built-in cookie
    handling and falls back to robust header parsing.
    """
    response = _Request.head(url, cookies=cookies)

    result = httpx.Cookies()
    result.set("i", schoolid)

    sid_value = response.cookies.get("sid")
    if not sid_value:
        for raw in response.headers.get_list("set-cookie"):
            for field in raw.split(";"):
                field = field.strip()
                if field.lower().startswith("sid="):
                    sid_value = field.split("=", 1)[1]
                    break

    result.set("sid", sid_value)
    _LOGGER.info("Authentication - Get sid: Success.")
    return result


# Patch into lanisapi.client's namespace (where _create_new_session resolves it)
import lanisapi.client as _lanisapi_client

_auth.get_authentication_sid = _fixed_get_authentication_sid
_lanisapi_client.get_authentication_sid = _fixed_get_authentication_sid


_client: Optional[LanisClient] = None


def _get_credentials() -> tuple[
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
]:
    """Read credentials from environment variables.

    Supports two authentication modes:
      1. Username/password: LANIS_SCHOOL_ID (or LANIS_SCHOOL_NAME + LANIS_SCHOOL_CITY),
         LANIS_USERNAME, LANIS_PASSWORD
      2. Session cookie: LANIS_SCHOOL_ID + LANIS_SESSION_ID
    """
    school_id = os.environ.get("LANIS_SCHOOL_ID")
    school_name = os.environ.get("LANIS_SCHOOL_NAME")
    school_city = os.environ.get("LANIS_SCHOOL_CITY")
    username = os.environ.get("LANIS_USERNAME")
    password = os.environ.get("LANIS_PASSWORD")
    session_id = os.environ.get("LANIS_SESSION_ID")
    return school_id, school_name, school_city, username, password, session_id


def get_client() -> LanisClient:
    """Return an authenticated LanisClient, creating and authenticating one if needed."""
    global _client

    if _client is not None:
        return _client

    school_id, school_name, school_city, username, password, session_id = (
        _get_credentials()
    )

    if school_id and session_id:
        # Cookie-based auth (fastest, no password needed)
        auth = LanisCookie(school_id, session_id)
    elif username and password:
        # Username/password auth
        if school_id:
            school = school_id
        elif school_name and school_city:
            school = School(school_name, school_city)
        else:
            raise ValueError(
                "Authentication requires either LANIS_SCHOOL_ID or both "
                "LANIS_SCHOOL_NAME and LANIS_SCHOOL_CITY"
            )
        auth = LanisAccount(school, username, password)
    else:
        raise ValueError(
            "Authentication requires either:\n"
            "  - LANIS_SCHOOL_ID + LANIS_SESSION_ID (cookie auth)\n"
            "  - (LANIS_SCHOOL_ID or LANIS_SCHOOL_NAME + LANIS_SCHOOL_CITY) "
            "+ LANIS_USERNAME + LANIS_PASSWORD"
        )

    _client = LanisClient(auth)
    _client.authenticate()
    return _client


def reset_client() -> None:
    """Reset the cached client (forces re-authentication on next call)."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
