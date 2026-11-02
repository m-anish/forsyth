"""Google Flood Forecasting pull — riverine discharge for the reaches around
our stations. Findings that shaped this are in docs/flood-roadmap.md §0.1; the
ones that matter to the code:

  * There is no real gauge in this valley. Every reach that comes back is a
    virtual (HydroBASINS) one with quality_verified = false, which is why the
    search below has to pass includeNonQualityVerified — and why everything
    downstream carries that flag rather than dropping it.
  * Thresholds belong to a model, not a gauge: Google replace a model, issue a
    new gauge_model_id and new thresholds, and a value compared against the
    previous model's warning level is then silently wrong. So the model id is
    fetched alongside and stored with every forecast.
  * It is a DAILY product on an eight-day horizon, issued about once a day.
    Polling it more often than hourly buys nothing at all.

Budget: one search per day (Google ask that the gauge list not be cached "for
long periods of time" and call a day relatively safe), then two calls per cycle
regardless of how many reaches there are — batchGet and queryGaugeForecasts
both take the whole list. Against a 200/minute quota that is nothing.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from ..config import settings
from ..db import engine

log = logging.getLogger("forsyth.flood")

BASE = "https://floodforecasting.googleapis.com/v1"
# The documented caps are 500 ids for forecasts and 100,000 names for
# batchGet, and both are a red herring: these are GET requests carrying one
# query parameter per id, so the real limit is URL length. 500 names came to
# ~18 kB and earned a flat 400 Bad Request. 100 is ~4 kB, comfortably inside
# any 8 kB server limit, and costs a handful of extra calls against a 200/min
# budget we are nowhere near.
ID_CHUNK = 100


# Calls that came back as anything other than 200 this cycle. A chunked job
# that loses a chunk silently reports a smaller success, which is the worst of
# both worlds: nothing looks broken and the data is wrong. run() surfaces this.
_failures: list[str] = []


def _get(path: str, params=None, body=None) -> dict | None:
    """One call. The key goes in a header rather than the query string: a URL
    ends up in proxy logs and error messages, a header rather less often."""
    url = f"{BASE}/{path}"
    headers = {"X-Goog-Api-Key": settings.flood_api_key}
    try:
        if body is None:
            r = httpx.get(url, params=params, headers=headers, timeout=60)
        else:
            r = httpx.post(url, params=params, json=body, headers=headers, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        # Never let the key reach a log line, even in an exception's repr.
        msg = str(e)
        if settings.flood_api_key:
            msg = msg.replace(settings.flood_api_key, "***")
        body_txt = ""
        if isinstance(e, httpx.HTTPStatusError):
            body_txt = " · " + e.response.text[:200].replace("\n", " ")
        log.warning("flood %s failed: %s%s", path, msg, body_txt)
        _failures.append(path)
        return None


def _search_loop() -> dict:
    """The area to ask about: a box around our stations, padded. Deliberately
    wide — the useful reach is as likely to be downstream of a station as
    under it, and a tight box around a hilltop finds nothing."""
    with engine.connect() as conn:
        pts = conn.execute(text(
            "SELECT lat, lon FROM stations WHERE lat IS NOT NULL AND lon IS NOT NULL")).all()
    if not pts:
        return {}
    pad = settings.flood_search_pad_deg
    lats = [p.lat for p in pts]
    lons = [p.lon for p in pts]
    s, n = min(lats) - pad, max(lats) + pad
    w, e = min(lons) - pad, max(lons) + pad
    return {"loop": {"vertices": [
        {"latitude": s, "longitude": w}, {"latitude": s, "longitude": e},
        {"latitude": n, "longitude": e}, {"latitude": n, "longitude": w}]}}


def _refresh_gauges() -> list[str]:
    """Which reaches exist around us. Returns the stored gauge ids — including
    ones this search did not return, so a transient empty answer does not
    silently empty the widget."""
    loop = _search_loop()
    if loop:
        payload = {**loop,
                   "includeGaugesWithoutHydroModel": True,
                   # Required here: every reach in this valley is virtual and
                   # unverified, so without this the answer is zero gauges.
                   "includeNonQualityVerified": True}
        res = _get("gauges:searchGaugesByArea", body=payload)
        gauges = (res or {}).get("gauges", [])
        if gauges:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO flood_gauges (gauge_id, lat, lon, river, source,
                                              country_code, quality_verified, has_model)
                    VALUES (:gauge_id, :lat, :lon, :river, :source,
                            :country_code, :quality_verified, :has_model)
                    ON CONFLICT (gauge_id) DO UPDATE SET
                        lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                        river = EXCLUDED.river, source = EXCLUDED.source,
                        country_code = EXCLUDED.country_code,
                        quality_verified = EXCLUDED.quality_verified,
                        has_model = EXCLUDED.has_model, last_seen = now()
                """), [{
                    "gauge_id": g.get("gaugeId"),
                    "lat": (g.get("location") or {}).get("latitude"),
                    "lon": (g.get("location") or {}).get("longitude"),
                    "river": g.get("river"),
                    "source": g.get("source"),
                    "country_code": g.get("countryCode"),
                    "quality_verified": bool(g.get("qualityVerified")),
                    "has_model": bool(g.get("hasModel")),
                } for g in gauges if g.get("gaugeId")
                   and (g.get("location") or {}).get("latitude") is not None])
            log.info("flood: %d reach(es) in the search area", len(gauges))
    with engine.connect() as conn:
        return [r.gauge_id for r in conn.execute(text(
            "SELECT gauge_id FROM flood_gauges WHERE has_model ORDER BY gauge_id")).all()]


