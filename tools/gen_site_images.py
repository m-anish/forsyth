#!/usr/bin/env python3
"""Generate forsyth's site imagery with OpenAI, from the station's own CAD renders.

The station's look comes from hardware/enclosures/station: assembly.py renders the
printed kit, and those renders go to the image model as references, so the pictured
station is the one we are building (2020 aluminium mast, white ASA parts, orange vane
and cups, louvred screen and rain gauge on an east-west crossarm, small solar panel
over the core box) rather than a generic stock weather station.

Run with starstucklab's venv (it has openai, Pillow and python-dotenv):

    ../starstucklab/.venv/bin/python tools/gen_site_images.py [--only hero] [--out DIR]

Needs OPENAI_API_KEY in ../starstucklab/.env. Writes <name>.webp (sized for the web)
and <name>.png (the full-size original) to --out, default site/assets (PNGs are only
kept when --out is not site/assets).
"""
import argparse
import base64
import io
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parent.parent
RENDERS = REPO / "hardware" / "enclosures" / "station" / "docs"
OUT = REPO / "site" / "assets"
MODEL = "gpt-image-2"

STATION = (
    "The weather station must match the reference CAD renders closely: a slim "
    "silver aluminium 2020 T-slot extrusion mast about a metre tall. At the top, on a "
    "short side arm, a white 3D-printed cylindrical wind housing with an orange flat "
    "wind-vane tail above it and three small orange conical anemometer cups below it; "
    "a small white sky sensor pod pokes up at the very top of the mast. Halfway down, "
    "a horizontal aluminium crossarm carries a white stacked-plate radiation shield "
    "(five round louvred plates under a conical cap) at one end and a white "
    "cylindrical rain gauge at the other. Below that, a small solar panel about the "
    "size of a postcard on a tilted white bracket, and under it a flat white "
    "rectangular enclosure with round cable connectors along its bottom edge. "
    "All printed parts are matte white plastic with faint layer lines; vane and cups "
    "are a warm orange. It is small, neat and hand-built, not industrial."
)

STYLE = (
    "Muted filmic colour grade, overcast rain-slate blues and grey-greens with a "
    "faint warm brass accent, quiet melancholy, soft diffuse monsoon light, "
    "photographic realism with a storybook stillness. No text, no logos, no "
    "watermarks, no borders, no CAD outlines."
)

