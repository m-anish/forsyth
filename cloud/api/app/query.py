"""Read paths: everything the dashboard (and any curious curl) consumes."""
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from .config import settings
from .db import engine
from .ingest import READING_FIELDS

router = APIRouter(prefix="/api/v1")


@router.get("/config")
def public_config():
    """Non-secret front-end configuration — the dashboard reads this at load to
    feature-detect. Only values that are meant to be public (map keys ride in
    tile URLs and are domain-restricted, not secret) ever appear here."""
    sat = settings.satellite_tile_url
    return {
        "satellite": ({"url": sat, "attribution": settings.satellite_attribution,
                       "maxZoom": settings.satellite_max_zoom} if sat else None),
    }

NUMERIC_METRICS = [f for f in READING_FIELDS if f != "solar_state"]


def _station_id(conn, slug: str) -> int:
    row = conn.execute(text("SELECT id FROM stations WHERE slug = :s"), {"s": slug}).first()
    if row is None:
        raise HTTPException(404, "no such station")
    return row[0]


@router.get("/stations")
def list_stations():
    """All stations with their latest reading and last-seen time."""
    sql = text("""
        SELECT s.slug, s.name, s.lat, s.lon, s.elevation_m, s.is_simulated,
               r.ts AS last_seen,
               r.temp_c, r.rh, r.pressure_pa, r.wind_avg_ms, r.wind_gust_ms,
               r.wind_dir_deg, r.rain_mm, r.pm1, r.pm25, r.pm10,
               r.batt_v, r.solar_state, r.rssi_dbm
        FROM stations s
        LEFT JOIN LATERAL (
            SELECT * FROM readings WHERE station_id = s.id
            ORDER BY ts DESC LIMIT 1
        ) r ON TRUE
        ORDER BY s.slug
    """)
    with engine.connect() as conn:
        rows = [dict(m) for m in conn.execute(sql).mappings()]
    return {"stations": rows}


@router.get("/stations/{slug}/latest")
def latest(slug: str):
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        row = conn.execute(
            text("SELECT * FROM readings WHERE station_id = :sid ORDER BY ts DESC LIMIT 1"),
            {"sid": sid},
        ).mappings().first()
    if row is None:
        raise HTTPException(404, "no readings yet")
    return dict(row)


@router.get("/stations/{slug}/series")
def series(
    slug: str,
    metrics: str = Query("temp_c", description="comma-separated reading columns"),
    hours: float = Query(24, gt=0, le=24 * 366),
):
    """uPlot-shaped: {"ts": [epoch...], "series": {metric: [values...]}}.
    Buckets scale with the window; long windows read the hourly rollup."""
    cols = [m.strip() for m in metrics.split(",") if m.strip()]
    bad = [c for c in cols if c not in NUMERIC_METRICS]
    if bad:
        raise HTTPException(400, f"unknown metrics: {bad}")

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    if hours <= 48:
        bucket, source = "5 minutes", "readings"
    elif hours <= 24 * 14:
        bucket, source = "1 hour", "readings_hourly"
    else:
        bucket, source = "1 day", "readings_hourly"
    ts_col = "ts" if source == "readings" else "bucket"

    agg = ", ".join(
        f"{'max' if c == 'wind_gust_ms' else 'sum' if c == 'rain_mm' else 'avg'}({c}) AS {c}"
        for c in cols
    )
    sql = text(f"""
        SELECT time_bucket(:bucket, {ts_col}) AS t, {agg}
        FROM {source}
        WHERE station_id = :sid AND {ts_col} >= :since
        GROUP BY t ORDER BY t
    """)
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        rows = conn.execute(sql, {"bucket": bucket, "sid": sid, "since": since}).all()
    return {
        "ts": [int(r[0].timestamp()) for r in rows],
        "series": {c: [r[i + 1] for r in rows] for i, c in enumerate(cols)},
        "bucket": bucket,
    }


