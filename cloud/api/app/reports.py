"""Human weather reports — the mesh's eyes (insight-roadmap §3, engagement-
roadmap §3). Anonymous-first: one tap must be enough, so identity is optional
and rate limiting rides on an HMAC of ip|user-agent — no raw PII stored.
Every report is QC'd inline against the nearest fresh station and marked
corroborated / contradicted / no_station. A contradicted report near a station
is a signal to inspect, not spam — sometimes the human is right and the sensor
is wrong, and that disagreement is QC gold either way.

    POST /api/v1/reports                     (public, rate-limited, 201)
    GET  /api/v1/reports?hours=&kind=        (public; coords rounded ~100 m)

Kill switch: REPORTS_ENABLED=false → POST 404s, GET answers {"enabled": false}
so the dashboard quietly hides the whole feature.
"""
import hashlib
import hmac
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from .config import settings
from .db import engine

log = logging.getLogger("forsyth.reports")
router = APIRouter(prefix="/api/v1")

KINDS = ("precip", "hail", "fog", "snow_line", "wind_damage", "road_blocked", "flood")
RATE_10MIN, RATE_24H = 3, 20
QC_RADIUS_KM = 5.0       # a report is checkable if a fresh station is this close
FUZZ_DECIMALS = 3        # public coords rounded to ~110 m — homes are sensitive

# Trusted observer (engagement-roadmap §3): earned mechanically — enough
# sensor-corroborated reports, few contradicted ones, in a rolling window.
# Gaming this requires being reliably right about the weather.
TRUST_WINDOW_DAYS = 90
TRUST_MIN_CORROBORATED = 5
TRUST_MAX_CONTRA_RATIO = 0.25


def trusted_reporters(conn) -> set[str]:
    """Signed-in reporters whose track record earns extra weight."""
    rows = conn.execute(text("""
        SELECT reporter,
               count(*) FILTER (WHERE qc_flag = 'corroborated') AS ok,
               count(*) FILTER (WHERE qc_flag = 'contradicted') AS bad
        FROM obs_reports
        WHERE reporter IS NOT NULL
          AND ts >= now() - make_interval(days => :w)
        GROUP BY reporter"""), {"w": TRUST_WINDOW_DAYS}).all()
    return {r.reporter for r in rows
            if r.ok >= TRUST_MIN_CORROBORATED
            and r.bad <= r.ok * TRUST_MAX_CONTRA_RATIO}


def reporter_stats(conn, username: str) -> dict:
    """The numbers behind attribution: totals, corroboration, streak, trust."""
    total, ok, bad = conn.execute(text("""
        SELECT count(*),
               count(*) FILTER (WHERE qc_flag = 'corroborated'),
               count(*) FILTER (WHERE qc_flag = 'contradicted')
        FROM obs_reports
        WHERE reporter = :u AND ts >= now() - make_interval(days => :w)"""),
        {"u": username, "w": TRUST_WINDOW_DAYS}).first()
    days = [r[0] for r in conn.execute(text("""
        SELECT DISTINCT (ts AT TIME ZONE 'UTC')::date FROM obs_reports
        WHERE reporter = :u ORDER BY 1 DESC LIMIT 60"""), {"u": username}).all()]
    # streak = consecutive days with a report, still alive today or yesterday
    streak = 0
    expect = datetime.now(timezone.utc).date()
    if days and days[0] == expect - timedelta(days=1):
        expect = days[0]
    for d in days:
        if d != expect:
            break
        streak += 1
        expect -= timedelta(days=1)
    return {"total_90d": total, "corroborated": ok, "contradicted": bad,
            "streak_days": streak,
            "trusted": ok >= TRUST_MIN_CORROBORATED
                       and bad <= ok * TRUST_MAX_CONTRA_RATIO}


def _client_hash(request: Request) -> str:
    """Stable per-client token for rate limiting; stores no raw IP or UA."""
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else ""))
    ua = request.headers.get("user-agent", "")
    secret = hashlib.sha256(b"forsyth-report:" + settings.admin_key.encode()).digest()
    return hmac.new(secret, f"{ip}|{ua}".encode(), hashlib.sha256).hexdigest()[:32]


def _km(lat1, lon1, lat2, lon2) -> float:
    """Planar approximation — honest at valley scale, which is all QC needs."""
    return math.hypot((lat2 - lat1) * 111.32,
                      (lon2 - lon1) * 111.32 * math.cos(math.radians(lat1)))


