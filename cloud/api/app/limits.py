"""Per-client rate limiting for the public API.

The read API is open: no key, no sign-up, no terms. That is deliberate — the
whole point of putting a weather station on a hill is that the readings belong
to whoever wants them, and somebody building their own dashboard should not
have to ask. Open and unlimited are different things, though. One enthusiastic
script in a retry loop is enough to make the site unavailable to everybody
else, and this runs on a 1 GB droplet.

Sizing: a single station page costs 38 API calls on load (measured
2026-11-02) and the refresh loop adds roughly fifteen a minute, so the general
budget has to clear several page loads with room for a shared address — a
village on one NAT is the normal case here, not the exception. 300 a minute
leaves eight page loads for one address while still holding a scraper to five
requests a second. Exports get their own, much smaller budget: a year of CSV
for every station is 105 kB and the better part of a second of database.

Fixed windows, counted in process memory. uvicorn runs a single worker here,
so one dictionary is the whole truth; the day that stops being so, this moves
to Redis and the numbers come with it.
"""
import time

from fastapi import Request
from fastapi.responses import JSONResponse

WINDOW_S = 60
GENERAL_MAX = 300
EXPORT_MAX = 10
EXPORT_PREFIX = "/api/v1/export/"
# Said to whoever hit the wall. The general one points at the cheaper way to
# get what they are probably polling for; the export one cannot, because the
# export IS the cheaper way — so it just says wait.
TOO_MANY = ("Too many requests. The data is open; the droplet is small. "
            "If you want history, one call to /api/v1/export/{slug}.csv beats "
            "polling /series.")
TOO_MANY_EXPORT = ("Too many exports. A full CSV is the expensive one — "
                   "ten a minute, and the window resets shortly.")
_MAX_KEYS = 20_000          # ~1 MB of dict; prune rather than grow unbounded

# key -> (window index, count in that window)
_hits: dict[tuple[str, str], tuple[int, int]] = {}


def client_ip(request: Request) -> str:
    """The address our own proxy saw, not the one the caller claims.

    Caddy APPENDS to X-Forwarded-For, so a client that sends the header itself
    arrives as "1.2.3.4, <real>": the first entry is attacker-controlled and
    the last is the one Caddy wrote. Reading [0] — the obvious way to write
    this — makes a rate limit decorative, because evading it is a request
    header away.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "?"


def _is_ingest(request: Request) -> bool:
    """Hardware is never throttled. A coordinator catching up after a power cut
    posts a burst by design, and a reading dropped there is lost for good —
    unlike a dashboard call, which the next refresh simply makes again."""
    p = request.url.path
    return p == "/api/v1/ingest" or (request.method == "POST" and p.endswith("/frames"))


def _over(key: tuple[str, str], limit: int, now: float) -> int | None:
    """Count this request. Returns seconds to wait, or None if within budget."""
    win = int(now // WINDOW_S)
    start, n = _hits.get(key, (win, 0))
    if start != win:
        start, n = win, 0
    if n >= limit:
        return int((win + 1) * WINDOW_S - now) + 1
    _hits[key] = (start, n + 1)
    return None


def _prune(now: float) -> None:
    win = int(now // WINDOW_S)
    for k in [k for k, (start, _) in _hits.items() if start < win]:
        _hits.pop(k, None)


async def rate_limit(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/v1/") or _is_ingest(request):
        return await call_next(request)

    now = time.time()
    if len(_hits) > _MAX_KEYS:
        _prune(now)

    ip = client_ip(request)
    budgets = [(("gen", ip), GENERAL_MAX, TOO_MANY)]
    if path.startswith(EXPORT_PREFIX):
        budgets.append((("exp", ip), EXPORT_MAX, TOO_MANY_EXPORT))

    for key, limit, said in budgets:
        wait = _over(key, limit, now)
        if wait is not None:
            return JSONResponse(
                {"detail": said},
                status_code=429,
                headers={"Retry-After": str(wait), "Cache-Control": "no-store"},
            )
    return await call_next(request)
