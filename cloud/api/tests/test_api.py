"""Integration tests — run against a live stack (docker compose up).

    API_TEST_BASE=http://localhost:8080 ADMIN_KEY=... pytest cloud/api/tests

They create a throwaway station (slug: pytest-probe), exercise ingest → query →
export, and delete it on the way out.
"""
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

BASE = os.environ.get("API_TEST_BASE", "http://localhost:8080")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
SLUG = "pytest-probe"

pytestmark = pytest.mark.timeout(30)


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=20) as c:
        yield c


@pytest.fixture(scope="module")
def station(client):
    assert ADMIN_KEY, "set ADMIN_KEY (same value as the stack's .env)"
    r = client.post("/api/v1/stations",
                    headers={"Authorization": f"Bearer {ADMIN_KEY}"},
                    json={"slug": SLUG, "name": "Pytest Probe", "is_simulated": True})
    assert r.status_code == 201, r.text
    yield r.json()
    client.delete(f"/api/v1/stations/{SLUG}",
                  headers={"Authorization": f"Bearer {ADMIN_KEY}"})


def auth(station):
    return {"Authorization": f"Bearer {station['api_key']}"}


def test_health(client):
    assert client.get("/api/v1/health").status_code == 200


def test_ingest_requires_key(client, station):
    r = client.post("/api/v1/ingest", json={"temp_c": 20})
    assert r.status_code == 401
    r = client.post("/api/v1/ingest", json={"temp_c": 20},
                    headers={"Authorization": "Bearer wrong-key"})
    assert r.status_code == 403


def test_ingest_single_and_latest(client, station):
    r = client.post("/api/v1/ingest", headers=auth(station),
                    json={"temp_c": 21.5, "rh": 55, "pressure_pa": 81000,
                          "wind_avg_ms": 2.0, "wind_dir_deg": 270,
                          "lightning": [{"distance_km": 12, "energy": 5000}]})
    assert r.status_code == 200 and r.json()["stored"] == 1
    latest = client.get(f"/api/v1/stations/{SLUG}/latest").json()
    assert latest["temp_c"] == 21.5
    ev = client.get(f"/api/v1/lightning?slug={SLUG}&hours=1").json()["events"]
    assert len(ev) == 1 and ev[0]["distance_km"] == 12


def test_ingest_validation(client, station):
    r = client.post("/api/v1/ingest", headers=auth(station), json={"rh": 250})
    assert r.status_code == 422


def test_batch_backfill_and_series_bucketing(client, station):
    now = datetime.now(timezone.utc)
    batch = [{"ts": (now - timedelta(minutes=5 * i)).isoformat(),
              "temp_c": 15 + i * 0.1, "rain_mm": 0.2} for i in range(24)]
    r = client.post("/api/v1/ingest", headers=auth(station), json={"readings": batch})
    assert r.status_code == 200 and r.json()["stored"] == 24

    s = client.get(f"/api/v1/stations/{SLUG}/series"
                   f"?metrics=temp_c,rain_mm&hours=3").json()
    assert s["bucket"] == "5 minutes"
    assert len(s["ts"]) >= 20
    assert set(s["series"]) == {"temp_c", "rain_mm"}
    # rain aggregates by sum: total must match what we sent (±float noise)
    sent = sum(b["rain_mm"] for b in batch)
    got = sum(v for v in s["series"]["rain_mm"] if v is not None)
    assert abs(got - sent) < 0.31  # one 5-min bucket may fall outside the window


def test_series_rejects_unknown_metric(client, station):
    r = client.get(f"/api/v1/stations/{SLUG}/series?metrics=drop_table")
    assert r.status_code == 400


def test_windrose_shape(client, station):
    r = client.get(f"/api/v1/stations/{SLUG}/windrose?hours=24").json()
    assert len(r["bins"]) == 16
    assert r["total"] >= 1  # the 270° reading from the single-ingest test


def test_export_csv(client, station):
    r = client.get(f"/api/v1/export/{SLUG}.csv?hours=24")
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("ts,temp_c")
    assert len(lines) >= 25


def test_station_create_requires_admin(client):
    r = client.post("/api/v1/stations", json={"slug": "nope", "name": "Nope"})
    assert r.status_code == 403  # admin key or admin session required


def test_boards_default_public(client):
    r = client.get("/api/v1/boards/default")
    assert r.status_code == 200
    assert "widgets" in r.json()["layout"]


def test_export_range_validation(client):
    r = client.get("/api/v1/export/all.csv?start=2026-01-02T00:00:00Z&end=2026-01-01T00:00:00Z")
    assert r.status_code == 400


# ---------- forecast layer ----------

def test_forecast_404_when_empty(client, station):
    # pytest-probe has no coordinates, so the forecast job never fetches for it
    r = client.get(f"/api/v1/stations/{SLUG}/forecast")
    assert r.status_code == 404


def test_forecast_unknown_model_400(client, station):
    r = client.get(f"/api/v1/stations/{SLUG}/forecast?model=wishful_thinking")
    assert r.status_code == 400


