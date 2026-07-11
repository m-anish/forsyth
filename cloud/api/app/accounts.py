"""User accounts + custom dashboards ("boards").

Deliberately light: scrypt password hashes and HMAC-signed session cookies from
the stdlib — no new dependencies, no OAuth, no roles. Users are created by the
admin key; every logged-in user may edit their own board and publish it as the
public default (small, trusted userbase by design).

    POST /api/v1/auth/login     {username, password} → session cookie (30 days)
    POST /api/v1/auth/logout
    GET  /api/v1/auth/me
    POST /api/v1/users          (admin bearer) {username, password}
    GET  /api/v1/boards/default          public default layout
    GET  /api/v1/boards/mine             (session) own layout, falls back to default
    PUT  /api/v1/boards/mine[?set_default=1]  (session) save layout
"""
import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from .auth import AdminDep
from .config import settings
from .db import engine

log = logging.getLogger("forsyth.accounts")
router = APIRouter(prefix="/api/v1")

COOKIE = "forsyth_session"
SESSION_DAYS = 30

WIDGET_TYPES = {"now", "chart", "windrose", "aqi", "lightning", "camera", "map",
                "summary", "health"}

DEFAULT_LAYOUT = {
    "title": "The mesh, at a glance",
    "widgets": [
        {"id": "w1", "type": "summary",   "x": 0, "y": 0, "w": 12, "h": 1, "config": {}},
        {"id": "w2", "type": "map",       "x": 0, "y": 1, "w": 6,  "h": 4, "config": {}},
        {"id": "w3", "type": "now",       "x": 6, "y": 1, "w": 3,  "h": 4, "config": {"station": "ridge"}},
        {"id": "w4", "type": "windrose",  "x": 9, "y": 1, "w": 3,  "h": 4, "config": {"station": "ridge"}},
        {"id": "w5", "type": "chart",     "x": 0, "y": 5, "w": 8,  "h": 3,
         "config": {"station": "ridge", "metrics": "temp_c,rh", "hours": 24, "title": "Ridge · temp & humidity"}},
        {"id": "w6", "type": "lightning", "x": 8, "y": 5, "w": 4,  "h": 3, "config": {}},
    ],
}


def _secret() -> bytes:
    return hashlib.sha256(b"forsyth-session:" + settings.admin_key.encode()).digest()


def _hash_pw(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + h.hex()


def _check_pw(password: str, stored: str) -> bool:
    try:
        salt_hex, h_hex = stored.split("$", 1)
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def _make_token(username: str) -> str:
    exp = int(time.time()) + SESSION_DAYS * 86400
    msg = f"{username}:{exp}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_token(token: str) -> str | None:
    try:
        username, exp, sig = token.rsplit(":", 2)
        msg = f"{username}:{exp}"
        if not hmac.compare_digest(sig, hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()):
            return None
        if int(exp) < time.time():
            return None
        return username
    except Exception:
        return None


def current_user(request: Request) -> str | None:
    tok = request.cookies.get(COOKIE)
    return _verify_token(tok) if tok else None


def require_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not signed in")
    return user


# ---------- auth ----------

class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginBody, response: Response):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT pw_hash FROM users WHERE username = :u"),
                           {"u": body.username}).first()
    if row is None or not _check_pw(body.password, row[0]):
        raise HTTPException(403, "wrong username or password")
    response.set_cookie(
        COOKIE, _make_token(body.username),
        max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=settings.public_base_url.startswith("https"),
    )
    return {"username": body.username}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not signed in")
    return {"username": user}


class UserBody(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,30}$")
    password: str = Field(min_length=8)


@router.post("/users", dependencies=[AdminDep], status_code=201)
def create_user(body: UserBody):
    """Create a user, or reset their password if they exist (admin key)."""
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO users (username, pw_hash) VALUES (:u, :h)
                    ON CONFLICT (username) DO UPDATE SET pw_hash = EXCLUDED.pw_hash"""),
            {"u": body.username, "h": _hash_pw(body.password)},
        )
    log.info("user %s created/reset", body.username)
    return {"ok": True, "username": body.username}


# ---------- boards ----------

def _validate_layout(layout: dict) -> dict:
    widgets = layout.get("widgets")
    if not isinstance(widgets, list) or len(widgets) > 40:
        raise HTTPException(422, "layout.widgets must be a list of at most 40 items")
    for w in widgets:
        if w.get("type") not in WIDGET_TYPES:
            raise HTTPException(422, f"unknown widget type {w.get('type')!r}")
        for k in ("x", "y", "w", "h"):
            if not isinstance(w.get(k), int) or not (0 <= w[k] <= 48):
                raise HTTPException(422, f"widget {k} out of range")
        if not isinstance(w.get("config", {}), dict):
            raise HTTPException(422, "widget config must be an object")
    title = layout.get("title", "")
    if not isinstance(title, str) or len(title) > 80:
        raise HTTPException(422, "title too long")
    return {"title": title, "widgets": widgets}


def _get_board(owner: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT layout FROM boards WHERE owner = :o"),
                           {"o": owner}).first()
    return row[0] if row else None


@router.get("/boards/default")
def default_board():
    return {"layout": _get_board("__default__") or DEFAULT_LAYOUT, "owner": "__default__"}


@router.get("/boards/mine")
def my_board(request: Request):
    user = require_user(request)
    layout = _get_board(user) or _get_board("__default__") or DEFAULT_LAYOUT
    return {"layout": layout, "owner": user}


class BoardBody(BaseModel):
    layout: dict


@router.put("/boards/mine")
def save_board(body: BoardBody, request: Request, set_default: bool = False):
    user = require_user(request)
    layout = _validate_layout(body.layout)
    with engine.begin() as conn:
        for owner in ([user, "__default__"] if set_default else [user]):
            conn.execute(
                text("""INSERT INTO boards (owner, layout, updated_at)
                        VALUES (:o, :l, now())
                        ON CONFLICT (owner) DO UPDATE
                            SET layout = EXCLUDED.layout, updated_at = now()"""),
                {"o": owner, "l": json.dumps(layout)},
            )
    return {"ok": True, "set_default": set_default}
