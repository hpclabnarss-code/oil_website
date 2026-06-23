"""
Lightweight admin authentication.

This is intentionally simple (no external auth provider, no JWT library)
so the whole backend has zero heavyweight dependencies. It is fine for a
small internal admin tool running behind your own network / reverse proxy.

For anything internet-facing, put this behind HTTPS at minimum, and
consider swapping this for proper JWT + a real user table if more than
one admin will ever use it.

Credentials come from environment variables so you never have to commit
a password to source control:

    export ADMIN_USERNAME="admin"
    export ADMIN_PASSWORD="choose-a-strong-password"

If unset, defaults below are used -- change them before deploying anywhere
other than your own laptop.
"""
import os
import secrets
import time
from fastapi import Header, HTTPException, status

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

TOKEN_TTL_SECONDS = 8 * 60 * 60  # 8 hour admin session

# token -> expiry timestamp (in-memory; resets if the server restarts)
_active_tokens: dict[str, float] = {}


def check_credentials(username: str, password: str) -> bool:
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


def issue_token() -> str:
    token = secrets.token_urlsafe(32)
    _active_tokens[token] = time.time() + TOKEN_TTL_SECONDS
    return token


def _is_valid(token: str) -> bool:
    expiry = _active_tokens.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        _active_tokens.pop(token, None)
        return False
    return True


def require_admin(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: raises 401 unless a valid 'Bearer <token>' header is present."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin token")
    token = authorization.removeprefix("Bearer ").strip()
    if not _is_valid(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired admin token")
    return token
