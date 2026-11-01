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
    bm = settings.basemap_tile_url
    return {
        "satellite": ({"url": sat, "attribution": settings.satellite_attribution,
                       "maxZoom": settings.satellite_max_zoom} if sat else None),
        "homeStation": settings.home_station or None,
        "terrain": ({"url": settings.terrain_tile_url,
                     "attribution": settings.terrain_attribution,
                     "maxZoom": settings.terrain_max_zoom}
                    if settings.terrain_tile_url else None),
        "basemap": ({"url": bm,
                     "urlDark": settings.basemap_tile_url_dark or bm,
                     "attribution": settings.basemap_attribution,
                     "maxZoom": settings.basemap_max_zoom} if bm else None),
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
               r.wind_dir_deg, r.rain_mm,
               p.pm1, p.pm25, p.pm10, p.ts AS pm_ts,
               r.batt_v, r.solar_state, r.rssi_dbm
        FROM stations s
        LEFT JOIN LATERAL (
            SELECT * FROM readings WHERE station_id = s.id
            ORDER BY ts DESC LIMIT 1
        ) r ON TRUE
        -- PM rides only every Nth reading, so the latest reading usually has no
        -- PM; carry the last reading that actually had it (with its timestamp).
        LEFT JOIN LATERAL (
            SELECT pm1, pm25, pm10, ts FROM readings
            WHERE station_id = s.id AND pm25 IS NOT NULL
            ORDER BY ts DESC LIMIT 1
        ) p ON TRUE
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
        d = dict(row)
        # overlay the last actually-measured PM (sparse — every Nth reading)
        pm = conn.execute(
            text("""SELECT pm1, pm25, pm10, ts FROM readings
                    WHERE station_id = :sid AND pm25 IS NOT NULL
                    ORDER BY ts DESC LIMIT 1"""),
            {"sid": sid},
        ).mappings().first()
        if pm:
            d.update({"pm1": pm["pm1"], "pm25": pm["pm25"],
                      "pm10": pm["pm10"], "pm_ts": pm["ts"]})
    return d


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
    if hours <= 12:
        # short windows (the 1 h/6 h/12 h pills) would be a dozen points at a
        # 5-minute bucket — go as fine as the stations actually report
        bucket, source = "1 minute", "readings"
    elif hours <= 48:
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


# Wind-speed bands for the rose, in m/s. Anything below CALM_MS is not given a
# direction at all: a cup anemometer at a standstill leaves the vane pointing
# wherever it last was, so counting those samples would inflate whichever
# direction the vane happened to be resting in. Calm is reported as its own
# share instead (docs/v2-design.md §7.3).
ROSE_CALM_MS = 0.5
ROSE_BAND_EDGES = [2.0, 4.0, 8.0]      # → bands <2, 2–4, 4–8, ≥8 m/s


@router.get("/stations/{slug}/windrose")
def windrose(slug: str, hours: float = Query(24, gt=0, le=24 * 366)):
    """16 compass bins × 4 speed bands, plus the calm share.

    Frequency alone cannot say whether a direction brings a breeze or a gale,
    which is the question a rose is usually being asked. `bands` carries the
    per-bin speed distribution; `n` and `speed` remain for older callers.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    sql = text("""
        SELECT (floor((((wind_dir_deg + 11.25)::numeric % 360) / 22.5))::int) AS bin,
               width_bucket(wind_avg_ms, :edges) AS band,
               count(*) AS n, avg(wind_avg_ms) AS speed
        FROM readings
        WHERE station_id = :sid AND ts >= :since
          AND wind_dir_deg IS NOT NULL AND wind_avg_ms IS NOT NULL
          AND wind_avg_ms >= :calm
        GROUP BY bin, band ORDER BY bin
    """)
    # Gusts get their own pass. Folding them into the query above would hide
    # them exactly when they matter most: that one filters on the MEAN being
    # above calm, so a sharp gust during an otherwise still interval — which is
    # precisely what a gust is — contributed nothing. Gated on the gust itself.
    gust_sql = text("""
        SELECT (floor((((wind_dir_deg + 11.25)::numeric % 360) / 22.5))::int) AS bin,
               max(wind_gust_ms) AS gust
        FROM readings
        WHERE station_id = :sid AND ts >= :since
          AND wind_dir_deg IS NOT NULL AND wind_gust_ms IS NOT NULL
          AND wind_gust_ms >= :calm
        GROUP BY bin
    """)
    totals_sql = text("""
        SELECT count(*) FILTER (WHERE wind_avg_ms < :calm) AS calm,
               count(*) AS samples
        FROM readings
        WHERE station_id = :sid AND ts >= :since AND wind_avg_ms IS NOT NULL
    """)
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        rows = conn.execute(sql, {"sid": sid, "since": since,
                                  "calm": ROSE_CALM_MS,
                                  "edges": ROSE_BAND_EDGES}).all()
        gust_rows = conn.execute(gust_sql, {"sid": sid, "since": since,
                                            "calm": ROSE_CALM_MS}).all()
        calm, samples = conn.execute(
            totals_sql, {"sid": sid, "since": since, "calm": ROSE_CALM_MS}).one()

    nb = len(ROSE_BAND_EDGES) + 1
    bins = [{"n": 0, "speed": 0.0, "gust": 0.0, "bands": [0] * nb} for _ in range(16)]
    weighted = [0.0] * 16
    for b, band, n, speed in rows:
        i = int(b)
        bins[i]["bands"][min(int(band), nb - 1)] += n
        bins[i]["n"] += n
        weighted[i] += float(speed or 0) * n
    for b, gust in gust_rows:
        bins[int(b)]["gust"] = round(float(gust or 0), 2)
    for i, b in enumerate(bins):
        b["speed"] = round(weighted[i] / b["n"], 2) if b["n"] else 0.0

    total = sum(b["n"] for b in bins)
    return {
        "bins": bins,
        "total": total,                      # samples with a usable direction
        "calm": calm,                        # samples below ROSE_CALM_MS
        "samples": samples,                  # every sample with a wind reading
        "calm_pct": round(100 * calm / samples, 1) if samples else 0.0,
        "calm_ms": ROSE_CALM_MS,
        "band_edges_ms": ROSE_BAND_EDGES,
    }


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
