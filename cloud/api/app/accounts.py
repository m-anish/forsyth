"""User accounts, admin management, and dashboards ("boards").

Model:
- users: scrypt hashes, HMAC-signed session cookie, optional is_admin.
- boards: many per user, slug-addressed. Private (owner only) or public
  (anyone with the link). The site homepage arrangement is the special slug
  'default' — owner NULL, editable by admins only.
- Admin actions accept EITHER an is_admin session OR the ADMIN_KEY bearer
  (bootstrap path, and what the simulator uses).

    POST /api/v1/auth/login|logout · GET /auth/me
    GET/POST /api/v1/users · DELETE /users/{name}          (admin)
    GET  /api/v1/boards                    my boards       (session)
    POST /api/v1/boards {title}            create          (session)
    GET  /api/v1/boards/{slug}             owner|public|default
    PUT  /api/v1/boards/{slug}             owner (admin for 'default')
    DELETE /api/v1/boards/{slug}           owner
    POST /api/v1/boards/{slug}/publish-home  copy layout → 'default' (admin)
"""
import hashlib
import hmac
import json
import logging
import re
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from .config import settings
from .db import engine

log = logging.getLogger("forsyth.accounts")
router = APIRouter(prefix="/api/v1")

COOKIE = "forsyth_session"
SESSION_DAYS = 30

WIDGET_TYPES = {"now", "chart", "windrose", "aqi", "lightning", "camera", "map",
                "forecast", "reports", "summary", "health"}

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


# ---------- crypto plumbing ----------

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


# ---------- auth dependencies ----------

def current_user(request: Request) -> dict | None:
    tok = request.cookies.get(COOKIE)
    name = _verify_token(tok) if tok else None
    if not name:
        return None
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT username, is_admin FROM users WHERE username = :u"), {"u": name}
        ).mappings().first()
    return dict(row) if row else None


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not signed in")
    return user


def _has_admin_key(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    return bool(settings.admin_key and token
                and secrets.compare_digest(token, settings.admin_key))


def require_admin(request: Request) -> str:
    """Admin session user OR the raw ADMIN_KEY bearer (bootstrap)."""
    if _has_admin_key(request):
        return "__admin_key__"
    user = current_user(request)
    if user and user["is_admin"]:
        return user["username"]
    raise HTTPException(403, "admin only")


# ---------- auth endpoints ----------

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
    return user


# ---------- user management (admin) ----------

class UserBody(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,30}$")
    password: str = Field(min_length=8)
    is_admin: bool = False


@router.get("/users")
def list_users(request: Request):
    require_admin(request)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT u.username, u.is_admin, u.created_at,
                   count(b.slug) AS boards
            FROM users u LEFT JOIN boards b ON b.owner = u.username
            GROUP BY u.username, u.is_admin, u.created_at
            ORDER BY u.created_at""")).mappings().all()
    return {"users": [dict(r) for r in rows]}


@router.post("/users", status_code=201)
def create_user(body: UserBody, request: Request):
    """Create a user, or reset password/admin flag if they exist."""
    require_admin(request)
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO users (username, pw_hash, is_admin)
                    VALUES (:u, :h, :a)
                    ON CONFLICT (username) DO UPDATE
                        SET pw_hash = EXCLUDED.pw_hash, is_admin = EXCLUDED.is_admin"""),
            {"u": body.username, "h": _hash_pw(body.password), "a": body.is_admin},
        )
    log.info("user %s created/reset (admin=%s)", body.username, body.is_admin)
    return {"ok": True, "username": body.username, "is_admin": body.is_admin}


@router.delete("/users/{username}")
def delete_user(username: str, request: Request):
    actor = require_admin(request)
    if actor == username:
        raise HTTPException(400, "not while you're signed in as them")
    with engine.begin() as conn:
        n = conn.execute(text("DELETE FROM users WHERE username = :u"),
                         {"u": username}).rowcount
    if not n:
        raise HTTPException(404, "no such user")
    return {"ok": True}  # their boards cascade


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


def _slugify(title: str, conn) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:24] or "board"
    slug = base
    while conn.execute(text("SELECT 1 FROM boards WHERE slug = :s"), {"s": slug}).first():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def _board_row(conn, slug: str):
    return conn.execute(text(
        "SELECT slug, owner, title, is_public, layout, updated_at "
        "FROM boards WHERE slug = :s"), {"s": slug}).mappings().first()


