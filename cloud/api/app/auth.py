"""Two credentials exist: the admin key (env) and per-station bearer keys
(sha256 hash in the stations table, plaintext shown exactly once at creation)."""
import hashlib
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text

from .config import settings
from .db import engine


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_station_key() -> str:
    return secrets.token_urlsafe(24)


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    raise HTTPException(401, "missing bearer token")


def require_admin(request: Request) -> None:
    if not settings.admin_key:
        raise HTTPException(503, "ADMIN_KEY not configured")
    if not secrets.compare_digest(_bearer(request), settings.admin_key):
        raise HTTPException(403, "not the admin key")


def require_station(request: Request) -> dict:
    """Resolve the bearer token to a station row (dict) or 403."""
    key_hash = hash_key(_bearer(request))
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, slug, name, is_simulated FROM stations WHERE api_key_hash = :h"),
            {"h": key_hash},
        ).mappings().first()
    if row is None:
        raise HTTPException(403, "unknown station key")
    return dict(row)


StationDep = Depends(require_station)
AdminDep = Depends(require_admin)
