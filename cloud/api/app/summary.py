"""Weather summary: detects noteworthy events — observed in the recent data,
expected in the stored forecasts, and disagreements between the two — and, when
there are any, produces a 20–30 word plain-language summary in the house voice.
If OPENAI_API_KEY is configured the sentence is LLM-written; otherwise a
rule-based composer does a perfectly respectable job. Cached for 5 minutes.

Event kinds ending in `_expected` come from the latest stored model run
(jobs/forecast.py); `model_divergence` fires when the stations contradict the
model — which, in a valley the model can't see, is itself the warning.

GET /api/v1/summary            → mesh-wide
GET /api/v1/summary?slug=ridge → one station
"""
import logging
import math
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from .config import settings
from .db import engine

log = logging.getLogger("forsyth.summary")
router = APIRouter(prefix="/api/v1")

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 300  # seconds

_PERSONA = (
    "You are Forsyth, a quiet, old-fashioned weather station mesh — the relative who "
    "always knew it would rain. Dry, calm, understated; never dramatic, never corporate."
)


def _detect_events(slug: str | None) -> list[dict]:
    """Noteworthy present weather, from the last hour or three of data."""
    flt = "AND s.slug = :slug" if slug else ""
    p = {"slug": slug} if slug else {}
    events: list[dict] = []
    with engine.connect() as conn:
        # lightning in the last hour
        rows = conn.execute(text(f"""
            SELECT s.name, count(*) AS n, min(l.distance_km) AS nearest
            FROM lightning_events l JOIN stations s ON s.id = l.station_id
            WHERE l.ts >= now() - INTERVAL '1 hour' {flt}
            GROUP BY s.name"""), p).all()
        for name, n, nearest in rows:
            events.append({"kind": "lightning", "station": name, "count": n,
                           "nearest_km": round(nearest or 0)})

        # meaningful rain in the last hour (>2 mm)
        rows = conn.execute(text(f"""
            SELECT s.name, sum(r.rain_mm) AS mm
            FROM readings r JOIN stations s ON s.id = r.station_id
            WHERE r.ts >= now() - INTERVAL '1 hour' {flt}
            GROUP BY s.name HAVING sum(r.rain_mm) > 2"""), p).all()
        for name, mm in rows:
            events.append({"kind": "rain", "station": name, "mm_last_hour": round(mm, 1)})

        # strong gusts in the last 30 minutes (>10 m/s)
        rows = conn.execute(text(f"""
            SELECT s.name, max(r.wind_gust_ms) AS gust
            FROM readings r JOIN stations s ON s.id = r.station_id
            WHERE r.ts >= now() - INTERVAL '30 minutes' {flt}
            GROUP BY s.name HAVING max(r.wind_gust_ms) > 10"""), p).all()
        for name, gust in rows:
            events.append({"kind": "gusts", "station": name, "gust_ms": round(gust, 1)})

        # pressure falling fast (>2.5 hPa over 3 h)
        rows = conn.execute(text(f"""
            SELECT name, delta FROM (
                SELECT s.name,
                       (SELECT avg(pressure_pa) FROM readings
                        WHERE station_id = s.id AND ts >= now() - INTERVAL '30 minutes')
                     - (SELECT avg(pressure_pa) FROM readings
                        WHERE station_id = s.id
                          AND ts BETWEEN now() - INTERVAL '3 hours 30 minutes'
                                     AND now() - INTERVAL '3 hours') AS delta
                FROM stations s WHERE TRUE {flt.replace('s.slug', 'slug')}
            ) d WHERE delta < -250"""), p).all()
        for name, delta in rows:
            events.append({"kind": "pressure_falling", "station": name,
                           "hpa_3h": round(delta / 100, 1)})

        # air quality worth avoiding (PM2.5 > 90 µg/m³ over the last 30 min)
        rows = conn.execute(text(f"""
            SELECT s.name, avg(r.pm25) AS pm
            FROM readings r JOIN stations s ON s.id = r.station_id
            WHERE r.ts >= now() - INTERVAL '30 minutes' {flt}
            GROUP BY s.name HAVING avg(r.pm25) > 90"""), p).all()
        for name, pm in rows:
            events.append({"kind": "poor_air", "station": name, "pm25": round(pm)})

        events.extend(_detect_forecast_events(conn, flt, p, events))
        events.extend(_detect_report_events(conn, flt, p))
        events.extend(_detect_alert_events(conn, slug))
    return events


