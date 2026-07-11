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
    assert r.status_code == 401
