"""A small synthetic Himalayan-foothills climate.

Pure function of (slug, datetime): the same instant always produces the same
weather, so backfill and the live loop agree, and skycam's sky matches sim's
numbers. Noise comes from hashed RNGs, storms from a per-day hash — no state.
"""
import hashlib
import math
import random
from datetime import datetime, timedelta, timezone

STATIONS = {
    # slug: (name, lat, lon, elevation_m, temp_offset, prevailing_dir_deg)
    "ridge":   ("Ridge",   29.462, 79.612, 1830.0, -2.0, 300.0),
    "orchard": ("Orchard", 29.449, 79.634, 1650.0,  0.0, 280.0),
    "gate":    ("Gate",    29.441, 79.598, 1540.0, +1.5, 260.0),
}


def _rng(*parts) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _storm(slug: str, t: datetime) -> float:
    """0..1 storm intensity at time t. Monsoon afternoons brood; some days burst."""
    day = t.date().isoformat()
    r = _rng("storm", slug, day)
    if r.random() > 0.35:                       # most days: no storm
        return 0.0
    peak_h = r.uniform(13.0, 19.0)              # afternoon/evening event
    width_h = r.uniform(0.8, 2.5)
    strength = r.uniform(0.4, 1.0)
    hour = t.hour + t.minute / 60
    return strength * math.exp(-((hour - peak_h) ** 2) / (2 * width_h ** 2))


def sample(slug: str, t: datetime) -> dict:
    """One reading's worth of plausible weather for station `slug` at UTC time t."""
    _name, _lat, _lon, elev, t_off, prevail = STATIONS[slug]

    # local solar time ≈ UTC+5.5 in the Kumaon hills
    lt = t + timedelta(hours=5.5)
    hour = lt.hour + lt.minute / 60
    doy = lt.timetuple().tm_yday
    n = _rng(slug, t.replace(second=0, microsecond=0).isoformat())

    storm = _storm(slug, t)
    season = 6.0 * math.sin((doy - 105) / 365 * 2 * math.pi)          # warm May–Sep
    diurnal = 5.5 * math.sin((hour - 9) / 24 * 2 * math.pi)
    temp = 16.0 + t_off + season + diurnal - 4.0 * storm + n.gauss(0, 0.3)

    rh = 62 + 18 * math.sin((hour - 3) / 24 * 2 * math.pi) + 28 * storm + n.gauss(0, 2)
    rh = max(20.0, min(100.0, rh))

    p0 = 101325 * (1 - 2.25577e-5 * elev) ** 5.25588                  # barometric alt.
    slow = 250 * math.sin(doy / 5.3) + 120 * math.sin(hour / 24 * 4 * math.pi)
    pressure = p0 + slow - 600 * storm + n.gauss(0, 15)

    wind = max(0.0, 1.2 + 1.8 * math.sin((hour - 12) / 24 * 2 * math.pi)
               + 6.0 * storm + n.gauss(0, 0.4))
    gust = wind * (1.3 + 0.9 * storm + abs(n.gauss(0, 0.15)))
    wdir = (prevail + 25 * math.sin(hour / 24 * 2 * math.pi)
            + 70 * storm * math.sin(hour * 2.1) + n.gauss(0, 8)) % 360

    rain = 0.0
    if storm > 0.25:
        rain = round(max(0.0, n.gauss(storm * 4.0, 1.0)), 1)          # mm per 5-min

    pm_base = 28 + 14 * math.sin((hour - 8) / 24 * 4 * math.pi)       # traffic-ish peaks
    washout = max(0.15, 1.0 - 1.6 * storm)
    pm25 = max(2.0, (pm_base + n.gauss(0, 3)) * washout)
    pm1, pm10 = pm25 * 0.55, pm25 * 1.7

    solar_in = max(0.0, math.sin((hour - 6) / 12 * math.pi)) if 6 <= hour <= 18 else 0.0
    solar_in *= (1.0 - 0.75 * storm)
    batt = 3.28 + 0.14 * solar_in - 0.06 * math.sin((hour + 3) / 24 * 2 * math.pi) \
        + n.gauss(0, 0.005)
    solar_state = "charging" if solar_in > 0.25 else ("float" if batt > 3.38 else "discharging")

    lightning = []
    if storm > 0.5 and n.random() < storm * 0.55:
        for _ in range(n.randint(1, 3)):
            lightning.append({
                "distance_km": round(max(1.0, n.gauss(18 * (1.1 - storm), 6)), 1),
                "energy": round(n.uniform(20000, 250000)),
            })

    return {
        "temp_c": round(temp, 2), "rh": round(rh, 1), "pressure_pa": round(pressure, 0),
        "wind_avg_ms": round(wind, 2), "wind_gust_ms": round(gust, 2),
        "wind_dir_deg": round(wdir, 1), "rain_mm": rain,
        "pm1": round(pm1, 1), "pm25": round(pm25, 1), "pm10": round(pm10, 1),
        "batt_v": round(batt, 3), "solar_state": solar_state,
        "rssi_dbm": round(-72 - 18 * storm + n.gauss(0, 3), 0),
        "lightning": lightning,
        "_storm": storm, "_solar": solar_in,   # skycam uses these; API ignores extras
    }
