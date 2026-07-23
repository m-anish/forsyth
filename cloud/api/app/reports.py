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
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from .config import settings
from .db import engine

log = logging.getLogger("forsyth.reports")
router = APIRouter(prefix="/api/v1")

KIND_T = Literal["precip", "hail", "fog", "snow_line", "wind_damage",
                 "road_blocked", "flood"]
KINDS = ("precip", "hail", "fog", "snow_line", "wind_damage", "road_blocked", "flood")
RATE_10MIN, RATE_24H = 3, 20    # submissions (a composite counts once), not rows
MAX_OBS = 5              # observations per composite submission
QC_RADIUS_KM = 5.0       # a report is checkable if a fresh station is this close
FUZZ_DECIMALS = 3        # public coords rounded to ~110 m — homes are sensitive

# Weather-alert weighting (yellow/orange/red). A single voice — especially an
# anonymous one — must not turn a valley red; an alert is a weighted consensus.
# Each alert-flagged submission contributes  src_weight × recency  to every
# level at or below the one it claims; a level lights when its summed weight
# clears the threshold. So (⚙ all tunable):
#   1 anon (w 1.0) alone            → below yellow's 1.5, shows nothing
#   2 anon agreeing, or 1 member    → yellow
#   1 trusted observer's red (w 3)  → orange (needs a second voice for red)
#   2 trusted, or 1 trusted + 3 anon → red
ALERT_NAMES = {0: "none", 1: "yellow", 2: "orange", 3: "red"}
ALERT_WINDOW_H = 6
ALERT_RADIUS_KM = 15.0
ALERT_SRC_WEIGHT = {"anon": 1.0, "member": 1.5, "trusted": 3.0}
ALERT_LEVEL_THRESHOLD = {1: 1.5, 2: 3.0, 3: 5.0}

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


def station_alerts(conn) -> dict:
    """Effective weather-alert level per station, from recent alert-flagged
    report GROUPS weighted by reporter trust and recency (see the constants).
    Computed on read — always current, nothing to invalidate. Returns
    {slug: {name, level, score, contributors}} plus a mesh-wide max."""
    groups = conn.execute(text("""
        SELECT max(alert_level) AS lvl, avg(lat) AS lat, avg(lon) AS lon,
               max(reporter) AS reporter, max(ts) AS ts
        FROM obs_reports
        WHERE alert_level > 0 AND ts >= now() - make_interval(hours => :w)
        GROUP BY coalesce(report_group, id::text)"""),
        {"w": ALERT_WINDOW_H}).all()
    stations = conn.execute(text(
        "SELECT slug, name, lat, lon FROM stations "
        "WHERE lat IS NOT NULL AND lon IS NOT NULL")).all()
    trusted = trusted_reporters(conn) if groups else set()
    now = datetime.now(timezone.utc)

    out: dict = {}
    for s in stations:
        # summed weight for each level = Σ over groups claiming ≥ that level
        sums = {1: 0.0, 2: 0.0, 3: 0.0}
        contributors = 0
        for g in groups:
            if _km(s.lat, s.lon, g.lat, g.lon) > ALERT_RADIUS_KM:
                continue
            age_h = (now - g.ts).total_seconds() / 3600
            recency = max(0.0, 1.0 - age_h / ALERT_WINDOW_H)
            if recency <= 0:
                continue
            src = ("trusted" if g.reporter in trusted
                   else "member" if g.reporter else "anon")
            w = ALERT_SRC_WEIGHT[src] * recency
            for lvl in range(1, int(g.lvl) + 1):
                sums[lvl] += w
            contributors += 1
        level = 0
        for lvl in (1, 2, 3):
            if sums[lvl] >= ALERT_LEVEL_THRESHOLD[lvl]:
                level = lvl
        if level:
            out[s.slug] = {"name": s.name, "level": level,
                           "score": round(sums[level], 2),
                           "contributors": contributors}
    return {"stations": out, "mesh_level": max((v["level"] for v in out.values()),
                                               default=0)}


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


class Observation(BaseModel):
    kind: KIND_T
    intensity: int | None = Field(None, ge=0, le=3)


class ReportBody(BaseModel):
    """One submission at one place. Composite: `observations` may list several
    things seen at once (fog + rain + a blocked road). The old single-kind
    shape (`kind`/`intensity`) is still accepted. `alert_level` 0–3 optionally
    raises a weather alert (none/yellow/orange/red), weighted server-side."""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    observations: list[Observation] | None = None
    kind: KIND_T | None = None                 # legacy single form
    intensity: int | None = Field(None, ge=0, le=3)
    note: str | None = Field(None, max_length=140)
    alert_level: int = Field(0, ge=0, le=3)

    def obs_list(self) -> list[Observation]:
        obs = list(self.observations or [])
        if self.kind and not obs:              # legacy single-kind path
            obs = [Observation(kind=self.kind, intensity=self.intensity)]
        # de-dupe by kind, keeping the strongest intensity given
        by_kind: dict = {}
        for o in obs:
            cur = by_kind.get(o.kind)
            if cur is None or (o.intensity or 0) > (cur.intensity or 0):
                by_kind[o.kind] = o
        return list(by_kind.values())[:MAX_OBS]