def _qc(conn, kind: str, intensity: int | None, lat: float, lon: float):
    """Cross-check against the nearest station heard from in the last 15 min.
    Only rules with a sensor to back them return a verdict; everything else
    stays NULL (unverifiable ≠ wrong)."""
    rows = conn.execute(text("""
        SELECT s.id, s.lat, s.lon, r.rh, r.wind_gust_ms,
               (SELECT sum(rain_mm) FROM readings
                WHERE station_id = s.id AND ts >= now() - INTERVAL '30 minutes') AS rain30
        FROM stations s
        JOIN LATERAL (SELECT rh, wind_gust_ms, ts FROM readings
                      WHERE station_id = s.id ORDER BY ts DESC LIMIT 1) r ON TRUE
        WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
          AND r.ts >= now() - INTERVAL '15 minutes'""")).all()
    best, best_km = None, QC_RADIUS_KM
    for row in rows:
        d = _km(lat, lon, row.lat, row.lon)
        if d <= best_km:
            best, best_km = row, d
    if best is None:
        return None, "no_station"
    verdict = None
    if kind == "precip":
        if (best.rain30 or 0) > 0.2:
            verdict = "corroborated"
        elif (intensity or 0) >= 2:
            verdict = "contradicted"
    elif kind == "fog" and best.rh is not None:
        verdict = ("corroborated" if best.rh > 95
                   else "contradicted" if best.rh < 70 else None)
    elif kind == "wind_damage" and best.wind_gust_ms is not None:
        verdict = "corroborated" if best.wind_gust_ms > 10 else None
    return best.id, verdict


class ReportBody(BaseModel):
    kind: Literal["precip", "hail", "fog", "snow_line", "wind_damage",
                  "road_blocked", "flood"]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    intensity: int | None = Field(None, ge=0, le=3)
    note: str | None = Field(None, max_length=140)


@router.post("/reports", status_code=201)
def create_report(body: ReportBody, request: Request):
    if not settings.reports_enabled:
        raise HTTPException(404, "reports are disabled on this mesh")
    ch = _client_hash(request)
    from .accounts import current_user
    user = current_user(request)
    with engine.begin() as conn:
        n10, n24 = conn.execute(text("""
            SELECT count(*) FILTER (WHERE ts >= now() - INTERVAL '10 minutes'),
                   count(*)
            FROM obs_reports
            WHERE client_hash = :h AND ts >= now() - INTERVAL '24 hours'"""),
            {"h": ch}).first()
        if n10 >= RATE_10MIN or n24 >= RATE_24H:
            raise HTTPException(429, "one report at a time, please — try again in a few minutes")
        qc_station, qc_flag = _qc(conn, body.kind, body.intensity, body.lat, body.lon)
        row = conn.execute(text("""
            INSERT INTO obs_reports
                (lat, lon, kind, intensity, note, reporter, client_hash,
                 qc_flag, qc_station)
            VALUES (:lat, :lon, :kind, :intensity, :note, :reporter, :h,
                    :qc_flag, :qc_station)
            RETURNING id, ts"""),
            {"lat": body.lat, "lon": body.lon, "kind": body.kind,
             "intensity": body.intensity, "note": body.note,
             "reporter": user["username"] if user else None, "h": ch,
             "qc_flag": qc_flag, "qc_station": qc_station}).first()
    log.info("report #%s: %s i=%s qc=%s by=%s", row.id, body.kind,
             body.intensity, qc_flag, user["username"] if user else "anon")
    return {"id": row.id, "ts": row.ts, "kind": body.kind, "qc_flag": qc_flag,
            "reporter": user["username"] if user else None}


@router.get("/reports")
def list_reports(
    hours: float = Query(24, gt=0, le=24 * 31),
    kind: str | None = None,
):
    if not settings.reports_enabled:
        return {"enabled": False, "reports": []}
    if kind is not None and kind not in KINDS:
        raise HTTPException(400, f"unknown kind; have: {sorted(KINDS)}")
    sql = """
        SELECT o.id, o.ts, o.lat, o.lon, o.kind, o.intensity, o.note,
               o.reporter, o.qc_flag, s.name AS qc_station_name
        FROM obs_reports o LEFT JOIN stations s ON s.id = o.qc_station
        WHERE o.ts >= :since
    """
    params: dict = {"since": datetime.now(timezone.utc) - timedelta(hours=hours)}
    if kind:
        sql += " AND o.kind = :kind"
        params["kind"] = kind
    sql += " ORDER BY o.ts DESC LIMIT 500"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
        trusted = trusted_reporters(conn) if rows else set()
    return {"enabled": True, "reports": [
        {**dict(r), "lat": round(r["lat"], FUZZ_DECIMALS),
         "lon": round(r["lon"], FUZZ_DECIMALS),
         "trusted": r["reporter"] in trusted}
        for r in rows
    ]}