@router.get("/stations/{slug}/windrose")
def windrose(slug: str, hours: float = Query(24, gt=0, le=24 * 366)):
    """16 compass bins: sample count + mean speed per bin."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    sql = text("""
        SELECT (floor((((wind_dir_deg + 11.25)::numeric % 360) / 22.5))::int) AS bin,
               count(*) AS n, avg(wind_avg_ms) AS speed
        FROM readings
        WHERE station_id = :sid AND ts >= :since AND wind_dir_deg IS NOT NULL
        GROUP BY bin ORDER BY bin
    """)
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        rows = conn.execute(sql, {"sid": sid, "since": since}).all()
    bins = [{"n": 0, "speed": 0.0} for _ in range(16)]
    for b, n, speed in rows:
        bins[int(b)] = {"n": n, "speed": round(speed or 0, 2)}
    return {"bins": bins, "total": sum(b["n"] for b in bins)}


@router.get("/lightning")
def lightning(hours: float = Query(48, gt=0, le=24 * 366), slug: str | None = None):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    sql = """
        SELECT s.slug, l.ts, l.distance_km, l.energy, l.count
        FROM lightning_events l JOIN stations s ON s.id = l.station_id
        WHERE l.ts >= :since
    """
    params: dict = {"since": since}
    if slug:
        sql += " AND s.slug = :slug"
        params["slug"] = slug
    sql += " ORDER BY l.ts DESC LIMIT 500"
    with engine.connect() as conn:
        rows = [dict(m) for m in conn.execute(text(sql), params).mappings()]
    return {"events": rows}


@router.get("/stations/{slug}/frames/latest")
def latest_frame(slug: str):
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        row = conn.execute(
            text("""SELECT ts, path FROM camera_frames
                    WHERE station_id = :sid ORDER BY ts DESC LIMIT 1"""),
            {"sid": sid},
        ).mappings().first()
    if row is None:
        raise HTTPException(404, "no frames")
    return {"ts": row["ts"], "url": f"/media/{row['path']}"}


@router.get("/stations/{slug}/timelapses")
def timelapses(slug: str):
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        rows = conn.execute(
            text("""SELECT day, path, frame_count, duration_s FROM timelapses
                    WHERE station_id = :sid ORDER BY day DESC LIMIT 60"""),
            {"sid": sid},
        ).mappings().all()
    return {"timelapses": [
        {"day": str(r["day"]), "url": f"/media/{r['path']}",
         "frame_count": r["frame_count"], "duration_s": r["duration_s"]}
        for r in rows
    ]}


@router.get("/export/{slug}.csv")
def export_csv(
    slug: str,
    hours: float = Query(24 * 7, gt=0, le=24 * 366),
    start: datetime | None = Query(None, description="ISO start; overrides hours"),
    end: datetime | None = Query(None, description="ISO end; default now"),
):
    """Historical CSV. `slug` may be a station or `all` (adds a station column).
    Range: either ?hours=N back from now, or explicit ?start=&end= (max 366 days)."""
    until = end or datetime.now(timezone.utc)
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if start:
        since = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    else:
        since = until - timedelta(hours=hours)
    if since >= until:
        raise HTTPException(400, "start must be before end")
    if until - since > timedelta(days=366):
        raise HTTPException(400, "range capped at 366 days")

    with engine.connect() as conn:
        if slug == "all":
            cols = ["station", "ts"] + READING_FIELDS
            sql = text(f"""
                SELECT s.slug, r.ts, {', '.join('r.' + f for f in READING_FIELDS)}
                FROM readings r JOIN stations s ON s.id = r.station_id
                WHERE r.ts >= :since AND r.ts < :until ORDER BY r.ts, s.slug""")
            rows = conn.execute(sql, {"since": since, "until": until}).all()
        else:
            cols = ["ts"] + READING_FIELDS
            sid = _station_id(conn, slug)
            sql = text(f"""SELECT ts, {', '.join(READING_FIELDS)} FROM readings
                           WHERE station_id = :sid AND ts >= :since AND ts < :until
                           ORDER BY ts""")
            rows = conn.execute(sql, {"sid": sid, "since": since, "until": until}).all()

    ts_idx = cols.index("ts")

    def generate():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for r in rows:
            out = list(r)
            out[ts_idx] = out[ts_idx].isoformat()
            w.writerow(out)
            if buf.tell() > 64 * 1024:
                yield buf.getvalue(); buf.seek(0); buf.truncate()
        yield buf.getvalue()

    fname = f"forsyth-{slug}-{since.date()}-to-{until.date()}.csv"
    return StreamingResponse(
        generate(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/health")
def health():
    """Mesh self-monitoring: last-seen, battery, staleness per station."""
    sql = text("""
        SELECT s.slug, s.is_simulated, r.ts AS last_seen, r.batt_v, r.rssi_dbm,
               (r.ts IS NULL OR r.ts < now() - INTERVAL '30 minutes') AS stale
        FROM stations s
        LEFT JOIN LATERAL (
            SELECT ts, batt_v, rssi_dbm FROM readings
            WHERE station_id = s.id ORDER BY ts DESC LIMIT 1
        ) r ON TRUE
        ORDER BY s.slug
    """)
    with engine.connect() as conn:
        rows = [dict(m) for m in conn.execute(sql).mappings()]
    return {"stations": rows, "ok": all(not r["stale"] for r in rows) if rows else True}