@router.post("/reports", status_code=201)
def create_report(body: ReportBody, request: Request):
    if not settings.reports_enabled:
        raise HTTPException(404, "reports are disabled on this mesh")
    obs = body.obs_list()
    if not obs:
        raise HTTPException(422, "a report needs at least one observation")
    ch = _client_hash(request)
    from .accounts import current_user
    user = current_user(request)
    reporter = user["username"] if user else None
    group = secrets.token_hex(8)
    with engine.begin() as conn:
        # rate limit counts SUBMISSIONS (distinct groups), so a composite report
        # is one action, not one-per-observation
        n10, n24 = conn.execute(text("""
            SELECT count(DISTINCT coalesce(report_group, id::text))
                     FILTER (WHERE ts >= now() - INTERVAL '10 minutes'),
                   count(DISTINCT coalesce(report_group, id::text))
            FROM obs_reports
            WHERE client_hash = :h AND ts >= now() - INTERVAL '24 hours'"""),
            {"h": ch}).first()
        if n10 >= RATE_10MIN or n24 >= RATE_24H:
            raise HTTPException(429, "one report at a time, please — try again in a few minutes")
        ts = datetime.now(timezone.utc)
        out_obs = []
        for o in obs:
            qc_station, qc_flag = _qc(conn, o.kind, o.intensity, body.lat, body.lon)
            conn.execute(text("""
                INSERT INTO obs_reports
                    (ts, lat, lon, kind, intensity, note, reporter, client_hash,
                     qc_flag, qc_station, report_group, alert_level)
                VALUES (:ts, :lat, :lon, :kind, :intensity, :note, :reporter, :h,
                        :qc_flag, :qc_station, :grp, :alert)"""),
                {"ts": ts, "lat": body.lat, "lon": body.lon, "kind": o.kind,
                 "intensity": o.intensity, "note": body.note, "reporter": reporter,
                 "h": ch, "qc_flag": qc_flag, "qc_station": qc_station,
                 "grp": group, "alert": body.alert_level})
            out_obs.append({"kind": o.kind, "intensity": o.intensity, "qc_flag": qc_flag})
    log.info("report %s: %s alert=%s by=%s", group,
             ",".join(o["kind"] for o in out_obs),
             ALERT_NAMES[body.alert_level], reporter or "anon")
    return {"group": group, "ts": ts, "observations": out_obs,
            "alert_level": body.alert_level, "reporter": reporter}


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
               o.reporter, o.qc_flag, o.report_group, o.alert_level,
               s.name AS qc_station_name
        FROM obs_reports o LEFT JOIN stations s ON s.id = o.qc_station
        WHERE o.ts >= :since
    """
    params: dict = {"since": datetime.now(timezone.utc) - timedelta(hours=hours)}
    if kind:
        sql += " AND o.kind = :kind"
        params["kind"] = kind
    sql += " ORDER BY o.ts DESC LIMIT 800"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
        trusted = trusted_reporters(conn) if rows else set()

    # collapse a composite submission into one entry carrying all its kinds
    groups: dict = {}
    order: list = []
    for r in rows:
        key = r["report_group"] or f"_{r['id']}"
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "group": r["report_group"], "id": r["id"], "ts": r["ts"],
                "lat": round(r["lat"], FUZZ_DECIMALS), "lon": round(r["lon"], FUZZ_DECIMALS),
                "note": r["note"], "reporter": r["reporter"],
                "trusted": r["reporter"] in trusted, "alert_level": r["alert_level"],
                "qc_station_name": r["qc_station_name"], "observations": []}
            order.append(key)
        g["observations"].append({"kind": r["kind"], "intensity": r["intensity"],
                                  "qc_flag": r["qc_flag"]})
    return {"enabled": True, "reports": [groups[k] for k in order]}


@router.get("/alerts")
def list_alerts():
    """Effective weather-alert level per station (weighted human reports)."""
    if not settings.reports_enabled:
        return {"enabled": False, "mesh_level": 0, "stations": {}}
    with engine.connect() as conn:
        a = station_alerts(conn)
    return {"enabled": True, **a, "names": ALERT_NAMES}
