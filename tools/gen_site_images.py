#!/usr/bin/env python3
"""Generate forsyth's site imagery through the shared starstucklab media pipeline.

Reuses ../starstucklab/tools/lib/ai.py (AIClient → gpt-image-1) rather than
inventing a new pipeline — per the project brief. Run with starstucklab's venv:

    ../starstucklab/.venv/bin/python tools/gen_site_images.py [--only hero]

Requires OPENAI_API_KEY in ../starstucklab/.env (loaded by the lib itself).
Output: site/assets/*.webp, sized for the web.
"""
import argparse
import base64
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STARSTUCKLAB_TOOLS = REPO.parent / "starstucklab" / "tools"
sys.path.insert(0, str(STARSTUCKLAB_TOOLS))

from lib.ai import AIClient  # noqa: E402
from PIL import Image  # noqa: E402

OUT = REPO / "site" / "assets"

STYLE = (
    "Muted filmic color grade, overcast rain-slate blues and grey-greens with a "
    "faint warm brass accent, quiet melancholy, soft diffuse monsoon light, "
    "photographic realism with a storybook stillness. No text, no logos, no "
    "watermarks, no borders."
)

IMAGES = {
    "hero": dict(
        size="1536x1024", quality="high", max_w=1600,
        prompt=(
            "Wide cinematic shot: a lone small weather station on a weathered "
            "wooden mast — tiny anemometer cups, a wind vane, a small solar panel, "
            "a hand-sized grey instrument box — standing on a grassy Himalayan "
            "foothill ridge. Beside it, a little apart, an elderly gentleman in a "
            "flat cap and long wool coat stands with his hands clasped behind his "
            "back, calmly watching an enormous dark monsoon storm front building "
            "over the valley below. He is not worried. The storm is clearly coming; "
            "he clearly already knew. Vast brooding sky occupying most of the "
            "frame, first thin veils of distant rain. " + STYLE
        ),
    ),
    "hero-mobile": dict(
        size="1024x1536", quality="medium", max_w=900,
        prompt=(
            "Vertical portrait composition: a small weather station on a weathered "
            "wooden mast — anemometer cups, wind vane, small solar panel, small grey "
            "instrument box — on a grassy Himalayan ridge, an elderly gentleman in a "
            "flat cap and long wool coat standing calmly beside it, hands behind his "
            "back, looking up at a towering dark monsoon sky that fills the upper "
            "two-thirds of the frame. Distant rain veils. He already knew. " + STYLE
        ),
    ),
    "mood": dict(
        size="1536x1024", quality="medium", max_w=1400,
        prompt=(
            "Quiet moody landscape: monsoon mist rolling through a Himalayan valley "
            "at dusk, terraced fields dissolving into cloud, a faint silhouette of a "
            "single weather station mast on a far ridge line, thin rain beginning to "
            "fall, one warm lit window in a distant stone cottage. Almost abstract, "
            "very dark, suitable as a background behind large text. " + STYLE
        ),
    ),
    "unit": dict(
        size="1024x1024", quality="medium", max_w=1000,
        prompt=(
            "Product-style photograph, but handmade and warm rather than corporate: "
            "a small hand-built weather station 'leaf' on a workbench — a compact "
            "grey enclosure with a tiny circuit board visible through an open lid, "
            "a small solar panel leaning against it, brass-tipped wind vane and "
            "miniature anemometer cups lying beside it, a LiFePO4 battery cell, a "
            "stub antenna, soft window light, shallow depth of field, wood shavings "
            "and a pencil in the background. The feel of an instrument made by "
            "patient hands in a hill workshop. " + STYLE
        ),
    ),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="generate a single image by name")
    args = ap.parse_args()

    todo = {args.only: IMAGES[args.only]} if args.only else IMAGES
    client = AIClient(provider="openai")
    OUT.mkdir(parents=True, exist_ok=True)

    for name, spec in todo.items():
        print(f"→ {name} ({spec['size']}, {spec['quality']}) …", flush=True)
        result = client.generate_image(
            prompt=spec["prompt"], size=spec["size"], quality=spec["quality"]
        )
        img = Image.open(io.BytesIO(base64.b64decode(result["b64"]))).convert("RGB")
        if img.width > spec["max_w"]:
            img = img.resize(
                (spec["max_w"], int(img.height * spec["max_w"] / img.width)),
                Image.LANCZOS,
            )
        dest = OUT / f"{name}.webp"
        img.save(dest, "WEBP", quality=82)
        print(f"  ✓ {dest.relative_to(REPO)} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
