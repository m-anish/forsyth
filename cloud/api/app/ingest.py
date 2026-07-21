"""Write paths: readings (single or batch), lightning, camera frames,
station creation. Everything a leaf's data does on arrival starts here."""
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import secrets

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import text

from .auth import AdminDep, StationDep, hash_key, new_station_key, require_station
from .config import settings
from .db import engine

log = logging.getLogger("forsyth.ingest")
router = APIRouter(prefix="/api/v1")

READING_FIELDS = [
    "temp_c", "rh", "pressure_pa", "wind_avg_ms", "wind_gust_ms", "wind_dir_deg",
    "rain_mm", "pm1", "pm25", "pm10", "batt_v", "solar_state", "rssi_dbm",
]

_INSERT_READING = text(
    f"""INSERT INTO readings (station_id, ts, {', '.join(READING_FIELDS)})
        VALUES (:station_id, :ts, {', '.join(':' + f for f in READING_FIELDS)})
        ON CONFLICT (station_id, ts) DO NOTHING"""
)

_INSERT_LIGHTNING = text(
    """INSERT INTO lightning_events (station_id, ts, distance_km, energy, count)
       VALUES (:station_id, :ts, :distance_km, :energy, :count)
       ON CONFLICT (station_id, ts) DO NOTHING"""
)


class Lightning(BaseModel):
    ts: datetime | None = None
    distance_km: float | None = None
    energy: float | None = None
    count: int = 1


class Reading(BaseModel):
    ts: datetime | None = None
    temp_c: float | None = None
    rh: float | None = Field(None, ge=0, le=100)
    pressure_pa: float | None = Field(None, gt=30000, lt=120000)
    wind_avg_ms: float | None = Field(None, ge=0)
    wind_gust_ms: float | None = Field(None, ge=0)
    wind_dir_deg: float | None = Field(None, ge=0, lt=360)
    rain_mm: float | None = Field(None, ge=0)
    pm1: float | None = Field(None, ge=0)
    pm25: float | None = Field(None, ge=0)
    pm10: float | None = Field(None, ge=0)
    batt_v: float | None = Field(None, ge=0, le=6)
    solar_state: str | None = None
    rssi_dbm: float | None = None
    lightning: list[Lightning] = []


class IngestBody(BaseModel):
    """Either a single reading's fields inline, or a batch under `readings`."""
    readings: list[Reading] | None = None
    # inline single-reading fields (all optional; validated via Reading below)
    model_config = {"extra": "allow"}


def store_readings(station_id: int, readings: list[Reading]) -> int:
    now = datetime.now(timezone.utc)
    rows, strikes = [], []
    for r in readings:
        ts = r.ts or now
        rows.append({"station_id": station_id, "ts": ts,
                     **{f: getattr(r, f) for f in READING_FIELDS}})
        for i, ev in enumerate(r.lightning):
            # strikes without their own ts inherit the reading's, offset by a
            # microsecond each so a multi-strike payload doesn't collide on PK
            strikes.append({"station_id": station_id,
                            "ts": ev.ts or (ts + timedelta(microseconds=i)),
                            "distance_km": ev.distance_km, "energy": ev.energy,
                            "count": ev.count})
    with engine.begin() as conn:
        if rows:
            conn.execute(_INSERT_READING, rows)
        if strikes:
            conn.execute(_INSERT_LIGHTNING, strikes)
    return len(rows)


@router.post("/ingest")
def ingest(body: dict, station: dict = StationDep):
    """Accepts `{...reading fields...}` or `{"readings": [{...}, ...]}` (backfill)."""
    try:
        if "readings" in body and isinstance(body["readings"], list):
            readings = [Reading.model_validate(r) for r in body["readings"]]
            if len(readings) > 5000:
                raise HTTPException(413, "batch too large (max 5000)")
        else:
            readings = [Reading.model_validate(body)]
    except HTTPException:
        raise
    except Exception as e:  # pydantic ValidationError → 422 with detail
        raise HTTPException(422, str(e))
    n = store_readings(station["id"], readings)
    return {"ok": True, "stored": n}


