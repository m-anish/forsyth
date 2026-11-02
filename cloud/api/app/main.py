"""Forsyth cloud API — assembly."""
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# python's mimetypes predates web app manifests; without this the dashboard's
# manifest.webmanifest ships as octet-stream and PWA installs get finicky
mimetypes.add_type("application/manifest+json", ".webmanifest")

from .accounts import router as accounts_router
from .config import settings
from .db import init_db
from .forecast import router as forecast_router
from .ingest import router as ingest_router
from .limits import rate_limit
from .mqtt_bridge import start_bridge
from .query import router as query_router
from .reports import router as reports_router
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
    description=(
        "A scatter of quiet machines that know what the sky is planning.\n\n"
        "The readings are CC BY 4.0 — use them for anything, say where they came "
        "from. Written for people at /api; this page is the generated schema. "
        "Forecast rows are Open-Meteo's model output and carry their terms."
    ),
    version="0.1.0",
    license_info={"name": "CC BY 4.0 (the data)",
                  "url": "https://creativecommons.org/licenses/by/4.0/"},
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


@app.middleware("http")
async def response_headers(request: Request, call_next):
    """Say out loud how long each thing may be reused, and under what licence.

    Starlette's StaticFiles sends an ETag but no Cache-Control, which leaves
    browsers free to *heuristically* cache — typically a tenth of the file's
    age, without revalidating. That is fine for an asset whose URL carries a
    ?v=, and wrong for the documents that reference them: a phone could sit on
    yesterday's station.html, loading yesterday's scripts, while the desktop
    beside it had moved on. So the pages (and the service worker, which decides
    everything else) always revalidate — a cheap 304 when nothing changed —
    while versioned assets are immutable, because a new build is a new URL.
    """
    resp = await call_next(request)
    path = request.url.path
    if path in ("/", "/api") or path.endswith((".html", "/sw.js", ".webmanifest")):
        resp.headers["Cache-Control"] = "no-cache"
    elif request.url.query.startswith("v=") or "&v=" in request.url.query:
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # The licence, where a machine will find it. A CC BY term asking for
    # attribution is worth very little if the only place it is written down is
    # a prose page nobody fetching JSON will ever load, so every API response
    # carries it the standard way (RFC 8288). Not on /forecast, which serves
    # Open-Meteo's model output under Open-Meteo's terms, not ours.
    if path.startswith("/api/v1/") and not path.endswith("/forecast"):
        resp.headers["Link"] = f'<{LICENSE_URL}>; rel="license"'
    return resp


# Order matters and reads backwards: add_middleware INSERTS, so the LAST one
# added is the OUTERMOST. The limiter goes on first precisely so that CORS
# wraps it — otherwise a 429 comes back without CORS headers and a browser
# reports an opaque network failure instead of "you are being rate limited",
# which is the difference between a developer fixing their loop and a
# developer filing a bug against us. Tested, because I got it the wrong way
# round first.
app.middleware("http")(rate_limit)

# Anyone may read this data from anywhere — that is rather the point of a
# weather station on a public hill. GET and HEAD only, so the write surface is
# never reachable cross-origin, and crucially allow_credentials=False: a
# browser will not attach a forsyth session cookie to a request made from
# somebody else's page, so "open to every origin" cannot be turned into
# "acting as a signed-in reader". Authorization is left out of allow_headers
# for the same reason — a station key has no business travelling from a web
# page.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "HEAD"],
    max_age=86400,
)

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(summary_router)
app.include_router(forecast_router)
app.include_router(reports_router)
app.include_router(accounts_router)


@app.post("/api/v1/admin/run/{job}")
def run_job(job: str, request: Request):
    """Manually trigger a worker job (verification & catch-up). Runs inline.
    Auth: ADMIN_KEY bearer or an is_admin session (the admin console)."""
    from .accounts import require_admin
    require_admin(request)
    from .jobs import backup, elevation, forecast, retention, timelapse, wunderground
    jobs = {
        "timelapse": timelapse.run,
        "retention": retention.run,
        "wunderground": wunderground.run,
        "backup": backup.run,
        "elevation": elevation.run,
        "forecast": forecast.run,
    }
    if job not in jobs:
        raise HTTPException(404, f"unknown job; have: {sorted(jobs)}")
    result = jobs[job]()
    return {"ok": True, "job": job, "result": result}


# media (frames, timelapses) then the dashboard at the root — order matters.
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")
_dash = Path(__file__).resolve().parent.parent / "dashboard"


# The homepage IS the board: one layout (the 'default' board), rendered by
# board.html — read-only for visitors, editable for its owners. This route
# serves it at "/" so there is a single homepage implementation, not a
# hand-built page drifting apart from the board it's meant to mirror.
@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(_dash / "board.html")


# The API's own front door, for people rather than for machines. /api/docs is
# the generated schema and tells you every parameter; it does not tell you that
# pressure_pa is not reduced to sea level, or that polling faster than a minute
# only burns your rate budget. Served by an explicit route, like the homepage
# above, so the static mount is not asked to invent a directory for it — and so
# the URL is one anybody can say out loud.
# Both spellings: the static mount swallows "/api/" before Starlette's own
# slash-redirect gets a look at it, so a trailing slash 404s unless it is
# declared. People type the slash.
@app.get("/api", include_in_schema=False)
@app.get("/api/", include_in_schema=False)
def api_page():
    return FileResponse(_dash / "api.html")


app.mount("/", StaticFiles(directory=str(_dash), html=True), name="dashboard")