def _detect_alert_events(conn, slug) -> list[dict]:
    """Weighted community weather alerts (reports.station_alerts). These are the
    most urgent thing the banner can say, so they carry a high sort weight."""
    from .reports import station_alerts, ALERT_NAMES
    a = station_alerts(conn)
    events = []
    for s_slug, info in a["stations"].items():
        if slug and s_slug != slug:
            continue
        events.append({"kind": "weather_alert", "station": info["name"],
                       "level": info["level"], "level_name": ALERT_NAMES[info["level"]],
                       "reports": info["contributors"]})
    return events


# these kinds are worth a banner line from a single corroborated report;
# everything else needs two independent voices saying the same thing
_SEVERE_REPORT_KINDS = {"hail", "wind_damage", "road_blocked", "flood"}


def _detect_report_events(conn, flt: str, p: dict) -> list[dict]:
    """Human reports from the last 3 h, clustered by nearest station: two of a
    kind near the same station — or one severe one that's either sensor-
    corroborated or from a trusted observer — is an event. People are the
    sensor for what the BOM can't measure."""
    reports = conn.execute(text("""
        SELECT kind, intensity, lat, lon, qc_flag, reporter FROM obs_reports
        WHERE ts >= now() - INTERVAL '3 hours'""")).all()
    if not reports:
        return []
    from .reports import trusted_reporters
    trusted = trusted_reporters(conn)
    stations = conn.execute(text(f"""
        SELECT s.name, s.lat, s.lon FROM stations s
        WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL {flt}"""), p).all()
    if not stations:
        return []

    clusters: dict[tuple, dict] = {}
    for r in reports:
        best, best_km = None, 25.0
        for s in stations:
            d = math.hypot((s.lat - r.lat) * 111.32,
                           (s.lon - r.lon) * 111.32 * math.cos(math.radians(r.lat)))
            if d < best_km:
                best, best_km = s, d
        if best is None:
            continue
        c = clusters.setdefault((best.name, r.kind), {"n": 0, "corroborated": 0,
                                                      "trusted": 0})
        c["n"] += 1
        c["corroborated"] += r.qc_flag == "corroborated"
        c["trusted"] += r.reporter in trusted

    events = []
    for (name, kind), c in clusters.items():
        weighty = c["corroborated"] or c["trusted"]
        if c["n"] >= 2 or (weighty and kind in _SEVERE_REPORT_KINDS):
            events.append({"kind": "human_report", "what": kind, "n": c["n"],
                           "near": name, "corroborated": bool(c["corroborated"]),
                           "trusted_reporter": bool(c["trusted"])})
    return events


# latest stored run for this station+model — the anchor for every forecast query
_LATEST_RUN = ("(SELECT max(run_at) FROM forecasts "
               " WHERE station_id = f.station_id AND model = 'best_match')")


