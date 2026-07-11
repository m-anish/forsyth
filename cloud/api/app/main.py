"""Forsyth cloud API — assembly."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from .accounts import router as accounts_router
from .auth import AdminDep
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


@app.post("/api/v1/admin/run/{job}", dependencies=[AdminDep])
def run_job(job: str):
    """Manually trigger a worker job (verification & catch-up). Runs inline."""
    from .jobs import backup, retention, timelapse, wunderground
    jobs = {
        "timelapse": timelapse.run,
        "retention": retention.run,
        "wunderground": wunderground.run,
        "backup": backup.run,
    }
    if job not in jobs:
        raise HTTPException(404, f"unknown job; have: {sorted(jobs)}")
    result = jobs[job]()
    return {"ok": True, "job": job, "result": result}


# media (frames, timelapses) then the dashboard at the root — order matters.
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")
_dash = Path(__file__).resolve().parent.parent / "dashboard"
app.mount("/", StaticFiles(directory=str(_dash), html=True), name="dashboard")
