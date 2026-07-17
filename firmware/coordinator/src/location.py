"""location.py — coordinator-side capture of station coordinates.

The cloud `stations` table is the single source of truth; this is a *local*
capture point for the site, chiefly for installs where the phone can't reach the
internet but can reach the coordinator's AP. A location entered on the
`/location` page is saved to flash and pushed to the cloud via
`forsyth/<slug>/meta` (the same validated writer the admin editor uses) the
moment the uplink is up — and then **never re-pushed**. That one-shot rule is
what keeps the two write paths from fighting: a later admin edit stays
authoritative (last deliberate write wins). Elevation is left to the server-side
backfill, so nothing here needs an elevation API.
"""
import json

import config

_FILE = getattr(config, "LOCATION_FILE", "location.json")


class LocationManager:
    def __init__(self, uplink, slugs):
        self._up = uplink
        self._slugs = list(slugs)
        self._store = self._load()

    def _load(self):
        try:
            with open(_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            with open(_FILE, "w") as f:
                json.dump(self._store, f)
        except OSError as e:
            print("location: save failed (%r)" % e)

    # ---- read ----
    def slugs(self):
        return self._slugs

    def get(self, slug):
        return self._store.get(slug)

    def all(self):
        return self._store

    # ---- write ----
    def set(self, slug, lat, lon, elev=None):
        self._store[slug] = {"lat": lat, "lon": lon, "elevation": elev,
                             "synced": False}
        self._save()
        print("location: %s set to %.5f, %.5f (pending sync)" % (slug, lat, lon))
        self.sync_pending()          # try now; deferred cleanly if offline

    def sync_pending(self):
        """Publish any unsynced captures via MQTT meta. Called on capture and
        periodically from the main loop. A no-op when offline or all-synced;
        only marks synced on a real publish, so an offline capture retries."""
        if not self._up.connected:
            return
        for slug, e in self._store.items():
            if e.get("synced"):
                continue
            body = {"lat": e["lat"], "lon": e["lon"]}
            if e.get("elevation") is not None:
                body["elevation_m"] = e["elevation"]
            if self._up.publish("forsyth/%s/meta" % slug, body):
                e["synced"] = True
                self._save()
                print("location: %s synced to cloud" % slug)
