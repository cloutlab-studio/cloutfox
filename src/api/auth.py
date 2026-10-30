"""Bearer-token authentication for the REST API.

When CLOUTFOX_API_TOKEN is set every /api/v1 route except /health requires
`Authorization: Bearer <token>` (or `X-API-Key: <token>`). The API listens on
loopback only either way; without a token `LocalOnlyGuard` keeps websites out.
"""

import secrets

from fastapi import HTTPException, Request

from ..core.config import API_TOKEN


def _presented_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("X-API-Key", "").strip()


def require_token(request: Request) -> None:
    """FastAPI dependency: reject the request unless it carries the API token."""
    if not API_TOKEN:
        return
    if not secrets.compare_digest(_presented_token(request), API_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_token(token: str = API_TOKEN) -> None:
    """Refuse to start with a token too short to resist guessing."""
    if token and len(token) < 24:
        raise SystemExit("CLOUTFOX_API_TOKEN must be at least 24 characters long.")
