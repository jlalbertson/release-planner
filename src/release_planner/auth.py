"""Authentication middleware: API key mode (Phase 1).

If RELEASE_PLANNER_API_KEY is set, all API endpoints (except /api/status)
require Authorization: Bearer <key>. If unset, auth is disabled (local dev mode).
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)

# Read API key at module load time
_api_key: str = os.environ.get("RELEASE_PLANNER_API_KEY", "")


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> str:
    """Validate API key if configured. Returns the credential or 'anonymous'.

    If RELEASE_PLANNER_API_KEY is not set, auth is disabled and all requests
    are allowed (local dev mode).

    Args:
        credentials: Bearer token from the Authorization header.

    Returns:
        The validated credential string, or 'anonymous' if auth is disabled.

    Raises:
        HTTPException: 401 if auth is required and credentials are invalid.
    """
    if not _api_key:
        return "anonymous"
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, _api_key
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return credentials.credentials