def _detect_forecast_events(conn, flt: str, p: dict, present: list[dict]) -> list[dict]:
    """Forward-looking events from the latest best_match run, plus divergence
    (stations contradicting the model right now)."""
    events: list[dict] = []
    raining_now = {e["station"] for e in present if e["kind"] == "rain"}

    # the model said no rain; the gauges disagree. Trust the gauges.
    rows = conn.execute(text(f"""
        SELECT s.name, obs.mm AS observed, fc.mm AS forecast
        FROM stations s
        JOIN LATERAL (
            SELECT sum(rain_mm) AS mm FROM readings
            WHERE station_id = s.id AND ts >= now() - INTERVAL '1 hour') obs ON TRUE
        LEFT JOIN LATERAL (
            SELECT sum(f.precip_mm) AS mm FROM forecasts f
            WHERE f.station_id = s.id AND f.model = 'best_match'
              AND f.run_at = {_LATEST_RUN}
              AND f.valid_at >  date_trunc('hour', now()) - INTERVAL '1 hour'
              AND f.valid_at <= date_trunc('hour', now()) + INTERVAL '1 hour') fc ON TRUE
        WHERE obs.mm > 1 AND fc.mm IS NOT NULL AND fc.mm < 0.2 {flt}"""), p).all()
    for name, observed, forecast in rows:
        events.append({"kind": "model_divergence", "station": name, "what": "rain",
                       "observed_mm": round(observed, 1), "forecast_mm": round(forecast, 1)})

    # pressure falling harder than the model expected (> 1.5 hPa beyond the trend)
    rows = conn.execute(text(f"""
        SELECT name, obs_delta, fc_delta FROM (
            SELECT s.name,
                   (SELECT avg(pressure_pa) FROM readings
                    WHERE station_id = s.id AND ts >= now() - INTERVAL '30 minutes')
                 - (SELECT avg(pressure_pa) FROM readings
                    WHERE station_id = s.id
                      AND ts BETWEEN now() - INTERVAL '3 hours 30 minutes'
                                 AND now() - INTERVAL '3 hours') AS obs_delta,
                   (SELECT f.pressure_pa - f2.pressure_pa
                    FROM forecasts f JOIN forecasts f2
                      ON f2.station_id = f.station_id AND f2.model = f.model
                     AND f2.run_at = f.run_at
                     AND f2.valid_at = date_trunc('hour', now()) - INTERVAL '3 hours'
                    WHERE f.station_id = s.id AND f.model = 'best_match'
                      AND f.run_at = {_LATEST_RUN}
                      AND f.valid_at = date_trunc('hour', now())) AS fc_delta
            FROM stations s WHERE TRUE {flt}
        ) d
        WHERE obs_delta IS NOT NULL AND fc_delta IS NOT NULL
          AND obs_delta - fc_delta < -150"""), p).all()
    for name, obs_delta, fc_delta in rows:
        events.append({"kind": "model_divergence", "station": name, "what": "pressure",
                       "observed_hpa_3h": round(obs_delta / 100, 1),
                       "forecast_hpa_3h": round(fc_delta / 100, 1)})

    # rain expected in the next 12 h (skip stations where it's already raining).
    # "within N h" is anchored to the first hour with MEANINGFUL rain (>0.5 mm)
    # — probability alone must not start the clock, or a 100%-chance drizzle
    # reads as an imminent downpour while the real rain sits six hours out.
    rows = conn.execute(text(f"""
        SELECT s.name,
               min(f.valid_at) FILTER (WHERE f.precip_mm > 0.5) AS first_at,
               sum(f.precip_mm) AS mm_12h,
               max(f.precip_mm) AS peak_mm_hr,
               max(f.precip_prob) AS prob
        FROM forecasts f JOIN stations s ON s.id = f.station_id
        WHERE f.model = 'best_match' AND f.run_at = {_LATEST_RUN}
          AND f.valid_at > now() AND f.valid_at <= now() + INTERVAL '12 hours' {flt}
        GROUP BY s.name
        HAVING min(f.valid_at) FILTER (WHERE f.precip_mm > 0.5) IS NOT NULL"""),
        p).all()
    now_utc = conn.execute(text("SELECT now()")).scalar()
    for name, first_at, mm_12h, peak_mm_hr, prob in rows:
        if name in raining_now:
            continue
        in_h = max(1, round((first_at - now_utc).total_seconds() / 3600))
        events.append({"kind": "rain_expected", "station": name, "in_hours": in_h,
                       "mm_12h": round(mm_12h or 0, 1),
                       "peak_mm_hr": round(peak_mm_hr or 0, 1),
                       "prob": round(prob) if prob is not None else None})

    # the next 24 h in one pass: frost, big swings, wind worth lashing down for
    rows = conn.execute(text(f"""
        SELECT s.name, min(f.temp_c) AS tmin, max(f.temp_c) AS tmax,
               max(f.wind_gust_ms) AS gust
        FROM forecasts f JOIN stations s ON s.id = f.station_id
        WHERE f.model = 'best_match' AND f.run_at = {_LATEST_RUN}
          AND f.valid_at > now() AND f.valid_at <= now() + INTERVAL '24 hours' {flt}
        GROUP BY s.name"""), p).all()
    for name, tmin, tmax, gust in rows:
        if tmin is not None and tmin < 2:
            events.append({"kind": "frost_expected", "station": name,
                           "min_c": round(tmin, 1)})
        if tmin is not None and tmax is not None and tmax - tmin > 12:
            events.append({"kind": "temp_swing", "station": name,
                           "min_c": round(tmin, 1), "max_c": round(tmax, 1)})
        if gust is not None and gust > 15:
            events.append({"kind": "wind_expected", "station": name,
                           "gust_ms": round(gust, 1)})
    return events


