"""Daily timelapse: frames/<slug>/<YYYY-MM-DD>/HHMMSS.jpg → timelapses/<slug>/<date>.mp4.

Encodes every completed day (UTC) that has frames but no timelapse yet. Each frame
gets its capture time stamped into the corner (so the mp4 is self-timestamping),
then ffmpeg assembles at 24 fps.
"""
import logging
import shutil
import subprocess
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import text

from ..config import settings
from ..db import engine

log = logging.getLogger("forsyth.timelapse")
FPS = 24


def _stamp(src: Path, dest: Path, label: str) -> None:
    img = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=max(14, img.height // 24))
    except TypeError:  # older Pillow
        font = ImageFont.load_default()
    pad = img.height // 40
    draw.text((pad + 1, img.height - pad * 4 + 1), label, fill=(0, 0, 0), font=font)
    draw.text((pad, img.height - pad * 4), label, fill=(230, 231, 228), font=font)
    img.save(dest, "JPEG", quality=85)


def _encode_day(slug: str, station_id: int, day: date, frame_paths: list[tuple[datetime, str]]) -> dict:
    media = Path(settings.media_root)
    out_rel = Path("timelapses") / slug / f"{day.isoformat()}.mp4"
    out = media / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        n = 0
        for ts, rel in frame_paths:
            src = media / rel
            if not src.exists():
                continue
            label = f"{slug} · {day.isoformat()} {ts.strftime('%H:%M')} UTC"
            _stamp(src, tmp / f"{n:06d}.jpg", label)
            n += 1
        if n < 2:
            return {"slug": slug, "day": str(day), "skipped": "too few frames"}
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
             "-i", str(tmp / "%06d.jpg"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(out)],
            check=True,
        )

    duration = n / FPS
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO timelapses (station_id, day, path, frame_count, duration_s)
                    VALUES (:sid, :day, :path, :n, :dur)
                    ON CONFLICT (station_id, day) DO UPDATE
                        SET path = EXCLUDED.path, frame_count = EXCLUDED.frame_count,
                            duration_s = EXCLUDED.duration_s, created_at = now()"""),
            {"sid": station_id, "day": day, "path": str(out_rel), "n": n, "dur": duration},
        )
    log.info("timelapse %s/%s: %d frames, %.1fs", slug, day, n, duration)
    return {"slug": slug, "day": str(day), "frames": n, "duration_s": duration}


def run(include_today: bool = False) -> list[dict]:
    """Encode all (station, day) pairs with frames but no timelapse."""
    if shutil.which("ffmpeg") is None:
        log.error("ffmpeg not found")
        return [{"error": "ffmpeg not found"}]
    today = datetime.now(timezone.utc).date()
    sql = text("""
        SELECT s.slug, f.station_id, f.ts::date AS day,
               array_agg(f.ts ORDER BY f.ts) AS tss,
               array_agg(f.path ORDER BY f.ts) AS paths
        FROM camera_frames f JOIN stations s ON s.id = f.station_id
        WHERE NOT EXISTS (SELECT 1 FROM timelapses t
                          WHERE t.station_id = f.station_id AND t.day = f.ts::date)
        GROUP BY s.slug, f.station_id, day
        ORDER BY day
    """)
    with engine.connect() as conn:
        work = conn.execute(sql).all()

    results = []
    for slug, sid, day, tss, paths in work:
        if day >= today and not include_today:
            continue
        try:
            results.append(_encode_day(slug, sid, day, list(zip(tss, paths))))
        except Exception as e:
            log.exception("timelapse failed for %s/%s", slug, day)
            results.append({"slug": slug, "day": str(day), "error": str(e)})
    if not results:
        log.info("timelapse: nothing to do")
    return results