def _refresh_models(ids: list[str]) -> dict[str, str]:
    """Thresholds and units per model. Returns {gauge_id: gauge_model_id} so
    forecasts can be stored against the model they were actually made under."""
    current: dict[str, str] = {}
    rows = []
    for i in range(0, len(ids), ID_CHUNK):
        chunk = ids[i:i + ID_CHUNK]
        res = _get("gaugeModels:batchGet",
                   params=[("names", f"gaugeModels/{g}") for g in chunk])
        for m in (res or {}).get("gaugeModels", []):
            gid, mid = m.get("gaugeId"), m.get("gaugeModelId")
            if not gid or not mid:
                continue
            th = m.get("thresholds") or {}
            current[gid] = mid
            rows.append({"gauge_id": gid, "gauge_model_id": mid,
                         "value_unit": m.get("gaugeValueUnit"),
                         "warning_level": th.get("warningLevel"),
                         "danger_level": th.get("dangerLevel"),
                         "extreme_level": th.get("extremeDangerLevel"),
                         "quality_verified": bool(m.get("qualityVerified"))})
    if rows:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO flood_models (gauge_id, gauge_model_id, value_unit,
                    warning_level, danger_level, extreme_level, quality_verified)
                VALUES (:gauge_id, :gauge_model_id, :value_unit,
                    :warning_level, :danger_level, :extreme_level, :quality_verified)
                ON CONFLICT (gauge_id, gauge_model_id) DO UPDATE SET
                    value_unit = EXCLUDED.value_unit,
                    warning_level = EXCLUDED.warning_level,
                    danger_level = EXCLUDED.danger_level,
                    extreme_level = EXCLUDED.extreme_level,
                    quality_verified = EXCLUDED.quality_verified,
                    seen_at = now()
            """), rows)
    return current


def _refresh_status(ids: list[str]) -> int:
    n = 0
    for i in range(0, len(ids), ID_CHUNK):
        chunk = ids[i:i + ID_CHUNK]
        res = _get("floodStatus:queryLatestFloodStatusByGaugeIds",
                   params=[("gaugeIds", g) for g in chunk])
        rows = (res or {}).get("floodStatuses") or (res or {}).get("floodStatus") or []
        clean = [{"gauge_id": s.get("gaugeId"), "issued_time": s.get("issuedTime"),
                  "severity": s.get("severity"), "forecast_trend": s.get("forecastTrend"),
                  "quality_verified": bool(s.get("qualityVerified"))}
                 for s in rows if s.get("gaugeId")]
        if clean:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO flood_status (gauge_id, issued_time, severity,
                                              forecast_trend, quality_verified)
                    VALUES (:gauge_id, :issued_time, :severity,
                            :forecast_trend, :quality_verified)
                    ON CONFLICT (gauge_id) DO UPDATE SET
                        issued_time = EXCLUDED.issued_time,
                        severity = EXCLUDED.severity,
                        forecast_trend = EXCLUDED.forecast_trend,
                        quality_verified = EXCLUDED.quality_verified,
                        fetched_at = now()
                """), clean)
            n += len(clean)
    return n