def _station_or_admin(slug: str, request: Request) -> dict:
    """Frames may be posted with the station's own key or the admin key
    (the skycam simulator uses the latter; real cameras get station keys)."""
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if settings.admin_key and token and secrets.compare_digest(token, settings.admin_key):
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, slug, name, is_simulated FROM stations WHERE slug = :s"),
                {"s": slug},
            ).mappings().first()
        if row is None:
            raise HTTPException(404, "no such station")
        return dict(row)
    return require_station(request)


@router.post("/stations/{slug}/frames")
async def upload_frame(
    slug: str,
    request: Request,
    ts: datetime | None = None,   # capture time (?ts=ISO); default now — used by backfill
    frame: UploadFile = File(...),
):
    station = _station_or_admin(slug, request)
    if station["slug"] != slug:
        raise HTTPException(403, "key does not belong to this station")
    if frame.content_type not in ("image/jpeg", "image/jpg"):
        raise HTTPException(415, "JPEG only")
    data = await frame.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "frame too large (max 5 MB)")

    ts = ts or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    rel = Path("frames") / slug / ts.strftime("%Y-%m-%d") / (ts.strftime("%H%M%S") + ".jpg")
    dest = Path(settings.media_root) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO camera_frames (station_id, ts, path)
                    VALUES (:sid, :ts, :path) ON CONFLICT DO NOTHING"""),
            {"sid": station["id"], "ts": ts, "path": str(rel)},
        )
    return {"ok": True, "path": str(rel)}


class StationCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,30}$")
    name: str
    lat: float | None = None
    lon: float | None = None
    elevation_m: float | None = None
    is_simulated: bool = False
    sensors: int = 0
    wu_station_id: str | None = None
    wu_station_key: str | None = None


# --- station location: one validated writer, two callers (PATCH + MQTT meta) ---
# Location is the station's canonical metadata (see docs); everything that sets
# it funnels through here so the HTTP editor and the coordinator's meta push
# validate identically and can never diverge in what they accept.
_LOCATION_FIELDS = ("name", "lat", "lon", "elevation_m")
# Operational metadata. Deliberately NOT in _LOCATION_FIELDS: the MQTT `meta`
# handler feeds device-supplied JSON into the same writer, and a coordinator
# must never be able to set a host's phone number. Admin PATCH only.
_OPS_FIELDS = ("contact_name", "contact_phone", "installed_on", "hardware_rev",
               "notes")


def _validate_location(lat=None, lon=None, elevation_m=None):
    """Raise HTTPException(422) on out-of-range coordinates. None passes (means
    'leave unchanged' on a partial update / 'not provided' from a device)."""
    if lat is not None and not (-90 <= lat <= 90):
        raise HTTPException(422, "lat out of range [-90, 90]")
    if lon is not None and not (-180 <= lon <= 180):
        raise HTTPException(422, "lon out of range [-180, 180]")
    if elevation_m is not None and not (-500 <= elevation_m <= 9000):
        raise HTTPException(422, "elevation_m out of range [-500, 9000]")


def apply_station_location(slug: str, fields: dict, allow=_LOCATION_FIELDS) -> bool:
    """Partial-update a station's metadata. Only the keys present in `fields`
    AND permitted by `allow` are written — omitted columns keep their value,
    and the API key is never touched. Returns False if the slug doesn't exist.

    `allow` is the privilege boundary: the MQTT `meta` handler takes the
    default (location only, since the payload comes from a device), while the
    admin PATCH widens it to include _OPS_FIELDS."""
    updates = {k: v for k, v in fields.items() if k in allow}
    if not updates:
        return True
    _validate_location(updates.get("lat"), updates.get("lon"),
                       updates.get("elevation_m"))
    sets = ", ".join(f"{k} = :{k}" for k in updates)
    with engine.begin() as conn:
        n = conn.execute(
            text(f"UPDATE stations SET {sets} WHERE slug = :slug"),
            {**updates, "slug": slug},
        ).rowcount
    if n:
        # keys only — the values include personal data and must not reach logs
        log.info("station %s metadata updated: %s", slug, sorted(updates))
    return bool(n)


class StationUpdate(BaseModel):
    """Partial metadata update. Every field optional; unset fields untouched.
    Deliberately cannot change the API key, is_simulated, or WU credentials —
    it edits metadata, it does not re-register."""
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    elevation_m: float | None = None
    # operational, admin-only, never public (see _OPS_FIELDS)
    contact_name: str | None = Field(None, max_length=80)
    contact_phone: str | None = Field(None, max_length=40)
    installed_on: date | None = None
    hardware_rev: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=2000)


@router.post("/stations", status_code=201)
def create_station(body: StationCreate, request: Request):
    from .accounts import require_admin
    require_admin(request)  # ADMIN_KEY bearer or is_admin session
    """Create a station (or rotate its key if the slug exists).
    Returns the plaintext API key — the only time it is ever shown."""
    key = new_station_key()
    with engine.begin() as conn:
        row = conn.execute(
            text("""INSERT INTO stations
                        (slug, name, lat, lon, elevation_m, api_key_hash,
                         is_simulated, sensors, wu_station_id, wu_station_key)
                    VALUES (:slug, :name, :lat, :lon, :elevation_m, :h,
                            :is_simulated, :sensors, :wu_station_id, :wu_station_key)
                    ON CONFLICT (slug) DO UPDATE
                        SET name = EXCLUDED.name,
                            lat = EXCLUDED.lat, lon = EXCLUDED.lon,
                            elevation_m = EXCLUDED.elevation_m,
                            api_key_hash = EXCLUDED.api_key_hash,
                            is_simulated = EXCLUDED.is_simulated,
                            sensors = EXCLUDED.sensors,
                            wu_station_id = EXCLUDED.wu_station_id,
                            wu_station_key = EXCLUDED.wu_station_key
                    RETURNING id"""),
            {**body.model_dump(), "h": hash_key(key)},
        ).first()
    log.info("station %s created/rekeyed (id=%s)", body.slug, row[0])
    return {"id": row[0], "slug": body.slug, "api_key": key}


@router.get("/admin/stations")
def admin_list_stations(request: Request):
    """Stations WITH their operational metadata (contact details, notes). The
    public GET /stations deliberately selects a fixed column list and will
    never carry these — this is the only way they leave the database."""
    from .accounts import require_admin
    require_admin(request)
    cols = ("slug", "name", "lat", "lon", "elevation_m", "is_simulated",
            *_OPS_FIELDS)
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT {', '.join(cols)} FROM stations ORDER BY slug")).mappings().all()
    return {"stations": [dict(r) for r in rows]}


@router.patch("/stations/{slug}")
def update_station(slug: str, body: StationUpdate, request: Request):
    """Edit a station's metadata (name / location) WITHOUT rotating its API key
    or nulling untouched fields — the safe alternative to re-POSTing. Only the
    fields present in the request body are written."""
    from .accounts import require_admin
    require_admin(request)
    fields = body.model_dump(exclude_unset=True)
    # admin path: location fields plus the operational/private ones
    if not apply_station_location(slug, fields, _LOCATION_FIELDS + _OPS_FIELDS):
        raise HTTPException(404, "no such station")
    return {"ok": True, "slug": slug, "updated": sorted(fields)}


@router.delete("/stations/{slug}")
def delete_station(slug: str, request: Request):
    from .accounts import require_admin
    require_admin(request)
    with engine.begin() as conn:
        n = conn.execute(text("DELETE FROM stations WHERE slug = :s"), {"s": slug}).rowcount
    if not n:
        raise HTTPException(404, "no such station")
    return {"ok": True}
