"""Server-side Weather Underground uploader.

The coordinator posts to Forsyth once; this job fans the latest reading out to WU
for every real station that has wu_station_id/key set. Runs every 5 minutes;
skips simulated stations always, and everything unless WU_ENABLED=true.

Protocol: the classic PWS upload GET —
https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from ..config import settings
from ..db import engine

log = logging.getLogger("forsyth.wu")
WU_URL = "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"


def _to_params(r: dict) -> dict:
    """Metric reading → WU's imperial query params. Only send what we have."""
    p: dict = {}
    if r["temp_c"] is not None:
        p["tempf"] = round(r["temp_c"] * 9 / 5 + 32, 1)
    if r["rh"] is not None:
        p["humidity"] = round(r["rh"])
    if r["pressure_pa"] is not None:
        p["baromin"] = round(r["pressure_pa"] * 0.0002953, 3)
    if r["wind_avg_ms"] is not None:
        p["windspeedmph"] = round(r["wind_avg_ms"] * 2.23694, 1)
    if r["wind_gust_ms"] is not None:
        p["windgustmph"] = round(r["wind_gust_ms"] * 2.23694, 1)
    if r["wind_dir_deg"] is not None:
        p["winddir"] = round(r["wind_dir_deg"])
    if r["rain_hour_mm"] is not None:
        p["rainin"] = round(r["rain_hour_mm"] / 25.4, 3)
    if r["pm25"] is not None:
        p["AqPM2.5"] = round(r["pm25"], 1)
    return p


def run() -> list[dict]:
    sql = text("""
        SELECT s.slug, s.wu_station_id, s.wu_station_key,
               r.ts, r.temp_c, r.rh, r.pressure_pa, r.wind_avg_ms, r.wind_gust_ms,
               r.wind_dir_deg, r.pm25,
               (SELECT sum(rain_mm) FROM readings
                WHERE station_id = s.id AND ts >= now() - INTERVAL '1 hour') AS rain_hour_mm
        FROM stations s
        JOIN LATERAL (SELECT * FROM readings WHERE station_id = s.id
                      ORDER BY ts DESC LIMIT 1) r ON TRUE
        WHERE NOT s.is_simulated
          AND s.wu_station_id IS NOT NULL AND s.wu_station_key IS NOT NULL
    """)
    with engine.connect() as conn:
        rows = [dict(m) for m in conn.execute(sql).mappings()]

    results = []
    fresh_after = datetime.now(timezone.utc) - timedelta(minutes=10)
    for r in rows:
        if r["ts"] < fresh_after:
            results.append({"slug": r["slug"], "skipped": "stale reading"})
            continue
        params = {
            "ID": r["wu_station_id"], "PASSWORD": r["wu_station_key"],
            "action": "updateraw", "dateutc": "now",
            "softwaretype": "forsyth-cloud-0.1",
            **_to_params(r),
        }
        if not settings.wu_enabled:
            log.info("WU dry-run for %s: %s", r["slug"],
                     {k: v for k, v in params.items() if k != "PASSWORD"})
            results.append({"slug": r["slug"], "dry_run": True})
            continue
        try:
            resp = httpx.get(WU_URL, params=params, timeout=15)
            ok = resp.status_code == 200 and "success" in resp.text.lower()
            results.append({"slug": r["slug"], "ok": ok, "status": resp.status_code})
            if not ok:
                log.warning("WU upload for %s got %s: %s", r["slug"],
                            resp.status_code, resp.text[:120])
        except Exception as e:
            log.warning("WU upload for %s failed: %s", r["slug"], e)
            results.append({"slug": r["slug"], "error": str(e)})
    return results