def _compose_template(events: list[dict]) -> str:
    """Rule-based fallback: one dry sentence, ~20–30 words."""
    bits = []
    # a community weather alert leads — it is the most urgent thing here
    alerts = [e for e in events if e["kind"] == "weather_alert"]
    if alerts:
        top = max(alerts, key=lambda e: e["level"])
        bits.append(f"{top['level_name']} alert near {top['station']} "
                    f"({top['reports']} report{'s' if top['reports'] != 1 else ''})")
    lightning = [e for e in events if e["kind"] == "lightning"]
    if lightning:
        near = min(e["nearest_km"] for e in lightning)
        where = ", ".join(sorted(e["station"] for e in lightning))
        bits.append(f"lightning within {near} km of {where}")
    rain = [e for e in events if e["kind"] == "rain"]
    if rain:
        worst = max(rain, key=lambda e: e["mm_last_hour"])
        bits.append(f"steady rain at {worst['station']} ({worst['mm_last_hour']} mm this hour)")
    gusts = [e for e in events if e["kind"] == "gusts"]
    if gusts:
        worst = max(gusts, key=lambda e: e["gust_ms"])
        bits.append(f"gusts to {worst['gust_ms']} m/s at {worst['station']}")
    falling = [e for e in events if e["kind"] == "pressure_falling"]
    if falling:
        bits.append("pressure falling fast" + (" across the mesh" if len(falling) > 1 else f" at {falling[0]['station']}"))
    air = [e for e in events if e["kind"] == "poor_air"]
    if air:
        bits.append(f"air worth avoiding at {air[0]['station']}")
    humans = [e for e in events if e["kind"] == "human_report"]
    if humans:
        e = max(humans, key=lambda e: (e["what"] in _SEVERE_REPORT_KINDS, e["n"]))
        what = {"precip": "rain", "snow_line": "snow"}.get(e["what"], e["what"].replace("_", " "))
        bits.append(f"people report {what} near {e['near']}"
                    + (f" (×{e['n']})" if e["n"] > 1 else ""))
    diverging = [e for e in events if e["kind"] == "model_divergence"]
    if diverging:
        e = diverging[0]
        what = "rain the forecast never mentioned" if e["what"] == "rain" \
            else "pressure falling harder than the model expected"
        bits.append(f"{what} at {e['station']}")
    expect_rain = [e for e in events if e["kind"] == "rain_expected"]
    if expect_rain:
        soonest = min(expect_rain, key=lambda e: e["in_hours"])
        bits.append(f"rain likely at {soonest['station']} within {soonest['in_hours']} h"
                    f" (~{soonest['mm_12h']} mm by then and after)")
    frost = [e for e in events if e["kind"] == "frost_expected"]
    if frost:
        coldest = min(frost, key=lambda e: e["min_c"])
        bits.append(f"frost expected at {coldest['station']} ({coldest['min_c']} °C overnight)")
    swing = [e for e in events if e["kind"] == "temp_swing"]
    if swing:
        e = swing[0]
        bits.append(f"a {round(e['max_c'] - e['min_c'])} °C swing ahead at {e['station']}")
    expect_wind = [e for e in events if e["kind"] == "wind_expected"]
    if expect_wind:
        worst = max(expect_wind, key=lambda e: e["gust_ms"])
        bits.append(f"gusts to {worst['gust_ms']} m/s expected at {worst['station']} within a day")

    if not bits:
        return ""
    sentence = "; ".join(bits[:3])
    sentence = sentence[0].upper() + sentence[1:]
    red = any(e["level"] == 3 for e in alerts)
    closer = (" Take care." if red else
              " People are raising the alarm; take it seriously." if alerts else
              " Forsyth suggests being near a roof." if (lightning or rain) else
              " Trust the sky, not the model." if diverging else
              " Forsyth suggests planning accordingly." if (expect_rain or frost or expect_wind) else
              " Forsyth is watching.")
    return sentence + "." + closer