def test_skill_empty_ok(client, station):
    r = client.get(f"/api/v1/stations/{SLUG}/skill?days=30")
    assert r.status_code == 200
    d = r.json()
    assert d["n_pairs"] == 0 and d["leads"] == []


# ---------- accounts (self-serve) ----------

def test_auth_methods(client):
    m = client.get("/api/v1/auth/methods").json()
    assert set(m) == {"signup", "google", "github"}
    assert m["signup"] is True  # default-on in the test stack


def test_signup_and_me_stats(client):
    import uuid
    name = "probe-" + uuid.uuid4().hex[:8]
    with httpx.Client(base_url=BASE, timeout=20) as c:  # own cookie jar
        r = c.post("/api/v1/auth/signup",
                   json={"username": name, "password": "a-decent-passphrase"})
        assert r.status_code == 201, r.text
        me = c.get("/api/v1/auth/me")
        assert me.status_code == 200
        d = me.json()
        assert d["username"] == name and d["is_admin"] is False
        # report stats ride along, zeroed for a fresh account
        assert d["reports"]["total_90d"] == 0
        assert d["reports"]["streak_days"] == 0
        assert d["reports"]["trusted"] is False
        # duplicate signup is refused
        assert c.post("/api/v1/auth/signup",
                      json={"username": name, "password": "another-passphrase"}
                      ).status_code == 409
    # clean up (admin delete; also exercises the cascade)
    client.delete(f"/api/v1/users/{name}",
                  headers={"Authorization": f"Bearer {ADMIN_KEY}"})


def test_signup_validation(client):
    assert client.post("/api/v1/auth/signup",
                       json={"username": "Bad Name!", "password": "long-enough-pw"}
                       ).status_code == 422
    assert client.post("/api/v1/auth/signup",
                       json={"username": "shortpw", "password": "tiny"}
                       ).status_code == 422


def test_oauth_unconfigured_404(client):
    assert client.get("/api/v1/auth/oauth/google",
                      follow_redirects=False).status_code == 404
    assert client.get("/api/v1/auth/oauth/nope",
                      follow_redirects=False).status_code == 404


# ---------- human reports ----------

def test_report_roundtrip(client):
    r = client.post("/api/v1/reports",
                    json={"kind": "fog", "lat": 32.22, "lon": 76.32, "intensity": 2,
                          "note": "can't see the ridge"})
    # a rapid test rerun may be rate-limited from a previous pass; both are valid
    assert r.status_code in (201, 429), r.text
    if r.status_code == 201:
        d = r.json()
        assert d["kind"] == "fog" and "qc_flag" in d
        listed = client.get("/api/v1/reports?hours=1&kind=fog").json()
        assert listed["enabled"] is True
        mine = [x for x in listed["reports"] if x["id"] == d["id"]]
        assert mine and mine[0]["note"] == "can't see the ridge"
        # public coords are fuzzed to 3 decimals
        assert abs(mine[0]["lat"] - 32.22) < 0.001


def test_report_validation(client):
    assert client.post("/api/v1/reports",
                       json={"kind": "sharknado", "lat": 0, "lon": 0}).status_code == 422
    assert client.post("/api/v1/reports",
                       json={"kind": "hail", "lat": 99, "lon": 0}).status_code == 422
    assert client.post("/api/v1/reports",
                       json={"kind": "hail", "lat": 0, "lon": 0,
                             "note": "x" * 141}).status_code == 422
    assert client.get("/api/v1/reports?kind=sharknado").status_code == 400


def test_report_rate_limit(client):
    codes = [client.post("/api/v1/reports",
                         json={"kind": "precip", "lat": 32.2, "lon": 76.3}).status_code
             for _ in range(4)]
    assert 429 in codes  # the 4th (at the latest) trips the 3-per-10-min limit


@pytest.mark.skipif(not os.environ.get("FORECAST_LIVE"),
                    reason="set FORECAST_LIVE=1 to hit open-meteo for real (one call)")
def test_forecast_live_roundtrip(client, station):
    """Site the probe near Dharamsala, run the pull job once, read it back."""
    r = client.patch(f"/api/v1/stations/{SLUG}",
                     headers={"Authorization": f"Bearer {ADMIN_KEY}"},
                     json={"lat": 32.22, "lon": 76.32, "elevation_m": 1450})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/admin/run/forecast",
                    headers={"Authorization": f"Bearer {ADMIN_KEY}"})
    assert r.status_code == 200, r.text
    assert r.json()["result"].get("rows", 0) > 0

    d = client.get(f"/api/v1/stations/{SLUG}/forecast?hours=48").json()
    assert d["model"] == "best_match"
    assert len(d["ts"]) >= 40                     # ~48 hourly points
    assert any(v is not None for v in d["series"]["temp_c"])
    # pressure stored in Pa to match readings (sanity: > 50 kPa anywhere on Earth)
    pres = [v for v in d["series"]["pressure_pa"] if v is not None]
    assert not pres or pres[0] > 50_000
