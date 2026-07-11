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


def init_db() -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text()
    # psycopg3 speaks the extended protocol: one statement per execute — and
    # comments must go first, or a ';' inside one splits a statement in half.
    bare = "\n".join(line.split("--", 1)[0] for line in schema.splitlines())
    statements = [s.strip() for s in bare.split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    # continuous aggregate + policy must run outside a transaction block
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(_CAGG))
        conn.execute(text(_CAGG_POLICY))
        conn.execute(text(_CAGG_REALTIME))
    log.info("schema applied")
