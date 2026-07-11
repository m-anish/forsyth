"""Engine + idempotent schema application (plus the hourly rollup, which
Timescale insists on creating outside a transaction)."""
import logging
from pathlib import Path

from sqlalchemy import create_engine, text

from .config import settings

log = logging.getLogger("forsyth.db")

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

_CAGG = """
CREATE MATERIALIZED VIEW IF NOT EXISTS readings_hourly
WITH (timescaledb.continuous) AS
SELECT station_id,
       time_bucket('1 hour', ts) AS bucket,
       avg(temp_c)        AS temp_c,
       avg(rh)            AS rh,
       avg(pressure_pa)   AS pressure_pa,
       avg(wind_avg_ms)   AS wind_avg_ms,
       max(wind_gust_ms)  AS wind_gust_ms,
       avg(wind_dir_deg)  AS wind_dir_deg,
       sum(rain_mm)       AS rain_mm,
       avg(pm1)           AS pm1,
       avg(pm25)          AS pm25,
       avg(pm10)          AS pm10,
       avg(batt_v)        AS batt_v,
       avg(rssi_dbm)      AS rssi_dbm
FROM readings
GROUP BY station_id, bucket
WITH NO DATA
"""

_CAGG_POLICY = """
SELECT add_continuous_aggregate_policy('readings_hourly',
    start_offset => NULL,
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE)
"""

# Real-time aggregation: queries transparently union the materialized part with
# recent raw rows, so freshly backfilled data is visible before any policy run.
_CAGG_REALTIME = "ALTER MATERIALIZED VIEW readings_hourly SET (timescaledb.materialized_only = false)"


def _migrate_boards_v1(conn) -> None:
    """boards v1 was keyed by owner with '__default__' for the site board.
    v2 is slug-addressed with visibility. One-way, loses nothing."""
    has_slug = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'boards' AND column_name = 'slug'")).first()
    exists = conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'boards'")).first()
    if not exists or has_slug:
        return
    log.info("migrating boards v1 → v2")
    conn.execute(text("ALTER TABLE boards RENAME TO boards_v1"))
    conn.execute(text("""
        CREATE TABLE boards (
            slug TEXT PRIMARY KEY,
            owner TEXT REFERENCES users(username) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT '',
            is_public BOOLEAN NOT NULL DEFAULT FALSE,
            layout JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"""))
    rows = conn.execute(text("SELECT owner, layout, updated_at FROM boards_v1")).all()
    for owner, layout, updated in rows:
        title = (layout or {}).get("title", "")
        if owner == "__default__":
            conn.execute(text(
                "INSERT INTO boards (slug, owner, title, is_public, layout, updated_at) "
                "VALUES ('default', NULL, :t, TRUE, :l, :u) ON CONFLICT DO NOTHING"),
                {"t": title or "The mesh, at a glance", "l": json_dumps(layout), "u": updated})
        else:
            conn.execute(text(
                "INSERT INTO boards (slug, owner, title, is_public, layout, updated_at) "
                "VALUES (:s, :o, :t, FALSE, :l, :u) ON CONFLICT DO NOTHING"),
                {"s": f"{owner}-board", "o": owner, "t": title or f"{owner}'s board",
                 "l": json_dumps(layout), "u": updated})
    conn.execute(text("DROP TABLE boards_v1"))


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj)


def init_db() -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text()
    # psycopg3 speaks the extended protocol: one statement per execute — and
    # comments must go first, or a ';' inside one splits a statement in half.
    bare = "\n".join(line.split("--", 1)[0] for line in schema.splitlines())
    statements = [s.strip() for s in bare.split(";") if s.strip()]
    with engine.begin() as conn:
        # users table must exist before the boards FK; run migration between
        for stmt in statements:
            if stmt.startswith("CREATE TABLE IF NOT EXISTS boards"):
                _migrate_boards_v1(conn)
            conn.execute(text(stmt))
    # continuous aggregate + policy must run outside a transaction block
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(_CAGG))
        conn.execute(text(_CAGG_POLICY))
        conn.execute(text(_CAGG_REALTIME))
    log.info("schema applied")