IMAGES = {
    # mirror: the prompt puts the station on the left, where the model composes it
    # best; flipped, it stands clear of the headline, which sits bottom-left.
    "hero": dict(
        size="1536x1024", quality="high", max_w=1600, mirror=True,
        refs=["assembly/overview.png", "wind.png"],
        prompt=(
            "Wide cinematic photograph. On the left third of the frame, the small "
            "weather station from the reference images stands on a grassy Himalayan "
            "foothill ridge, its mast clamped to a short weathered wooden post. Further "
            "along the ridge to the right, several metres away in the middle distance "
            "and no taller in frame than the station, an elderly gentleman in a flat "
            "cap and long wool coat stands with his hands clasped behind his back, "
            "seen from behind, calmly watching an "
            "enormous dark monsoon storm front building over the valley below. He is "
            "not worried; he already knew. The vast brooding sky fills the upper half "
            "of the frame, first thin veils of distant rain over the far ridges, the "
            "orange cups catching a little of the last light. Keep the lower edge dark "
            "and calm so text can sit over it. Dim, desaturated, low-key evening light, "
            "nothing bright except a pale band of sky at the horizon. " + STATION + " " + STYLE
        ),
    ),
    "hero-mobile": dict(
        size="1024x1536", quality="high", max_w=900,
        refs=["assembly/overview.png"],
        prompt=(
            "Vertical portrait photograph: the small weather station from the "
            "reference image, its mast clamped to a short weathered wooden post on a "
            "grassy Himalayan ridge, seen from slightly below, an elderly gentleman in "
            "a flat cap and long wool coat standing calmly beside it with his hands "
            "behind his back, both looking toward a towering dark monsoon sky that "
            "fills the upper half of the frame. Distant rain veils over the valley. "
            "Keep the bottom third dark grass so text can sit over it. "
            + STATION + " " + STYLE
        ),
    ),
    "mood": dict(
        size="1536x1024", quality="medium", max_w=1400,
        refs=["assembly/overview.png"],
        prompt=(
            "Quiet, very dark moody landscape for use behind large text: monsoon mist "
            "rolling through a Himalayan valley at dusk, terraced fields dissolving into "
            "cloud, thin rain beginning to fall, one warm lit window in a distant stone "
            "cottage. On a near ridge to one side, small in the frame, the silhouette "
            "of the weather station from the reference image, its round louvred shield "
            "and rain gauge on the crossarm and cups at the top readable as shapes "
            "against the grey sky. Almost abstract, low contrast, lots of empty sky. "
            + STYLE
        ),
    ),
    "unit": dict(
        size="1024x1024", quality="high", max_w=1000,
        refs=["assembly/overview.png", "wind.png", "box-open.png", "assembly/screen-06-cap.png"],
        prompt=(
            "Warm, handmade product photograph on a wooden workbench in a hill "
            "workshop, soft window light, shallow depth of field. The parts of the "
            "weather station from the reference images, before it goes up the mast. "
            "Everything rests on the bench with real contact shadows; nothing floats. "
            "The wind kit (white 3D-printed cylindrical housing about 7 cm across, "
            "orange vane on top, three small orange conical cups 5 cm across hanging "
            "below on short arms) is bolted by the foot at the end of its side arm to "
            "a short upright offcut of silver 2020 aluminium extrusion, which stands "
            "screwed onto a small square wooden block on the bench, so the kit is "
            "held up at that height and its cups hang clear above the bench top. "
            "In front, the fully assembled white radiation shield sits flat on the "
            "bench: five round louvred plates stacked under a conical cap, 14 cm "
            "across and 11 cm tall, clearly twice the diameter of the wind housing "
            "and the biggest round object in the picture. To one side the flat white "
            "core enclosure (19 by 16 cm) lies with its lid off, showing a small green "
            "circuit board, a cylindrical battery cell in a holder and a black "
            "right-angle stub antenna inside; a small solar panel, 10 by 7 cm and "
            "clearly smaller than the enclosure, leans against it. A few hex keys, "
            "M5 screws and a pencil lie around. Matte white plastic with visible "
            "print layer lines. The feel of an instrument made by patient hands. "
            + STYLE
        ),
    ),
}


def generate(client: OpenAI, spec: dict) -> Image.Image:
    refs = [open(RENDERS / r, "rb") for r in spec["refs"]]
    try:
        result = client.images.edit(
            model=MODEL, image=refs, prompt=spec["prompt"],
            size=spec["size"], quality=spec["quality"], n=1,
        )
    finally:
        for f in refs:
            f.close()
    return Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json))).convert("RGB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="generate only these images (repeatable)")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    load_dotenv(REPO.parent / "starstucklab" / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY not set (expected in ../starstucklab/.env)")
    client = OpenAI()
    args.out.mkdir(parents=True, exist_ok=True)
    keep_png = args.out.resolve() != OUT.resolve()

    for name in args.only or IMAGES:
        spec = IMAGES[name]
        print(f"→ {name} ({MODEL}, {spec['size']}, {spec['quality']}) …", flush=True)
        img = generate(client, spec)
        if spec.get("mirror"):
            img = ImageOps.mirror(img)
        if keep_png:
            img.save(args.out / f"{name}.png")
        if img.width > spec["max_w"]:
            img = img.resize(
                (spec["max_w"], int(img.height * spec["max_w"] / img.width)),
                Image.LANCZOS,
            )
        dest = args.out / f"{name}.webp"
        img.save(dest, "WEBP", quality=82)
        print(f"  ✓ {dest} ({dest.stat().st_size // 1024} KB)", flush=True)


if __name__ == "__main__":
    main()
