"""Lanis client wrapper with lazy initialization and session management."""

import os
from typing import Optional

from lanisapi import LanisClient, LanisAccount, LanisCookie, School


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
