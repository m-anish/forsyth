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

CREATE TABLE IF NOT EXISTS timelapses (
    station_id  INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    path        TEXT NOT NULL,
    frame_count INTEGER NOT NULL,
    duration_s  REAL NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, day)
);
