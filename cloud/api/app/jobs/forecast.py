"""Forecast pull: fetch open-meteo point forecasts for every sited station and
keep EVERY run. The table of (run, lead, forecast) rows joined against what the
stations actually measured is the long-term asset — it is what per-valley skill
scores (/skill) and, later, bias correction train on. See docs/insight-roadmap.md.

Two batched HTTP requests per cycle regardless of station count (comma-separated
coordinate lists, same trick as the elevation job): one multi-model deterministic
call, one GEFS ensemble call reduced to mean/spread. Runs hourly — global
models only refresh 4–8×/day, so polling faster buys nothing.
"""
import logging
import statistics
from datetime import datetime, timezone

import httpx
from sqlalchemy import text

from ..config import settings
from ..db import engine

log = logging.getLogger("forsyth.forecast")

# requested hourly variable → forecasts column (order matters for suffix parsing)
VARIABLES = {
    "temperature_2m": "temp_c",
    "relative_humidity_2m": "rh",
    "surface_pressure": "pressure_pa",   # hPa from the API; stored as Pa
    "wind_speed_10m": "wind_avg_ms",
    "wind_gusts_10m": "wind_gust_ms",
    "wind_direction_10m": "wind_dir_deg",
    "precipitation": "precip_mm",
    "precipitation_probability": "precip_prob",
    "cloud_cover": "cloud_cover_pct",
}
MODELS = ["best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
ENSEMBLE_MODEL = "ens_gefs"              # stored name for the reduced GEFS rows

COLUMNS = ["temp_c", "rh", "pressure_pa", "wind_avg_ms", "wind_gust_ms",
           "wind_dir_deg", "precip_mm", "precip_prob", "cloud_cover_pct",
           "temp_spread_c", "precip_spread_mm"]

_UPSERT = text(f"""
    INSERT INTO forecasts (station_id, model, run_at, valid_at, {', '.join(COLUMNS)})
    VALUES (:station_id, :model, :run_at, :valid_at, {', '.join(':' + c for c in COLUMNS)})
    ON CONFLICT (station_id, model, run_at, valid_at)
    DO UPDATE SET fetched_at = now(), {', '.join(f'{c} = EXCLUDED.{c}' for c in COLUMNS)}
""")


def _run_bucket(now: datetime) -> datetime:
    """Fetch-cycle bucket: now truncated to the hour, so a re-run (admin
    button, worker restart) within the same hour upserts rather than
    duplicates. A *new* run_at is only ever written when the forecast content
    actually changed — see _unchanged."""
    return now.replace(minute=0, second=0, microsecond=0)


def _differs(a, b, tol=1e-6) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(a - b) > tol


def _latest_snapshot(conn) -> dict:
    """{(station_id, model): {valid_at: (temp_c, precip_mm)}} for the most
    recent stored run of each pair — enough to recognise a fetch we already
    have."""
    rows = conn.execute(text("""
        SELECT f.station_id, f.model, f.valid_at, f.temp_c, f.precip_mm
        FROM forecasts f
        JOIN (SELECT station_id, model, max(run_at) AS run_at
              FROM forecasts GROUP BY station_id, model) l
          ON l.station_id = f.station_id AND l.model = f.model
         AND l.run_at = f.run_at""")).all()
    snap: dict = {}
    for sid, model, valid_at, t, p in rows:
        snap.setdefault((sid, model), {})[valid_at] = (t, p)
    return snap


def _unchanged(prev: dict, rows: list[dict]) -> bool:
    """True when every hour this fetch shares with the stored run carries the
    same numbers — i.e. upstream hasn't published a new model run yet, and
    writing this would only duplicate what we already have.

    The horizon slides forward between polls, so the tail hours are legitimately
    new; only the overlap is evidence, and we want a decent amount of it."""
    if not prev:
        return False
    shared = 0
    for r in rows:
        old = prev.get(r["valid_at"])
        if old is None:
            continue
        shared += 1
        if _differs(old[0], r["temp_c"]) or _differs(old[1], r["precip_mm"]):
            return False
    return shared >= 6


def _hourly_value(hourly: dict, var: str, model: str, i: int, single_model: bool):
    """Multi-model responses suffix each variable with the model name; variables
    the API serves as a single unsuffixed series (e.g. precipitation_probability)
    are credited to best_match only. Missing keys/values → None."""
    vals = hourly.get(var if single_model else f"{var}_{model}")
    if vals is None and model == "best_match":
        vals = hourly.get(var)
    vals = vals or []
    return vals[i] if i < len(vals) and vals[i] is not None else None


def _row(sid: int, model: str, run_at: datetime, valid_at: datetime) -> dict:
    return {"station_id": sid, "model": model, "run_at": run_at,
            "valid_at": valid_at, **{c: None for c in COLUMNS}}


def _parse_deterministic(sid: int, run_at: datetime, resp: dict) -> list[dict]:
    hourly = resp.get("hourly", {})
    times = hourly.get("time", [])
    single = len(MODELS) == 1
    rows = []
    for model in MODELS:
        for i, t in enumerate(times):
            row = _row(sid, model, run_at, datetime.fromtimestamp(t, tz=timezone.utc))
            for var, col in VARIABLES.items():
                v = _hourly_value(hourly, var, model, i, single)
                if v is None:
                    continue
                row[col] = float(v) * 100 if col == "pressure_pa" else float(v)
            rows.append(row)
    return rows


def _parse_ensemble(sid: int, run_at: datetime, resp: dict) -> list[dict]:
    """Reduce GEFS members to mean + stdev; members are not stored."""
    hourly = resp.get("hourly", {})
    times = hourly.get("time", [])
    members: dict[str, list[list]] = {"temperature_2m": [], "precipitation": []}
    for key, vals in hourly.items():
        for var in members:
            if key == var or key.startswith(var + "_member"):
                members[var].append(vals)
    rows = []
    for i, t in enumerate(times):
        row = _row(sid, ENSEMBLE_MODEL, run_at, datetime.fromtimestamp(t, tz=timezone.utc))
        for var, (mean_col, sd_col) in {
            "temperature_2m": ("temp_c", "temp_spread_c"),
            "precipitation": ("precip_mm", "precip_spread_mm"),
        }.items():
            vals = [m[i] for m in members[var] if i < len(m) and m[i] is not None]
            if len(vals) >= 2:
                row[mean_col] = round(statistics.fmean(vals), 3)
                row[sd_col] = round(statistics.stdev(vals), 3)
        rows.append(row)
    return rows


def _as_list(payload) -> list[dict]:
    """Multi-location requests return an array; a single location, an object."""
    return payload if isinstance(payload, list) else [payload]


def run() -> dict:
    if not settings.forecast_enabled:
        return {"disabled": True}
    with engine.connect() as conn:
        stations = conn.execute(text(
            "SELECT id, slug, lat, lon, elevation_m FROM stations "
            "WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY id")).all()
    if not stations:
        return {"stations": 0, "rows": 0}

    run_at = _run_bucket(datetime.now(timezone.utc))
    coords = {
        "latitude": ",".join(str(s.lat) for s in stations),
        "longitude": ",".join(str(s.lon) for s in stations),
        # elevation improves downscaling in steep terrain; NaN = let the API pick
        "elevation": ",".join(str(round(s.elevation_m, 1)) if s.elevation_m is not None
                              else "NaN" for s in stations),
        "timeformat": "unixtime",
        "wind_speed_unit": "ms",
        "forecast_days": settings.forecast_days,
    }

    rows: list[dict] = []
    try:
        r = httpx.get(f"{settings.openmeteo_base_url}/v1/forecast",
                      params={**coords, "hourly": ",".join(VARIABLES),
                              "models": ",".join(MODELS)},
                      timeout=30)
        r.raise_for_status()
        for station, resp in zip(stations, _as_list(r.json())):
            rows.extend(_parse_deterministic(station.id, run_at, resp))
    except Exception as e:
        log.warning("forecast fetch failed (%s); next cycle will retry", e)
        return {"error": str(e), "rows": 0}

    if settings.forecast_ensemble:
        try:
            r = httpx.get(f"{settings.openmeteo_ensemble_base_url}/v1/ensemble",
                          params={**coords, "hourly": "temperature_2m,precipitation",
                                  "models": "gfs025"},
                          timeout=30)
            r.raise_for_status()
            for station, resp in zip(stations, _as_list(r.json())):
                rows.extend(_parse_ensemble(station.id, run_at, resp))
        except Exception as e:
            log.warning("ensemble fetch failed (%s); deterministic rows kept", e)

    # Only persist model runs we don't already have. Polling hourly catches a
    # new run within the hour it lands, but the models themselves only publish
    # a few times a day — without this, most polls would write a fresh run_at
    # holding numbers identical to the last one, bloating the archive and
    # double-counting the same forecast in the skill statistics.
    by_pair: dict = {}
    for r in rows:
        by_pair.setdefault((r["station_id"], r["model"]), []).append(r)

    with engine.begin() as conn:
        snap = _latest_snapshot(conn)
        fresh, unchanged = [], 0
        for pair, group in by_pair.items():
            if _unchanged(snap.get(pair, {}), group):
                unchanged += 1
            else:
                fresh.extend(group)
        if fresh:
            conn.execute(_UPSERT, fresh)

    result = {"stations": len(stations), "rows": len(fresh),
              "updated_models": len(by_pair) - unchanged,
              "unchanged_models": unchanged, "run_at": run_at.isoformat()}
    log.info("forecast: %s", result)
    return result
