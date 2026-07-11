# Deploying the Forsyth cloud

*(Choosing where to host + price comparison: see [hosting-options.md](hosting-options.md).)*

One small VPS, one docker-compose file. Everything below assumes Ubuntu 24.04 on a
~$5–6/mo box (Hetzner CX22, DigitalOcean basic droplet in BLR, etc. — 2 GB RAM is
plenty; the whole stack idles under 700 MB).

## 1. Provision

```bash
# as root on the fresh VPS
adduser forsyth && usermod -aG sudo forsyth
# install docker (official convenience script is fine for a single-purpose box)
curl -fsSL https://get.docker.com | sh
usermod -aG docker forsyth
# firewall: ssh, http/s, mqtt
ufw allow OpenSSH && ufw allow 80,443/tcp && ufw allow 1883/tcp && ufw enable

# on a 1 GB box: add swap BEFORE building, or docker compose build will OOM
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 2. DNS (Cloudflare)

Add an `A` record: `live.forsyth` → the VPS IP.

- Simplest: **grey cloud (DNS only)** — Caddy gets a Let's Encrypt cert itself.
- If you want the orange cloud (proxied), set the zone's SSL mode to **Full (strict)**
  so Cloudflare speaks HTTPS to Caddy. Note MQTT (1883) can't ride the proxy; point
  devices at the raw IP or a second grey-cloud name (e.g. `mqtt.forsyth...`).

## 3. Deploy

```bash
# as the forsyth user
git clone https://github.com/m-anish/forsyth.git && cd forsyth/cloud
cp .env.example .env
$EDITOR .env          # strong DB_PASSWORD + ADMIN_KEY; PUBLIC_BASE_URL=https://live.forsyth.starstucklab.com
docker compose --profile sim --profile prod up -d --build
```

Dummy data appears within a couple of minutes (7-day backfill for three fictional
stations, plus yesterday's synthetic sky for the timelapse job). Check:

- `https://live.forsyth.starstucklab.com` — dashboard
- `.../api/docs` — OpenAPI
- `docker compose logs -f simulator api` — heartbeat

## 4. MQTT credentials (for real hardware, later)

```bash
docker compose exec mosquitto mosquitto_passwd -c -b /mosquitto/passwd/passwd forsyth-api  '<pw-for-api>'
docker compose exec mosquitto mosquitto_passwd    -b /mosquitto/passwd/passwd coordinator-01 '<pw-for-device>'
docker compose restart mosquitto
# then set MQTT_APP_USER / MQTT_APP_PASSWORD in .env and: docker compose up -d api
```

Topics: `forsyth/<slug>/reading` (JSON, same fields as HTTP ingest),
`forsyth/<slug>/lightning`, `forsyth/<slug>/availability` (LWT). Home Assistant
discovery is published automatically for every known station.

## 5. Registering a real station

```bash
curl -X POST https://live.forsyth.starstucklab.com/api/v1/stations \
  -H "Authorization: Bearer $ADMIN_KEY" -H 'Content-Type: application/json' \
  -d '{"slug":"rooftop","name":"Rooftop","lat":29.45,"lon":79.61,"elevation_m":1700}'
# → returns {"api_key": "..."} — shown once; put it in the coordinator's config
```

The coordinator then POSTs `/api/v1/ingest` with `Authorization: Bearer <key>`,
or publishes MQTT. Weather Underground: set `wu_station_id`/`wu_station_key` when
creating the station and flip `WU_ENABLED=true` in `.env` — the server uploads
every 5 minutes; the coordinator never talks to WU.

## 6. Retiring the dummy data

```bash
docker compose stop simulator skycam           # or drop --profile sim from up
curl -X DELETE .../api/v1/stations/ridge -H "Authorization: Bearer $ADMIN_KEY"
# repeat for orchard + gate — cascade removes their readings/frames/timelapses
```

## 7. Care and feeding

- **Backups:** nightly `pg_dump` gz into the `backups` volume (newest 14 kept).
  Pull a copy off-box periodically:
  `docker compose cp worker:/data/backups ./offsite/` (or rsync the volume path).
- **Updates:** `git pull && docker compose --profile sim --profile prod up -d --build`.
- **Retention:** raw readings 365 days (hourly rollups kept forever), camera frames
  14 days (daily timelapse mp4s kept forever). Tune via `RAW_RETENTION_DAYS` /
  `FRAME_RETENTION_DAYS` env on api+worker.
- **Manual jobs:** `curl -X POST .../api/v1/admin/run/timelapse -H "Authorization: Bearer $ADMIN_KEY"`
  (also: `retention`, `backup`, `wunderground`).
