"""Nightly pg_dump into the backups volume; keeps the newest 14.
Copying a backup off the VPS is a user-side step (documented in docs/deploy.md)."""
import gzip
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

log = logging.getLogger("forsyth.backup")
BACKUP_DIR = Path("/data/backups")
KEEP = 14


def run() -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    # pg_dump wants a libpq URL; strip SQLAlchemy's driver suffix
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"forsyth-{stamp}.sql.gz"

    dump = subprocess.run(["pg_dump", "--no-owner", url], capture_output=True, check=True)
    with gzip.open(dest, "wb") as f:
        f.write(dump.stdout)

    old = sorted(BACKUP_DIR.glob("forsyth-*.sql.gz"))[:-KEEP]
    for f in old:
        f.unlink()
    result = {"backup": dest.name, "bytes": dest.stat().st_size, "pruned": len(old)}
    log.info("backup: %s", result)
    return result
