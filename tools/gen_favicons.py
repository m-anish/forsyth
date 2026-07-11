#!/usr/bin/env python3
"""Rasterize the forsyth mark (wind-vane needle over a horizon) into proper
favicons: favicon.ico (16/32/48) + favicon-32.png + apple-touch-icon (180).
Written into site/ and cloud/dashboard/. Run with any python that has Pillow:

    ../starstucklab/.venv/bin/python tools/gen_favicons.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
BG, RING, NEEDLE, TAIL, HORIZON = (11, 12, 14), (127, 162, 196), (127, 162, 196), (73, 94, 114), (127, 162, 196)


def draw_mark(size: int) -> Image.Image:
    s = 8  # supersample
    W = size * s
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = W / 2, W / 2 * 0.94

    # rounded dark tile
    rad = W * 0.22
    d.rounded_rectangle([W * 0.02, W * 0.02, W * 0.98, W * 0.98], radius=rad, fill=BG + (255,))

    # ring
    lw = max(s, int(W * 0.045))
    d.ellipse([c - r * 0.82, c - r * 0.82, c + r * 0.82, c + r * 0.82],
              outline=RING + (150,), width=lw)

    # needle (N-pointing diamond) + dim tail
    def diamond(angle_deg, length, half_w, color):
        a = math.radians(angle_deg)
        tip = (c + length * math.sin(a), c - length * math.cos(a))
        left = (c + half_w * math.sin(a - math.pi / 2), c - half_w * math.cos(a - math.pi / 2))
        right = (c + half_w * math.sin(a + math.pi / 2), c - half_w * math.cos(a + math.pi / 2))
        d.polygon([tip, left, (c, c), right], fill=color)

    diamond(18, r * 0.72, W * 0.075, NEEDLE + (255,))
    diamond(198, r * 0.55, W * 0.075, TAIL + (255,))

    # horizon tick
    d.line([c - r * 0.5, c + r * 0.52, c + r * 0.5, c + r * 0.52],
           fill=HORIZON + (140,), width=max(s, int(W * 0.035)))

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    for root in (REPO / "site", REPO / "cloud" / "dashboard"):
        assets = root / "assets"
        assets.mkdir(exist_ok=True)
        draw_mark(32).save(assets / "favicon-32.png")
        draw_mark(180).save(assets / "apple-touch-icon.png")
        img = draw_mark(48)
        img.save(root / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
        print(f"✓ {root.relative_to(REPO)}: favicon.ico, assets/favicon-32.png, assets/apple-touch-icon.png")


if __name__ == "__main__":
    main()
