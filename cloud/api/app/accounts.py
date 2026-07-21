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

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
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

# The homepage arrangement, following the weather-product canon (alert bar →
# current hero → hourly forecast → map → detail), in Forsyth's own order of
# honesty. The alert BANNER is not a widget — it is a fixed page-level element
# above every board (board.js), so it never clips and looks identical on the
# homepage and station pages. The grid below carries the rest: the forecast
# shows its work, the map gives the valley, feeds carry what people and the
# sky reported, and mesh health lets the instrument show its own pulse.
DEFAULT_LAYOUT = {
    "title": "The mesh, at a glance",
    "widgets": [
        {"id": "w2", "type": "now",       "x": 0, "y": 0,  "w": 3,  "h": 4, "config": {}},
        {"id": "w3", "type": "forecast",  "x": 3, "y": 0,  "w": 6,  "h": 4, "config": {}},
        {"id": "w4", "type": "windrose",  "x": 9, "y": 0,  "w": 3,  "h": 4, "config": {}},
        {"id": "w5", "type": "map",       "x": 0, "y": 4,  "w": 8,  "h": 4, "config": {}},
        {"id": "w6", "type": "lightning", "x": 8, "y": 4,  "w": 4,  "h": 2, "config": {}},
        {"id": "w7", "type": "reports",   "x": 8, "y": 6,  "w": 4,  "h": 2, "config": {}},
        {"id": "w8", "type": "chart",     "x": 0, "y": 8,  "w": 8,  "h": 3,
         "config": {"metrics": "temp_c,rh", "hours": 24, "title": "Temperature & humidity · 24 h"}},
        {"id": "w9", "type": "health",    "x": 8, "y": 8,  "w": 4,  "h": 3, "config": {}},
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
            "SELECT username, is_admin, default_board FROM users WHERE username = :u"),
            {"u": name}).mappings().first()
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
    from .reports import reporter_stats
    with engine.connect() as conn:
        user["reports"] = reporter_stats(conn, user["username"])
    return user


# ---------- self-serve accounts (engagement-roadmap §4) ----------

@router.get("/auth/methods")
def auth_methods():
    """What the sign-in dialog should offer. OAuth providers show up only
    when their credentials are configured."""
    return {
        "signup": settings.signup_enabled,
        "google": bool(settings.google_client_id and settings.google_client_secret),
        "github": bool(settings.github_client_id and settings.github_client_secret),
    }


class SignupBody(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,30}$")
    password: str = Field(min_length=8)


@router.post("/auth/signup", status_code=201)
def signup(body: SignupBody, response: Response):
    if not settings.signup_enabled:
        raise HTTPException(404, "self-serve signup is disabled on this mesh")
    with engine.begin() as conn:
        n = conn.execute(text(
            "INSERT INTO users (username, pw_hash) VALUES (:u, :h) "
            "ON CONFLICT (username) DO NOTHING"),
            {"u": body.username, "h": _hash_pw(body.password)}).rowcount
    if not n:
        raise HTTPException(409, "that username is taken")
    response.set_cookie(
        COOKIE, _make_token(body.username),
        max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=settings.public_base_url.startswith("https"),
    )
    log.info("self-serve signup: %s", body.username)
    return {"username": body.username}


# ---------- OAuth (Google, GitHub) — plain code flow, no framework ----------

_OAUTH = {
    "google": {
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "auth": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "scope": "read:user",
    },
}


def _oauth_creds(provider: str) -> tuple[str, str]:
    cid = getattr(settings, f"{provider}_client_id", "")
    sec = getattr(settings, f"{provider}_client_secret", "")
    if provider not in _OAUTH or not (cid and sec):
        raise HTTPException(404, f"{provider} sign-in is not configured")
    return cid, sec


def _redirect_uri(provider: str) -> str:
    return f"{settings.public_base_url}/api/v1/auth/oauth/{provider}/callback"