@router.get("/boards")
def my_boards(request: Request):
    user = require_user(request)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT slug, title, is_public, updated_at FROM boards "
            "WHERE owner = :o ORDER BY updated_at DESC"), {"o": user["username"]}
        ).mappings().all()
    return {"boards": [dict(r) for r in rows], "is_admin": user["is_admin"]}


class BoardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)


@router.post("/boards", status_code=201)
def create_board(body: BoardCreate, request: Request):
    user = require_user(request)
    layout = dict(DEFAULT_LAYOUT, title=body.title)
    with engine.begin() as conn:
        slug = _slugify(body.title, conn)
        conn.execute(text(
            "INSERT INTO boards (slug, owner, title, is_public, layout) "
            "VALUES (:s, :o, :t, FALSE, :l)"),
            {"s": slug, "o": user["username"], "t": body.title, "l": json.dumps(layout)})
    return {"slug": slug, "title": body.title}


@router.get("/boards/{slug}")
def get_board(slug: str, request: Request):
    with engine.connect() as conn:
        row = _board_row(conn, slug)
    if row is None:
        if slug == "default":   # first boot: synthesize the site board
            return {"slug": "default", "owner": None, "title": DEFAULT_LAYOUT["title"],
                    "is_public": True, "layout": DEFAULT_LAYOUT, "can_edit": False}
        raise HTTPException(404, "no such board")
    user = current_user(request)
    is_owner = user and user["username"] == row["owner"]
    is_admin = bool(user and user["is_admin"])
    if not (row["is_public"] or slug == "default" or is_owner or is_admin):
        raise HTTPException(403, "this board is private")
    can_edit = is_owner or (slug == "default" and is_admin)
    return {**dict(row), "can_edit": can_edit}


class BoardUpdate(BaseModel):
    layout: dict | None = None
    title: str | None = Field(None, max_length=80)
    is_public: bool | None = None


@router.put("/boards/{slug}")
def update_board(slug: str, body: BoardUpdate, request: Request):
    user = require_user(request)
    with engine.begin() as conn:
        row = _board_row(conn, slug)
        if row is None:
            if slug != "default" or not user["is_admin"]:
                raise HTTPException(404, "no such board")
            conn.execute(text(
                "INSERT INTO boards (slug, owner, title, is_public, layout) "
                "VALUES ('default', NULL, :t, TRUE, :l)"),
                {"t": DEFAULT_LAYOUT["title"], "l": json.dumps(DEFAULT_LAYOUT)})
            row = _board_row(conn, "default")
        may = user["username"] == row["owner"] or (slug == "default" and user["is_admin"])
        if not may:
            raise HTTPException(403, "not your board")
        sets, params = [], {"s": slug}
        if body.layout is not None:
            params["l"] = json.dumps(_validate_layout(body.layout))
            sets.append("layout = :l")
        if body.title is not None:
            params["t"] = body.title
            sets.append("title = :t")
        if body.is_public is not None and slug != "default":
            params["p"] = body.is_public
            sets.append("is_public = :p")
        if sets:
            conn.execute(text(
                f"UPDATE boards SET {', '.join(sets)}, updated_at = now() WHERE slug = :s"),
                params)
    return {"ok": True}


@router.delete("/boards/{slug}")
def delete_board(slug: str, request: Request):
    user = require_user(request)
    if slug == "default":
        raise HTTPException(400, "the homepage board is not deletable")
    with engine.begin() as conn:
        n = conn.execute(text(
            "DELETE FROM boards WHERE slug = :s AND owner = :o"),
            {"s": slug, "o": user["username"]}).rowcount
    if not n:
        raise HTTPException(404, "no such board of yours")
    return {"ok": True}


@router.post("/boards/{slug}/publish-home")
def publish_home(slug: str, request: Request):
    """Copy this board's layout onto the site homepage board (admins)."""
    require_admin(request)
    with engine.begin() as conn:
        row = _board_row(conn, slug)
        if row is None:
            raise HTTPException(404, "no such board")
        conn.execute(text(
            "INSERT INTO boards (slug, owner, title, is_public, layout) "
            "VALUES ('default', NULL, :t, TRUE, :l) "
            "ON CONFLICT (slug) DO UPDATE SET layout = EXCLUDED.layout, "
            "title = EXCLUDED.title, updated_at = now()"),
            {"t": row["title"], "l": json.dumps(row["layout"])})
    return {"ok": True}