_LANGS = {
    "en": "",
    "hi": "Write the summary in everyday Hindi (Devanagari script); keep "
          "station names and units in Latin script. ",
}


def _compose_llm(events: list[dict], lang: str = "en") -> str | None:
    if not settings.openai_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "gpt-5.1",
                "max_completion_tokens": 400,
                "messages": [
                    {"role": "system", "content": _PERSONA},
                    {"role": "user", "content":
                        "Current weather events from the station mesh, as JSON: "
                        f"{events}\n\nWrite ONE summary of 20-30 words for the dashboard "
                        "banner. Mention station names and the most important numbers. "
                        "A weather_alert event is a community-raised alert "
                        "(yellow/orange/red) and must LEAD the sentence, named by its "
                        "colour, calm but clear — it is the most urgent thing here. "
                        "Events whose kind ends in _expected come from a forecast — "
                        "phrase them as expectation, not observation. For rain_expected: "
                        "in_hours = first hour with meaningful rain; mm_12h = the TOTAL "
                        "over the next 12 hours (never imply it falls in the first hour); "
                        "peak_mm_hr = the wettest single hour; prob = hourly precipitation "
                        "probability — never call it confidence. Scale adjectives to "
                        "peak_mm_hr: under 1 is drizzle, 1-4 steady, above 5 heavy. "
                        "model_divergence "
                        "means the stations contradict the forecast: say so plainly; "
                        "the stations are the ones to believe. human_report events are "
                        "first-hand accounts from people nearby — credit them as such "
                        "('people report hail near Ridge'), especially when corroborated. "
                        "Dry and calm. No exclamation marks. Plain text only. "
                        + _LANGS.get(lang, "")},
                ],
            },
            timeout=20,
        )
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"].strip()
        return txt or None
    except Exception as e:
        log.warning("LLM summary failed (%s); using template", e)
        return None


@router.get("/summary")
def summary(slug: str | None = None, lang: str = "en"):
    if lang not in _LANGS:
        lang = "en"
    key = f"{slug or '__mesh__'}:{lang}"
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    events = _detect_events(slug)
    # when the events were detected — a cached response carries its true age,
    # so the dashboard can whisper "just now" or warn "2 h ago — may be stale"
    generated_at = datetime.now(timezone.utc).isoformat()
    if not events:
        result = {"events": [], "summary": None, "generated_by": None,
                  "generated_at": generated_at}
    else:
        text_ = _compose_llm(events, lang)
        result = {
            "events": events,
            "summary": text_ or _compose_template(events),
            "generated_by": "llm" if text_ else "rules",
            "generated_at": generated_at,
            "lang": lang if text_ else "en",
        }
    _CACHE[key] = (now, result)
    return result
