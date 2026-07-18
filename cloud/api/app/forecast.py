"""Forecast read paths: the latest stored model run for a station, and the
verification ("skill") numbers that say how honest those forecasts have been
against that station's own readings. Data is written by jobs/forecast.py.

    GET /api/v1/stations/{slug}/forecast?hours=48&model=best_match
    GET /api/v1/stations/{slug}/skill?days=30&model=best_match
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from .db import engine
from .jobs.forecast import ENSEMBLE_MODEL, MODELS
from .query import _station_id

router = APIRouter(prefix="/api/v1")

KNOWN_MODELS = set(MODELS) | {ENSEMBLE_MODEL}
SERIES_COLS = ["temp_c", "rh", "pressure_pa", "wind_avg_ms", "wind_gust_ms",
               "wind_dir_deg", "precip_mm", "precip_prob", "cloud_cover_pct"]
# rain counts as forecast/observed above this (mm per hour) for the contingency table
PRECIP_THRESHOLD = 0.2


def _check_model(model: str) -> None:
    if model not in KNOWN_MODELS:
        raise HTTPException(400, f"unknown model; have: {sorted(KNOWN_MODELS)}")


def _latest_run(conn, sid: int, model: str):
    return conn.execute(text(
        "SELECT max(run_at) FROM forecasts WHERE station_id = :sid AND model = :m"),
        {"sid": sid, "m": model}).scalar()


@router.get("/stations/{slug}/forecast")
def forecast(
    slug: str,
    hours: float = Query(48, gt=0, le=168),
    model: str = Query("best_match"),
):
    """uPlot-shaped, like /series: {"ts": [...], "series": {col: [...]}} from the
    latest stored run. Ensemble spread (when the GEFS rows exist for the same
    window) rides along as temp_spread_c / precip_spread_mm."""
    _check_model(model)
    now = datetime.now(timezone.utc)
    since, until = now - timedelta(hours=1), now + timedelta(hours=hours)
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        run_at = _latest_run(conn, sid, model)
        if run_at is None:
            raise HTTPException(404, "no forecast yet — the worker pulls every 3 h")
        rows = conn.execute(text(f"""
            SELECT valid_at, fetched_at, {', '.join(SERIES_COLS)}
            FROM forecasts
            WHERE station_id = :sid AND model = :m AND run_at = :r
              AND valid_at >= :since AND valid_at <= :until
            ORDER BY valid_at"""),
            {"sid": sid, "m": model, "r": run_at, "since": since, "until": until},
        ).all()

        spread: dict[datetime, tuple] = {}
        if model != ENSEMBLE_MODEL:
            ens_run = _latest_run(conn, sid, ENSEMBLE_MODEL)
            if ens_run is not None:
                spread = {r[0]: (r[1], r[2]) for r in conn.execute(text("""
                    SELECT valid_at, temp_spread_c, precip_spread_mm FROM forecasts
                    WHERE station_id = :sid AND model = :m AND run_at = :r
                      AND valid_at >= :since AND valid_at <= :until"""),
                    {"sid": sid, "m": ENSEMBLE_MODEL, "r": ens_run,
                     "since": since, "until": until}).all()}

    if not rows:
        raise HTTPException(404, "no forecast rows in window")
    return {
        "model": model,
        "run_at": run_at.isoformat(),
        "fetched_at": max(r[1] for r in rows).isoformat(),
        "ts": [int(r[0].timestamp()) for r in rows],
        "series": {
            **{c: [r[i + 2] for r in rows] for i, c in enumerate(SERIES_COLS)},
            "temp_spread_c": [spread.get(r[0], (None, None))[0] for r in rows],
            "precip_spread_mm": [spread.get(r[0], (None, None))[1] for r in rows],
        },
    }


@router.get("/stations/{slug}/skill")
def skill(
    slug: str,
    days: int = Query(30, gt=0, le=365),
    model: str = Query("best_match"),
):
    """Forecast-vs-observed verification, grouped by lead time (6 h buckets).
    Temperature joins readings_hourly at the forecast hour (instantaneous vs
    hour-average — a deliberate ±30 min blur); precipitation joins the bucket
    the forecast hour actually covers (open-meteo precip is the hour ENDING at
    valid_at, the rollup bucket is the hour STARTING at its timestamp)."""
    _check_model(model)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sql = text("""
        SELECT floor(extract(epoch FROM f.valid_at - f.run_at) / 21600)::int AS lead,
               count(*) FILTER (WHERE f.temp_c IS NOT NULL
                                  AND o.temp_c IS NOT NULL)             AS n,
               avg(f.temp_c - o.temp_c)                                 AS temp_bias,
               avg(abs(f.temp_c - o.temp_c))                            AS temp_mae,
               count(*) FILTER (WHERE f.precip_mm >= :thr
                                  AND op.rain_mm  >= :thr)              AS hits,
               count(*) FILTER (WHERE f.precip_mm IS NOT NULL
                                  AND f.precip_mm <  :thr
                                  AND op.rain_mm  >= :thr)              AS misses,
               count(*) FILTER (WHERE f.precip_mm >= :thr
                                  AND op.rain_mm IS NOT NULL
                                  AND op.rain_mm  <  :thr)              AS false_alarms
        FROM forecasts f
        JOIN readings_hourly o
          ON o.station_id = f.station_id AND o.bucket = f.valid_at
        LEFT JOIN readings_hourly op
          ON op.station_id = f.station_id
         AND op.bucket = f.valid_at - INTERVAL '1 hour'
        WHERE f.station_id = :sid AND f.model = :m
          AND f.valid_at > f.run_at AND f.valid_at <= now()
          AND f.valid_at >= :since
        GROUP BY lead ORDER BY lead
    """)
    with engine.connect() as conn:
        sid = _station_id(conn, slug)
        rows = conn.execute(sql, {"sid": sid, "m": model, "since": since,
                                  "thr": PRECIP_THRESHOLD}).all()

    leads = []
    for lead, n, bias, mae, hits, misses, fa in rows:
        leads.append({
            "lead_h": int(lead) * 6,
            "n": n,
            "temp_bias_c": round(bias, 2) if bias is not None else None,
            "temp_mae_c": round(mae, 2) if mae is not None else None,
            "precip_pod": round(hits / (hits + misses), 2) if hits + misses else None,
            "precip_far": round(fa / (hits + fa), 2) if hits + fa else None,
        })
    return {"model": model, "days": days,
            "n_pairs": sum(l["n"] for l in leads), "leads": leads}
