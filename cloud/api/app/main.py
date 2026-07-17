"""Forsyth cloud API — assembly."""
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

# python's mimetypes predates web app manifests; without this the dashboard's
# manifest.webmanifest ships as octet-stream and PWA installs get finicky
mimetypes.add_type("application/manifest+json", ".webmanifest")

from .accounts import router as accounts_router
from .config import settings
from .db import init_db
from .ingest import router as ingest_router
from .mqtt_bridge import start_bridge
from .query import router as query_router
from .summary import router as summary_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("forsyth.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    stop_bridge = start_bridge()
    yield
    stop_bridge()


app = FastAPI(
    title="forsyth cloud",
    description="A scatter of quiet machines that know what the sky is planning.",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(summary_router)
app.include_router(accounts_router)


@app.post("/api/v1/admin/run/{job}")
def run_job(job: str, request: Request):
    """Manually trigger a worker job (verification & catch-up). Runs inline.
    Auth: ADMIN_KEY bearer or an is_admin session (the admin console)."""
    from .accounts import require_admin
    require_admin(request)
    from .jobs import backup, elevation, retention, timelapse, wunderground
    jobs = {
        "timelapse": timelapse.run,
        "retention": retention.run,
        "wunderground": wunderground.run,
        "backup": backup.run,
        "elevation": elevation.run,
    }
    if job not in jobs:
        raise HTTPException(404, f"unknown job; have: {sorted(jobs)}")
    result = jobs[job]()
    return {"ok": True, "job": job, "result": result}


# media (frames, timelapses) then the dashboard at the root — order matters.
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")
_dash = Path(__file__).resolve().parent.parent / "dashboard"
app.mount("/", StaticFiles(directory=str(_dash), html=True), name="dashboard")
