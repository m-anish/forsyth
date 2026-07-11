"""Present-weather summary: detects noteworthy events in the recent data and,
when there are any, produces a 20–30 word plain-language summary in the house
voice. If OPENAI_API_KEY is configured the sentence is LLM-written; otherwise a
rule-based composer does a perfectly respectable job. Cached for 5 minutes.

GET /api/v1/summary            → mesh-wide
GET /api/v1/summary?slug=ridge → one station
"""
import logging
import time

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
    return events


def _compose_template(events: list[dict]) -> str:
    """Rule-based fallback: one dry sentence, ~20–30 words."""
    bits = []
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

    if not bits:
        return ""
    sentence = "; ".join(bits[:3])
    sentence = sentence[0].upper() + sentence[1:]
    closer = " Forsyth suggests being near a roof." if (lightning or rain) else " Forsyth is watching."
    return sentence + "." + closer


def _compose_llm(events: list[dict]) -> str | None:
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
                        "Dry and calm. No exclamation marks. Plain text only."},
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
def summary(slug: str | None = None):
    key = slug or "__mesh__"
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    events = _detect_events(slug)
    if not events:
        result = {"events": [], "summary": None, "generated_by": None}
    else:
        text_ = _compose_llm(events)
        result = {
            "events": events,
            "summary": text_ or _compose_template(events),
            "generated_by": "llm" if text_ else "rules",
        }
    _CACHE[key] = (now, result)
    return result
