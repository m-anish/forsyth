"""Scheduled jobs — runs as its own container (`worker` in docker-compose).
Same image and code as the API; different entrypoint."""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .db import init_db
from .jobs import backup, elevation, retention, timelapse, wunderground

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("forsyth.worker")


def main() -> None:
    init_db()  # idempotent; worker may win the boot race against the api
    sched = BlockingScheduler(timezone="UTC")
    # Timelapse just after midnight UTC (server time-of-record is UTC throughout).
    sched.add_job(timelapse.run, CronTrigger(hour=0, minute=20), name="timelapse")
    sched.add_job(backup.run, CronTrigger(hour=2, minute=0), name="backup")
    sched.add_job(retention.run, CronTrigger(hour=3, minute=0), name="retention")
    sched.add_job(wunderground.run, IntervalTrigger(minutes=5), name="wunderground")
    # backfill soon after boot, then hourly — new/edited stations pick up
    # elevation within the hour without hammering the API
    sched.add_job(elevation.run, IntervalTrigger(hours=1),
                  name="elevation", next_run_time=None)
    sched.add_job(elevation.run, "date", name="elevation-boot")
    log.info("worker up; jobs scheduled")
    sched.start()


if __name__ == "__main__":
    main()