def _refresh_forecasts(ids: list[str], models: dict[str, str],
                       since: str | None = None) -> int:
    """Store every issued run. `since` backfills — the archive answers from
    roughly mid-2025, which is how a monsoon can be studied without waiting
    for the next one (docs/flood-roadmap.md §0.1)."""
    rows = []
    for i in range(0, len(ids), ID_CHUNK):
        chunk = ids[i:i + ID_CHUNK]
        params = [("gaugeIds", g) for g in chunk]
        if since:
            params.append(("issuedTimeStart", since))
        res = _get("gauges:queryGaugeForecasts", params=params)
        for gid, fset in ((res or {}).get("forecasts") or {}).items():
            # The model a forecast was made under is not in the forecast, so
            # it is taken from the model fetched in the same cycle. A model
            # swapped between the two calls mislabels one cycle's rows; the
            # alternative is not storing the id at all, which mislabels every
            # comparison for ever.
            mid = models.get(gid)
            if not mid:
                continue
            for fc in fset.get("forecasts", []):
                issued = fc.get("issuedTime")
                for r in fc.get("forecastRanges", []):
                    if r.get("value") is None or not r.get("forecastStartTime"):
                        continue
                    rows.append({
                        "gauge_id": gid, "gauge_model_id": mid, "issued_time": issued,
                        "valid_start": r["forecastStartTime"],
                        "valid_end": r.get("forecastEndTime") or r["forecastStartTime"],
                        "value": r["value"]})
    if rows:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO flood_forecasts (gauge_id, gauge_model_id, issued_time,
                                             valid_start, valid_end, value)
                VALUES (:gauge_id, :gauge_model_id, :issued_time,
                        :valid_start, :valid_end, :value)
                ON CONFLICT (gauge_id, gauge_model_id, issued_time, valid_start)
                DO UPDATE SET value = EXCLUDED.value, valid_end = EXCLUDED.valid_end,
                              fetched_at = now()
            """), rows)
    return len(rows)


def _gauges_stale() -> bool:
    """Has it been a day since the last search? Google's own guidance on the
    gauge list is not to hold it "for long periods of time", with a day called
    relatively safe — so a day is exactly what we hold it for."""
    with engine.connect() as conn:
        newest = conn.execute(text("SELECT max(last_seen) FROM flood_gauges")).scalar()
    return newest is None or newest < datetime.now(timezone.utc) - timedelta(hours=24)


def run(backfill_since: str | None = None) -> dict:
    """Hourly. Pass backfill_since ('2025-06-01') to pull the archive instead."""
    if not settings.flood_enabled or not settings.flood_api_key:
        return {"disabled": True}
    _failures.clear()
    ids = _refresh_gauges() if (_gauges_stale() or backfill_since) else None
    if ids is None:
        with engine.connect() as conn:
            ids = [r.gauge_id for r in conn.execute(text(
                "SELECT gauge_id FROM flood_gauges WHERE has_model ORDER BY gauge_id")).all()]
    if not ids:
        log.info("flood: no reaches with a model in the search area")
        return {"gauges": 0, "rows": 0}

    models = _refresh_models(ids)
    status = _refresh_status(ids)
    rows = _refresh_forecasts(ids, models, since=backfill_since)
    result = {"gauges": len(ids), "models": len(models),
              "status": status, "rows": rows,
              **({"backfill_since": backfill_since} if backfill_since else {})}
    if _failures:
        # Loud, because the alternative is a result that looks fine while a
        # chunk of the valley is missing from it.
        result["failed_calls"] = len(_failures)
        result["incomplete"] = True
        log.error("flood: %d call(s) failed this cycle: %s", len(_failures),
                  sorted(set(_failures)))
    log.info("flood: %s", result)
    return result
