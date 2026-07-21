"""Dummy stations: registers three fictional leaves and feeds them through the
real public API — same path real hardware will use. Backfills history on first
boot (or after a gap), then reports live every SIM_INTERVAL_S."""
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx

from weather import STATIONS, sample

logging.basicConfig(level=logging.INFO, format="%(asctime)s sim %(levelname)s %(message)s")
log = logging.getLogger("sim")

API = os.environ.get("API_BASE", "http://api:8000")
ADMIN_KEY = os.environ["ADMIN_KEY"]
BACKFILL_DAYS = int(os.environ.get("SIM_BACKFILL_DAYS", "7"))
INTERVAL_S = int(os.environ.get("SIM_INTERVAL_S", "60"))
STEP = timedelta(minutes=5)


def wait_for_api(client: httpx.Client) -> None:
    for _ in range(120):
        try:
            if client.get(f"{API}/api/v1/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit("API never came up")


def register(client: httpx.Client) -> dict[str, str]:
    """Create/rekey the dummy stations; returns slug → api key.

    The sim has no persistent key store, so it must re-register on every boot
    to get usable keys — but re-registering must not undo a human. A station
    that already exists keeps ITS name and location (whatever an admin set in
    the console); only genuinely new ones get the fictional defaults."""
    existing = {}
    try:
        r = client.get(f"{API}/api/v1/stations")
        r.raise_for_status()
        existing = {s["slug"]: s for s in r.json()["stations"]}
    except httpx.HTTPError:
        pass   # first boot / API hiccup: fall back to the defaults below

    keys = {}
    for slug, (name, lat, lon, elev, _t, _p) in STATIONS.items():
        cur = existing.get(slug)
        if cur:   # echo back what's already there rather than resetting it
            payload = {"slug": slug, "name": cur["name"], "lat": cur["lat"],
                       "lon": cur["lon"], "elevation_m": cur["elevation_m"],
                       "is_simulated": True}
        else:
            payload = {"slug": slug, "name": name, "lat": lat, "lon": lon,
                       "elevation_m": elev, "is_simulated": True}
        r = client.post(
            f"{API}/api/v1/stations",
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
            json=payload,
        )
        r.raise_for_status()
        keys[slug] = r.json()["api_key"]
        log.info("registered %s%s", slug, "" if cur else " (new)")
    return keys


def last_seen(client: httpx.Client, slug: str) -> datetime | None:
    r = client.get(f"{API}/api/v1/stations/{slug}/latest")
    if r.status_code != 200:
        return None
    return datetime.fromisoformat(r.json()["ts"])


def backfill(client: httpx.Client, slug: str, key: str, now: datetime) -> None:
    start = now - timedelta(days=BACKFILL_DAYS)
    seen = last_seen(client, slug)
    if seen is not None:
        start = max(start, seen + STEP)
    if now - start < STEP:
        log.info("%s: no backfill needed", slug)
        return
    t, batch, total = start, [], 0
    while t < now:
        batch.append({**sample(slug, t), "ts": t.isoformat()})
        t += STEP
        if len(batch) >= 2000:
            _post_batch(client, slug, key, batch); total += len(batch); batch = []
    if batch:
        _post_batch(client, slug, key, batch); total += len(batch)
    log.info("%s: backfilled %d readings from %s", slug, total, start.isoformat())


def _post_batch(client: httpx.Client, slug: str, key: str, batch: list) -> None:
    r = client.post(f"{API}/api/v1/ingest",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"readings": batch}, timeout=120)
    r.raise_for_status()


def main() -> None:
    with httpx.Client(timeout=30) as client:
        wait_for_api(client)
        keys = register(client)
        now = datetime.now(timezone.utc)
        for slug, key in keys.items():
            backfill(client, slug, key, now)

        log.info("live: reporting every %ss", INTERVAL_S)
        while True:
            t = datetime.now(timezone.utc)
            for slug, key in keys.items():
                body = sample(slug, t)
                try:
                    client.post(f"{API}/api/v1/ingest",
                                headers={"Authorization": f"Bearer {key}"}, json=body)
                    if body["lightning"]:
                        log.info("%s: ⚡ ×%d", slug, len(body["lightning"]))
                except httpx.HTTPError as e:
                    log.warning("%s: ingest failed: %s", slug, e)
            time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
