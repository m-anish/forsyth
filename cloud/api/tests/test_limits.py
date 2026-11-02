"""The public API's front door: CORS and the rate limiter.

Unlike test_api.py next door, this needs no stack and no database — it mounts
the real middleware from app/limits.py and app/main.py's configuration onto a
stub app, so it says nothing about the queries and everything about what a
stranger's browser and a stranger's script are allowed to do.

    pytest cloud/api/tests/test_limits.py
"""
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import limits  # noqa: E402

ORIGIN = {"Origin": "https://somebody-elses-dashboard.example"}
CALLER = {"X-Forwarded-For": "203.0.113.9"}


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/api/v1/stations")
    def stations():
        return {"stations": []}

    @app.get("/api/v1/export/all.csv")
    def export():
        return {"csv": True}

    @app.delete("/api/v1/users/someone")
    def delete_user():
        return {"gone": True}

    @app.post("/api/v1/ingest")
    def ingest():
        return {"ok": True}

    @app.get("/healthz")
    def outside():
        return {"ok": True}

    # The same order as main.py, and the order is the point: add_middleware
    # INSERTS, so the last one added ends up outermost. The limiter is added
    # first precisely so CORS wraps it — see test_rate_limited_response_is_cors.
    app.middleware("http")(limits.rate_limit)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                       allow_methods=["GET", "HEAD"], max_age=86400)
    limits._hits.clear()
    return TestClient(app)


# ---------- CORS: open to read, shut to everything else ----------

def test_any_origin_may_read(client):
    r = client.get("/api/v1/stations", headers=ORIGIN)
    assert r.headers["access-control-allow-origin"] == "*"


def test_no_credentials_so_a_session_cookie_never_rides_along(client):
    """The one that matters. "*" plus credentials would let any page on the
    internet make authenticated calls as whoever is signed in."""
    r = client.get("/api/v1/stations", headers=ORIGIN)
    assert "access-control-allow-credentials" not in r.headers


def test_write_methods_are_refused_cross_origin(client):
    p = client.options("/api/v1/users/someone",
                       headers={**ORIGIN, "Access-Control-Request-Method": "DELETE"})
    assert p.status_code == 400
    assert "DELETE" not in (p.headers.get("access-control-allow-methods") or "")


def test_authorization_header_is_not_allowed_cross_origin(client):
    """A station key or the admin key has no business travelling from a web page."""
    p = client.options("/api/v1/stations",
                       headers={**ORIGIN, "Access-Control-Request-Method": "GET",
                                "Access-Control-Request-Headers": "authorization"})
    assert "authorization" not in (p.headers.get("access-control-allow-headers") or "").lower()


# ---------- the budget ----------

def test_budget_runs_out_and_says_when_to_return(client):
    codes = [client.get("/api/v1/stations", headers=CALLER).status_code
             for _ in range(limits.GENERAL_MAX + 3)]
    assert codes[:limits.GENERAL_MAX] == [200] * limits.GENERAL_MAX
    assert set(codes[limits.GENERAL_MAX:]) == {429}
    r = client.get("/api/v1/stations", headers=CALLER)
    assert 0 < int(r.headers["Retry-After"]) <= limits.WINDOW_S + 1


def test_rate_limited_response_is_cors(client):
    """A 429 without CORS headers reaches the browser as an opaque network
    error, and the developer on the other end files a bug against us instead
    of fixing their loop."""
    for _ in range(limits.GENERAL_MAX):
        client.get("/api/v1/stations", headers=CALLER)
    r = client.get("/api/v1/stations", headers={**CALLER, **ORIGIN})
    assert r.status_code == 429
    assert r.headers["access-control-allow-origin"] == "*"


def test_each_caller_has_their_own(client):
    for _ in range(limits.GENERAL_MAX + 1):
        client.get("/api/v1/stations", headers=CALLER)
    assert client.get("/api/v1/stations",
                      headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 200


def test_a_forged_forwarded_for_wins_nothing(client):
    """Caddy appends, so a caller who sends the header arrives as
    "<forged>, <real>". Reading the first entry — the obvious way to write it —
    would make the limit a request header away from useless."""
    for i in range(limits.GENERAL_MAX):
        client.get("/api/v1/stations",
                   headers={"X-Forwarded-For": f"10.0.0.{i % 250}, 203.0.113.9"})
    assert client.get("/api/v1/stations",
                      headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.9"}).status_code == 429


def test_hardware_is_never_throttled(client):
    """A coordinator catching up after a power cut posts a burst by design, and
    a reading dropped there is gone for good."""
    for _ in range(limits.GENERAL_MAX + 1):
        client.get("/api/v1/stations", headers=CALLER)
    assert client.post("/api/v1/ingest", headers=CALLER).status_code == 200


def test_the_dashboard_itself_is_not_the_victim(client):
    """A station page costs 38 calls on load; the budget has to clear several,
    because a village behind one address is the normal case here."""
    assert limits.GENERAL_MAX >= 38 * 4


def test_exports_have_a_tighter_budget_of_their_own(client):
    codes = [client.get("/api/v1/export/all.csv", headers=CALLER).status_code
             for _ in range(limits.EXPORT_MAX + 2)]
    assert set(codes[limits.EXPORT_MAX:]) == {429}
    assert client.get("/api/v1/stations", headers=CALLER).status_code == 200


def test_paths_outside_the_api_are_untouched(client):
    """Static assets are the dashboard loading itself; throttling those would
    break the site for the very people the limit is meant to protect."""
    for _ in range(limits.GENERAL_MAX + 1):
        client.get("/api/v1/stations", headers=CALLER)
    assert client.get("/healthz", headers=CALLER).status_code == 200


def test_the_next_minute_starts_clean(client, monkeypatch):
    for _ in range(limits.GENERAL_MAX):
        client.get("/api/v1/stations", headers=CALLER)
    assert client.get("/api/v1/stations", headers=CALLER).status_code == 429
    later = time.time() + limits.WINDOW_S + 1
    monkeypatch.setattr(limits.time, "time", lambda: later)
    assert client.get("/api/v1/stations", headers=CALLER).status_code == 200


def test_the_table_does_not_grow_without_end(client):
    for i in range(limits._MAX_KEYS + 50):
        limits._hits[("gen", f"x{i}")] = (0, 1)      # all in a long-gone window
    client.get("/api/v1/stations", headers=CALLER)
    assert len(limits._hits) < 10
