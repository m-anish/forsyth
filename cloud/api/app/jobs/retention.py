"""Retention: raw readings beyond RAW_RETENTION_DAYS are dropped (hourly rollup
persists); camera frames beyond FRAME_RETENTION_DAYS are deleted from disk + DB.
Forecasts beyond FORECAST_RETENTION_DAYS (default two years — the forecast-vs-
observed pairs are the asset, so they outlive raw readings) are chunk-dropped.
Timelapses are kept forever — that's the archive."""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from ..config import settings
from ..db import engine

log = logging.getLogger("forsyth.retention")


def run() -> dict:
    now = datetime.now(timezone.utc)
    raw_cutoff = now - timedelta(days=settings.raw_retention_days)
    frame_cutoff = now - timedelta(days=settings.frame_retention_days)
    media = Path(settings.media_root)

    forecast_cutoff = now - timedelta(days=settings.forecast_retention_days)

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        dropped = conn.execute(
            text("SELECT drop_chunks('readings', older_than => :cutoff)"),
            {"cutoff": raw_cutoff},
        ).all()
        fc_dropped = conn.execute(
            text("SELECT drop_chunks('forecasts', older_than => :cutoff)"),
            {"cutoff": forecast_cutoff},
        ).all()

    with engine.begin() as conn:
        old = conn.execute(
            text("SELECT station_id, ts, path FROM camera_frames WHERE ts < :c"),
            {"c": frame_cutoff},
        ).all()
        removed = 0
        for _sid, _ts, rel in old:
            f = media / rel
            if f.exists():
                f.unlink()
                removed += 1
        conn.execute(text("DELETE FROM camera_frames WHERE ts < :c"), {"c": frame_cutoff})
        conn.execute(text("DELETE FROM lightning_events WHERE ts < :c"), {"c": raw_cutoff})

    # sweep now-empty day directories
    frames_root = media / "frames"
    if frames_root.exists():
        for day_dir in frames_root.glob("*/*"):
            if day_dir.is_dir() and not any(day_dir.iterdir()):
                day_dir.rmdir()

    result = {"chunks_dropped": len(dropped), "frames_removed": removed,
              "forecast_chunks_dropped": len(fc_dropped)}
    log.info("retention: %s", result)
    return result
