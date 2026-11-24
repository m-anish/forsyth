#!/usr/bin/env python3
"""Cut the hero's wind vane and cups out so the page can animate them.

From each hero photo (site/assets/hero.webp, hero-mobile.webp) this writes:

  <name>-plate.webp   the photo with the vane arm and the three cups painted out
  <name>-vane.webp    the vane (arm and fin), real pixels on transparency
  <name>-hub.webp     the cup hub, so cups passing behind it are hidden
  site/hero-anim.json where everything sits, in each photo's own pixels

/assets/* is served immutable for a year, so every asset URL carries ?v=VERSION.
Bump VERSION (and the ?v= in site/styles.css) whenever these files change.

site/hero-anim.js draws the plate's missing parts back every frame: the vane
sprite yawing a few degrees about its pivot, and the cups as small projected cones
turning round the rotor axis. The coordinates below are read off the generated
images by eye (tools/gen_site_images.py), so regenerating a hero means re-reading
them here.

Pillow only:  ../starstucklab/.venv/bin/python tools/hero_anim.py
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "site" / "assets"
VERSION = 3

# Coordinates are in the generator's pixels (ref_w wide) and scaled to the webp.
HEROES = {
    "desktop": dict(
        src="hero.webp", stem="hero", ref_w=1536,
        vane_box=(1138, 198, 1258, 274),     # everything orange in here is vane...
        vane_keep=(1199, 232, 1232, 264),    # ...except the hub cone under the arm
        pivot=(1215, 227), axis=((1147.5, 236), (1250, 204)),
        cups_box=(1158, 288, 1282, 342),
        hub_rect=(1199, 284, 1231, 327),
        cup_discs=[(1181, 314, 16, 21), (1255, 313, 21, 22)],   # as painted: x, y, rx, ry
        sky_max=120,   # brightest value still counted as sky when filling holes
        cups=dict(cx=1215, cy=312, R=38, r=19.5, h=17, hubR=14, e=-0.12),
    ),
    "mobile": dict(
        src="hero-mobile.webp", stem="hero-mobile", ref_w=1024,
        vane_box=(568, 458, 692, 504),
        vane_keep=(609, 480, 636, 504),
        pivot=(621, 477), axis=((577.5, 475), (685, 467.5)),
        cups_box=(566, 524, 672, 580),
        hub_rect=(603, 522, 637, 563),
        cup_discs=[(587.5, 557.5, 16, 17), (650.5, 555, 14, 17), (627.5, 567.5, 9, 13)],
        sky_max=165,
        cups=dict(cx=619, cy=556, R=31.5, r=15.5, h=14, hubR=15, e=-0.3),
    ),
}


def orange_mask(img: Image.Image) -> Image.Image:
    """255 where a pixel is the vane/cup orange, closed over small highlights."""
    h, s, v = img.convert("HSV").split()
    hue = h.point(lambda x: 255 if (x <= 30 or x >= 245) else 0)
    sat = s.point(lambda x: 255 if x >= 85 else 0)
    val = v.point(lambda x: 255 if x >= 35 else 0)
    m = ImageChops.multiply(ImageChops.multiply(hue, sat), val)
    return m.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))


def box_only(mask: Image.Image, box, minus=None) -> Image.Image:
    keep = Image.new("L", mask.size, 0)
    d = ImageDraw.Draw(keep)
    d.rectangle(box, fill=255)
    if minus:
        d.rectangle(minus, fill=0)
    return ImageChops.multiply(mask, keep)


def fill_holes(img: Image.Image, hole: Image.Image, unknown: Image.Image) -> Image.Image:
    """Diffuse the surroundings into the hole (sky, mostly), then add soft grain.

    `unknown` is the hole plus the orange parts that stay (hub, vane cone): they are
    left out of the diffusion so their colour does not bleed into the sky."""
    out = img.copy()
    for radius in [12] * 20 + [6] * 30 + [3] * 40 + [1.5] * 40:
        out = Image.composite(out.filter(ImageFilter.GaussianBlur(radius)), img, unknown)
    noise = Image.effect_noise(img.size, 3).filter(ImageFilter.GaussianBlur(0.5)).convert("RGB")
    grain = ImageChops.add(out, noise, scale=1.0, offset=-128)
    return Image.composite(grain, img, hole)


def sprite(img: Image.Image, alpha: Image.Image, box) -> Image.Image:
    rgba = img.convert("RGBA")
    rgba.putalpha(alpha.filter(ImageFilter.GaussianBlur(0.6)))
    return rgba.crop(box)


def hexcolor(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def build(name: str, spec: dict) -> dict:
    img = Image.open(ASSETS / spec["src"]).convert("RGB")
    k = img.width / spec["ref_w"]
    S = lambda t: tuple(round(v * k) for v in t)  # noqa: E731

    orange = orange_mask(img)
    vane = box_only(orange, S(spec["vane_box"]), S(spec["vane_keep"]))
    cups = box_only(orange, S(spec["cups_box"]), S(spec["hub_rect"]))
    hub = box_only(orange, S(spec["hub_rect"]))

    discs = Image.new("L", img.size, 0)
    for x, y, rx, ry in spec["cup_discs"]:
        ImageDraw.Draw(discs).ellipse(S((x - rx, y - ry, x + rx, y + ry)), fill=255)
    discs = ImageChops.subtract(discs, box_only(Image.new("L", img.size, 255), S(spec["hub_rect"])))
    cups = ImageChops.lighter(cups, discs)

    grow = ImageFilter.MaxFilter(5)
    hole = ImageChops.lighter(vane.filter(ImageFilter.MaxFilter(9)), cups.filter(grow))
    # anything bright that is not orange (mast, arm, housing) is never painted out
    bright = img.convert("HSV").split()[2].point(lambda x: 255 if x > spec["sky_max"] else 0)
    not_orange = ImageChops.invert(orange.filter(ImageFilter.MaxFilter(5)))
    hole = ImageChops.subtract(hole, ImageChops.multiply(bright, not_orange))
    # never paint over the parts that stay put
    hole = ImageChops.subtract(hole, box_only(Image.new("L", img.size, 255), S(spec["vane_keep"])))
    hole = ImageChops.subtract(hole, hub)
    staying = ImageChops.lighter(hub, box_only(orange, S(spec["vane_keep"]))).filter(ImageFilter.MaxFilter(3))
    # only sky may flow into the hole: the white arm and mast nearby are left out
    near = hole.filter(ImageFilter.MaxFilter(31))
    unknown = ImageChops.lighter(ImageChops.lighter(hole, staying), ImageChops.multiply(near, bright))
    plate = fill_holes(img, hole, unknown)

    vb, hb = S(spec["vane_box"]), S(spec["hub_rect"])
    stem = spec["stem"]
    plate.save(ASSETS / f"{stem}-plate.webp", "WEBP", quality=82)
    sprite(img, vane, vb).save(ASSETS / f"{stem}-vane.webp", "WEBP", lossless=True)
    sprite(img, hub, hb).save(ASSETS / f"{stem}-hub.webp", "WEBP", lossless=True)

    # cup colours from the vane (same plastic, better lit than the painted cups)
    px = [p for p, m in zip(img.get_flattened_data(), vane.get_flattened_data()) if m]
    px.sort(key=lambda p: 0.3 * p[0] + 0.59 * p[1] + 0.11 * p[2])
    base = px[int(0.6 * (len(px) - 1))]   # edges blend into the sky, so derive the rest

    (ax0, ay0), (ax1, ay1) = spec["axis"]
    c = spec["cups"]
    return dict(
        w=img.width, h=img.height,
        plate=f"assets/{stem}-plate.webp?v={VERSION}",
        vane=dict(src=f"assets/{stem}-vane.webp?v={VERSION}", x=vb[0], y=vb[1],
                  pivot=[spec["pivot"][0] * k, spec["pivot"][1] * k],
                  axis=math.atan2(ay1 - ay0, ax1 - ax0)),
        hub=dict(src=f"assets/{stem}-hub.webp?v={VERSION}", x=hb[0], y=hb[1]),
        cups=dict(cx=c["cx"] * k, cy=c["cy"] * k, R=c["R"] * k, r=c["r"] * k,
                  h=c["h"] * k, hubR=c["hubR"] * k, e=c["e"],
                  base=hexcolor(base), light=hexcolor([min(255, v * 1.45) for v in base]),
                  dark=hexcolor([v * 0.45 for v in base])),
    )


def main() -> None:
    out = {name: build(name, spec) for name, spec in HEROES.items()}
    (REPO / "site" / "hero-anim.json").write_text(json.dumps(out, indent=1))
    for name, cfg in out.items():
        print(name, cfg["cups"]["base"], cfg["cups"]["light"], cfg["cups"]["dark"])


if __name__ == "__main__":
    main()
