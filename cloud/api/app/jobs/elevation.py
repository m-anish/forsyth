"""Elevation backfill.

Location is set by humans (admin editor, coordinator capture) who supply lat/lon
but rarely a reliable altitude — and typing elevation is error-prone. So whenever
a station has coordinates but no elevation, we look it up from the free open-meteo
elevation API and fill it. This is the single server-side implementation that
covers BOTH write paths, and keeps the external call out of the request hot path
(it runs on a schedule, and once filled a station is never queried again).

Elevation matters for the (future) sea-level pressure reduction; until then it's
display-only, but populating it now means that feature is unblocked.
"""
import logging

import httpx
from sqlalchemy import text

from ..db import engine

log = logging.getLogger("forsyth.elevation")
# batch endpoint: up to 100 coords comma-separated, returns {"elevation":[...]}
ELEV_URL = "https://api.open-meteo.com/v1/elevation"


def run() -> None:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT slug, lat, lon FROM stations "
            "WHERE lat IS NOT NULL AND lon IS NOT NULL AND elevation_m IS NULL"
        )).all()
    if not rows:
        return
    lats = ",".join(str(r.lat) for r in rows)
    lons = ",".join(str(r.lon) for r in rows)
    try:
        r = httpx.get(ELEV_URL, params={"latitude": lats, "longitude": lons},
                      timeout=15)
        r.raise_for_status()
        elevs = r.json().get("elevation", [])
    except Exception as e:
        log.warning("elevation lookup failed (%s); will retry next run", e)
        return
    if len(elevs) != len(rows):
        log.warning("elevation API returned %d for %d stations; skipping",
                    len(elevs), len(rows))
        return
    with engine.begin() as conn:
        for station, elev in zip(rows, elevs):
            if elev is None:
                continue
            conn.execute(
                text("UPDATE stations SET elevation_m = :e WHERE slug = :s "
                     "AND elevation_m IS NULL"),
                {"e": round(float(elev), 1), "s": station.slug},
            )
            log.info("station %s elevation → %.1f m", station.slug, elev)