def _oauth_state() -> str:
    exp = int(time.time()) + 600
    sig = hmac.new(_secret(), f"oauth:{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{exp}:{sig}"


def _oauth_state_ok(state: str) -> bool:
    try:
        exp, sig = state.split(":", 1)
        good = hmac.new(_secret(), f"oauth:{exp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) >= time.time()
    except Exception:
        return False


def _derive_username(conn, wanted: str) -> str:
    """Sanitize a provider handle/email into our username shape, dedupe."""
    base = re.sub(r"[^a-z0-9_-]", "-", wanted.lower()).strip("-")[:24]
    if not re.match(r"^[a-z0-9]", base or ""):
        base = "sky-" + (base or "watcher")
    base = base[:24]
    name = base
    while conn.execute(text("SELECT 1 FROM users WHERE username = :u"),
                       {"u": name}).first():
        name = f"{base}-{secrets.token_hex(2)}"
    return name


@router.get("/auth/oauth/{provider}")
def oauth_start(provider: str):
    cid, _ = _oauth_creds(provider)
    p = _OAUTH[provider]
    params = httpx.QueryParams({
        "client_id": cid, "redirect_uri": _redirect_uri(provider),
        "scope": p["scope"], "state": _oauth_state(), "response_type": "code",
    })
    return RedirectResponse(f"{p['auth']}?{params}", status_code=303)


def _auth_fail(msg: str) -> RedirectResponse:
    """Send sign-in failures back to the board page, where the dialog shows
    the message — nobody should ever see a naked JSON error screen."""
    from urllib.parse import quote
    return RedirectResponse("/board.html?auth_error=" + quote(msg), status_code=303)


def _provider_call(fn, tries: int = 2):
    """One retry — the droplet's route to some providers flakes for seconds."""
    for attempt in range(tries):
        try:
            r = fn()
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == tries - 1:
                raise
            log.warning("provider call failed (%s); retrying once", e)
            time.sleep(1.5)


@router.get("/auth/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str = "", state: str = "", error: str = ""):
    cid, sec = _oauth_creds(provider)
    p = _OAUTH[provider]
    if error or not code or not _oauth_state_ok(state):
        return _auth_fail("sign-in was cancelled or went stale - try again")
    try:
        tok = _provider_call(lambda: httpx.post(p["token"], data={
            "client_id": cid, "client_secret": sec, "code": code,
            "redirect_uri": _redirect_uri(provider),
            "grant_type": "authorization_code",
        }, headers={"Accept": "application/json"}, timeout=15))
        access = tok.get("access_token", "")
        info = _provider_call(lambda: httpx.get(
            p["userinfo"], headers={"Authorization": f"Bearer {access}"},
            timeout=15))
    except Exception as e:
        log.warning("oauth %s failed: %s", provider, e)
        return _auth_fail(f"{provider} didn't answer - try again in a minute")

    if provider == "google":
        sub = str(info.get("sub", ""))
        wanted = (info.get("email") or "").split("@")[0] or "google-user"
    else:
        sub = str(info.get("id", ""))
        wanted = info.get("login") or "github-user"
    if not sub:
        return _auth_fail(f"{provider} returned no usable identity - try again")

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT username FROM users "
            "WHERE oauth_provider = :p AND oauth_sub = :s"),
            {"p": provider, "s": sub}).first()
        if row:
            username = row[0]
        else:
            username = _derive_username(conn, wanted)
            conn.execute(text(
                "INSERT INTO users (username, pw_hash, oauth_provider, oauth_sub) "
                "VALUES (:u, NULL, :p, :s)"),
                {"u": username, "p": provider, "s": sub})
            log.info("oauth signup via %s: %s", provider, username)

    resp = RedirectResponse("/board.html", status_code=303)
    resp.set_cookie(
        COOKIE, _make_token(username),
        max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=settings.public_base_url.startswith("https"),
    )
    return resp


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
    """New boards start as a copy of the homepage arrangement — a familiar
    starting point to rearrange, not a blank page."""
    user = require_user(request)
    with engine.begin() as conn:
        home = _board_row(conn, "default")
        base = home["layout"] if home else DEFAULT_LAYOUT
        layout = dict(base, title=body.title)
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


@router.post("/boards/{slug}/default")
def set_default_board(slug: str, request: Request):
    """Make this board what I land on (board.html with no ?b=). Calling it on
    the current default clears the preference back to the site board."""
    user = require_user(request)
    with engine.begin() as conn:
        if slug != "default" and _board_row(conn, slug) is None:
            raise HTTPException(404, "no such board")
        new = None if user.get("default_board") == slug or slug == "default" else slug
        conn.execute(text("UPDATE users SET default_board = :b WHERE username = :u"),
                     {"b": new, "u": user["username"]})
    return {"ok": True, "default_board": new}


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
