-- Forsyth cloud schema. Applied idempotently at API startup (app/db.py).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS stations (
    id            SERIAL PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    lat           DOUBLE PRECISION,
    lon           DOUBLE PRECISION,
    elevation_m   REAL,
    api_key_hash  TEXT NOT NULL,
    is_simulated  BOOLEAN NOT NULL DEFAULT FALSE,
    -- bitmask mirroring hardware/architecture.md §7 (informational; columns are nullable anyway)
    sensors       INTEGER NOT NULL DEFAULT 0,
    wu_station_id TEXT,
    wu_station_key TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS readings (
    station_id   INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL,
    temp_c       REAL,
    rh           REAL,
    pressure_pa  REAL,
    wind_avg_ms  REAL,
    wind_gust_ms REAL,
    wind_dir_deg REAL,
    rain_mm      REAL,          -- accumulation since previous report
    pm1          REAL,
    pm25         REAL,
    pm10         REAL,
    batt_v       REAL,
    solar_state  TEXT,          -- charging | float | discharging
    rssi_dbm     REAL,
    PRIMARY KEY (station_id, ts)
);
SELECT create_hypertable('readings', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS lightning_events (
    station_id  INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    ts          TIMESTAMPTZ NOT NULL,
    distance_km REAL,
    energy      REAL,
    count       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (station_id, ts)
);

CREATE TABLE IF NOT EXISTS camera_frames (
    station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    ts         TIMESTAMPTZ NOT NULL,
    path       TEXT NOT NULL,   -- relative to MEDIA_ROOT
    PRIMARY KEY (station_id, ts)
);

-- Model forecasts pulled from open-meteo (jobs/forecast.py), every run kept.
-- Columns deliberately mirror readings' names: verification and (future) bias
-- correction join on (station_id, valid_at = readings_hourly.bucket).
-- Lead time is derivable: valid_at - run_at. precip_mm covers the hour ENDING
-- at valid_at (open-meteo convention); temp/wind/pressure are instantaneous.
CREATE TABLE IF NOT EXISTS forecasts (
    station_id       INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    model            TEXT NOT NULL,        -- best_match | ecmwf_ifs025 | gfs_seamless | icon_seamless | ens_gefs
    run_at           TIMESTAMPTZ NOT NULL, -- fetch-cycle bucket (3 h); not the model's own init time
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_at         TIMESTAMPTZ NOT NULL,
    temp_c           REAL,
    rh               REAL,
    pressure_pa      REAL,
    wind_avg_ms      REAL,
    wind_gust_ms     REAL,
    wind_dir_deg     REAL,
    precip_mm        REAL,
    precip_prob      REAL,                 -- %, best_match only
    cloud_cover_pct  REAL,
    temp_spread_c    REAL,                 -- ensemble stdev (ens_gefs rows only)
    precip_spread_mm REAL,
    PRIMARY KEY (station_id, model, run_at, valid_at)
);
SELECT create_hypertable('forecasts', 'valid_at', if_not_exists => TRUE);

-- Human weather reports (app/reports.py). Anonymous-first; client_hash is an
-- HMAC of ip|user-agent (rate limiting without PII). qc_* is the inline
-- cross-check against the nearest fresh station. Plain table: tens of rows a
-- day even in optimistic futures.
CREATE TABLE IF NOT EXISTS obs_reports (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    kind        TEXT NOT NULL,      -- precip | hail | fog | snow_line | wind_damage | road_blocked | flood
    intensity   SMALLINT,           -- 1 light · 2 moderate · 3 heavy (NULL = unsaid)
    note        TEXT,
    reporter    TEXT,               -- username when signed in, else NULL
    client_hash TEXT NOT NULL,
    qc_flag     TEXT,               -- corroborated | contradicted | no_station | NULL
    qc_station  INTEGER REFERENCES stations(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS obs_reports_ts_idx ON obs_reports (ts DESC);
CREATE INDEX IF NOT EXISTS obs_reports_hash_idx ON obs_reports (client_hash, ts DESC);

CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    username   TEXT UNIQUE NOT NULL,
    pw_hash    TEXT NOT NULL,           -- scrypt: salthex$hashhex
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- self-serve + OAuth identities (accounts.py). OAuth users have no password:
-- pw_hash NULL means "sign in with the provider, not a password".
ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_sub TEXT;
ALTER TABLE users ALTER COLUMN pw_hash DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_oauth_idx ON users (oauth_provider, oauth_sub)
    WHERE oauth_provider IS NOT NULL;

-- boards v2: many per user, slug-addressed, public/private.
-- The site homepage board is the special slug 'default' (owner NULL, admin-managed).
CREATE TABLE IF NOT EXISTS boards (
    slug       TEXT PRIMARY KEY,
    owner      TEXT REFERENCES users(username) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT '',
    is_public  BOOLEAN NOT NULL DEFAULT FALSE,
    layout     JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS timelapses (
    station_id  INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    path        TEXT NOT NULL,
    frame_count INTEGER NOT NULL,
    duration_s  REAL NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, day)
);
