"""Synthetic sky camera: renders what the sky over SKYCAM_STATION plausibly
looks like (same weather function as sim.py) and posts frames through the real
camera API — so the timelapse pipeline runs long before a real camera exists.

On first boot (SKYCAM_BACKFILL=1) it uploads yesterday's daylight frames so the
nightly timelapse job has a complete day to encode immediately.
"""
import io
import logging
import math
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from PIL import Image, ImageDraw, ImageFilter

from weather import sample, _rng

logging.basicConfig(level=logging.INFO, format="%(asctime)s skycam %(levelname)s %(message)s")
log = logging.getLogger("skycam")

API = os.environ.get("API_BASE", "http://api:8000")
ADMIN_KEY = os.environ["ADMIN_KEY"]
STATION = os.environ.get("SKYCAM_STATION", "ridge")
INTERVAL_S = int(os.environ.get("SKYCAM_INTERVAL_S", "180"))
DO_BACKFILL = os.environ.get("SKYCAM_BACKFILL", "1") == "1"
W, H = 640, 360


def _lerp(a, b, f):
    return tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))


def render(t: datetime) -> bytes:
    """A quiet little sky: gradient by sun height, clouds by storminess."""
    wx = sample(STATION, t)
    storm, solar = wx["_storm"], wx["_solar"]
    lt = t + timedelta(hours=5.5)
    hour = lt.hour + lt.minute / 60

    sun_h = math.sin((hour - 6) / 12 * math.pi) if 6 <= hour <= 18 else -0.3
    if sun_h > 0.15:      # day
        top, bottom = _lerp((30, 60, 110), (90, 140, 190), sun_h), (200, 210, 215)
    elif sun_h > -0.05:   # golden hour
        top, bottom = (60, 55, 90), (225, 140, 90)
    else:                 # night
        top, bottom = (8, 10, 18), (22, 26, 38)
    murk = 0.65 * storm
    top = _lerp(top, (70, 72, 78), murk)
    bottom = _lerp(bottom, (95, 97, 100), murk)

    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp(top, bottom, y / H))

    # sun / moon
    if sun_h > 0:
        sx = int(W * (hour - 6) / 12)
        sy = int(H * (0.85 - 0.7 * sun_h))
        glow = int(30 + 20 * sun_h)
        d.ellipse([sx - glow, sy - glow, sx + glow, sy + glow],
                  fill=_lerp((255, 240, 200), top, 0.3 + murk * 0.6))

    # clouds: count and darkness scale with humidity/storm
    r = _rng("clouds", STATION, t.strftime("%Y-%m-%d %H:%M"))
    n_clouds = int(2 + wx["rh"] / 18 + storm * 6)
    for _ in range(n_clouds):
        cx, cy = r.randint(-40, W + 40), r.randint(int(H * 0.05), int(H * 0.55))
        cw, ch = r.randint(60, 180), r.randint(14, 38)
        shade = _lerp((235, 235, 238), (60, 62, 68), min(1.0, 0.25 + storm))
        d.ellipse([cx, cy, cx + cw, cy + ch], fill=shade)
    img = img.filter(ImageFilter.GaussianBlur(6))

    # rain streaks
    if wx["rain_mm"] > 0:
        d = ImageDraw.Draw(img)
        for _ in range(int(80 * min(1.0, wx["rain_mm"] / 3))):
            x, y = r.randint(0, W), r.randint(0, H)
            d.line([(x, y), (x - 3, y + 12)], fill=(190, 200, 210), width=1)

    # ridge line
    d = ImageDraw.Draw(img)
    pts = [(0, H)] + [
        (x, int(H * 0.78 + 26 * math.sin(x / 71) + 12 * math.sin(x / 23)))
        for x in range(0, W + 1, 8)
    ] + [(W, H)]
    d.polygon(pts, fill=(14, 16, 15) if sun_h < 0 else (28, 34, 30))

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def post_frame(client: httpx.Client, t: datetime) -> None:
    client.post(
        f"{API}/api/v1/stations/{STATION}/frames",
        params={"ts": t.isoformat()},
        headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        files={"frame": (f"{t.strftime('%H%M%S')}.jpg", render(t), "image/jpeg")},
    ).raise_for_status()


def wait_for_station(client: httpx.Client) -> None:
    for _ in range(150):
        try:
            r = client.get(f"{API}/api/v1/stations")
            if r.status_code == 200 and any(
                s["slug"] == STATION for s in r.json()["stations"]
            ):
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit(f"station {STATION} never appeared")


def backfill_yesterday(client: httpx.Client) -> None:
    day = (datetime.now(timezone.utc) + timedelta(hours=5.5)).date() - timedelta(days=1)
    r = client.get(f"{API}/api/v1/stations/{STATION}/timelapses")
    if r.status_code == 200 and any(tl["day"] == day.isoformat() for tl in r.json()["timelapses"]):
        log.info("yesterday already has a timelapse; skipping backfill")
        return
    # daylight in local time 06:00–18:30 → UTC 00:30–13:00
    start = datetime(day.year, day.month, day.day, 0, 30, tzinfo=timezone.utc)
    end = datetime(day.year, day.month, day.day, 13, 0, tzinfo=timezone.utc)
    t, n = start, 0
    while t <= end:
        post_frame(client, t)
        t += timedelta(minutes=3)
        n += 1
    log.info("backfilled %d frames for %s", n, day)


def main() -> None:
    with httpx.Client(timeout=60) as client:
        wait_for_station(client)
        if DO_BACKFILL:
            backfill_yesterday(client)
        log.info("live: one frame every %ss", INTERVAL_S)
        while True:
            try:
                post_frame(client, datetime.now(timezone.utc))
            except httpx.HTTPError as e:
                log.warning("frame post failed: %s", e)
            time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
