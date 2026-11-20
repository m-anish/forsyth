"""Regenerate every printed part of the station from params.py.

    ./build.sh            (or: freecadcmd build.py, run from this directory)

Writes, under out/:
    step/<part>.step     exact geometry, for other CAD tools
    print/<part>.3mf     meshes already lying in their print orientation
    station.FCStd        every part in place on a mock 2020 frame
    report.md            sizes, masses, printability checks and the hardware list

The build refuses to run if params.validate() finds a combination that cannot
work, and it fails if any part comes out as anything but one valid solid that
fits the printer.
"""
import json
import math
import os
import sys
import time

HERE = os.environ.get("STATION_DIR") or os.getcwd()
sys.path.insert(0, HERE)

import FreeCAD as App  # noqa: E402
import Mesh  # noqa: E402
import MeshPart  # noqa: E402
import Part  # noqa: E402

import params as P  # noqa: E402

# What-if runs: STATION_SET="name=value,name=value" overrides params.py for one build;
# STATION_CHECK=1 runs every check but writes no files.
_over = {}
for _kv in filter(None, os.environ.get("STATION_SET", "").split(",")):
    _k, _v = _kv.split("=")
    _over[_k.strip()] = float(_v)
if _over:
    P.apply(**_over)
CHECK_ONLY = bool(os.environ.get("STATION_CHECK"))
from lib import *  # noqa: E402,F401,F403
import wind  # noqa: E402
import rain  # noqa: E402
import screen  # noqa: E402
import enclosure  # noqa: E402
import sky  # noqa: E402

ASA_DENSITY = 1.07       # g/cm3
TPU_DENSITY = 1.21
OVERHANG_COS = math.cos(math.radians(45.0)) + 0.02   # facets steeper than 45 deg pass
CLASH_MM3 = 0.5          # two placed parts sharing more volume than this is an error
QTY = {}  # filled in main(), after any overrides
COLORS = {
    "wind": (0.92, 0.92, 0.90), "vane": (0.85, 0.33, 0.15), "cup": (0.85, 0.33, 0.15),
    "rain": (0.90, 0.90, 0.88), "screen": (0.96, 0.96, 0.94), "enclosure": (0.80, 0.82, 0.80),
    "solar": (0.80, 0.82, 0.80), "frame": (0.62, 0.64, 0.68), "ref": (0.15, 0.45, 0.25),
}


# Filament colour per printed part, for the print tracker: the moving wind parts
# (vane and cups, orange in COLORS) are the second ASA colour, any tone; every
# other ASA part is white; TPU seals have one colour of their own. Plates never
# mix colours, so this must match what goes on the spool holder.
ACCENT_PREFIXES = ("vane_", "cup_")


def print_color(name):
    if name.startswith("tpu_"):
        return "tpu"
    return "accent" if name.startswith(ACCENT_PREFIXES) else "white"


def log(msg):
    print(msg)
    sys.stdout.flush()


def mesh_of(shape):
    return MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.01,
                                  AngularDeflection=math.radians(2.0), Relative=False)


def overhang_report(mesh):
    """Area (mm2) of down-facing surface shallower than 45 deg and not on the bed,
    and the same figure ignoring short spans that print as bridges."""
    total = 0.0
    by_z = {}
    for f in mesh.Facets:
        n = f.Normal
        if n.z < -OVERHANG_COS:
            zs = [p[2] for p in f.Points]
            if min(zs) > 0.25:
                total += f.Area
                k = round(min(zs), 0)
                by_z[k] = by_z.get(k, 0.0) + f.Area
    worst = sorted(by_z.items(), key=lambda kv: -kv[1])[:3]
    return total, worst


def steady_zip(path):
    """Rewrite a 3MF (a zip) with fixed timestamps and entry order, so the same mesh
    always gives the same bytes: the print tracker hashes these files to tell whether a
    part changed, and git sees no change either."""
    import zipfile
    with zipfile.ZipFile(path) as z:
        entries = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, data in sorted(entries):
            info = zipfile.ZipInfo(fn, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


def fits_bed(bb):
    bx, by = P.bed_x - 2 * P.bed_margin, P.bed_y - 2 * P.bed_margin
    lo, hi = sorted((bb.XLength, bb.YLength))
    if bb.ZLength > P.bed_z - P.bed_margin:
        return False, "too tall"
    if hi <= bx and lo <= by:
        return True, "flat"
    # long thin parts go corner to corner
    if (hi + lo) / math.sqrt(2.0) <= min(bx, by):
        return True, "diagonal"
    return False, "too big"


def frame_assembly(parts):
    """Everything in place on a mast + crossarm, for a look at the whole station."""
    Lm = P.mast_len
    za = Lm - P.arm_drop
    items = [("frame_mast", box(-10, 10, -10, 10, 0, Lm)),
             # crossarm on the mast's north face (+X), running east-west (along Y)
             ("frame_crossarm", box(10, 30, -P.arm_len / 2, P.arm_len / 2, za - 20, za))]

    def add(group, dx, dy, dz, turn=None):
        for name, s in group:
            if turn:
                s = turn(s)
            items.append((name, mv(s, dx, dy, dz)))

    # wind kit: foot plate on the mast's -X face, plate top level with the mast top
    kit = wind.place(parts) + [("ref_" + n, s) for n, s in wind.reference()]
    add(kit, -10 - P.wind_arm_len, 0, Lm - P.wind_body_h - P.wind_gasket_t)
    # sky pod on the opposite mast face, standing above everything else
    pod = sky.place(parts) + [("ref_" + n, s) for n, s in sky.reference()]
    add(pod, 10, 0, Lm)
    # Rain gauge on the east end of the crossarm (-Y), screen on the west end (+Y). The crossarm
    # runs east-west on the north face so that neither stands between the midday sun and the
    # solar panel on the south face: on a north-south arm the screen shaded the panel from late
    # February to October (shade study, 2026-11-19, at 32 N). Each keeps its old angle to the arm.
    add(rain.place(parts), 20, -(P.arm_len / 2 - 62), za, lambda s: rz(s, 45 - 90))
    scr = screen.place(parts) + [("ref_" + n, s) for n, s in screen.reference()]
    add(scr, 20, P.arm_len / 2 - 66, za, lambda s: rz(s, -90))
    # Box and solar bracket on the same face as the wind arm (-X). With the sky pod's
    # face turned north, that face looks south: sun on the panel, panel shading the box.
    up = lambda s: rz(rx(s, 90), -90)   # part frame -> world: Y becomes up, depth runs along -X
    enc = enclosure.place(parts) + [("ref_" + n, s) for n, s in enclosure.reference()]
    ez = Lm - P.enc_drop - P.enc_in_h / 2
    add(enc, -10, P.enc_tab_x, ez, up)
    sol = [("solar_bracket", parts["solar_bracket"])] + \
          [("ref_" + n, s) for n, s in enclosure.solar_reference()]
    y_lo = -(P.solar_foot_pitch + P.m5_head_d / 2 + 3.0)
    sz = ez + P.enc_in_h + P.enc_wall + P.enc_tab_len + 6.0 - y_lo
    add(sol, -10, 0, sz, up)
    return items


def hardware():
    """Bought-in parts the printed parts were sized for: (item, qty, where)."""
    # screen: head seat to the far side of the nut that sits in the base
    scr = P.scr_base_t + P.scr_plates * P.scr_pitch + 3.0 + (P.scr_nut_h - P.scr_nut_pocket)
    scr = int(math.ceil(round(scr, 1) / 5.0) * 5)
    axle = 2 * (P.rain_bucket_w / 2 + P.rain_side_gap + P.rain_upright_t) + 8.0
    axle = int(math.ceil(axle / 5.0) * 5)
    n_ports = len(P.enc_ports)
    return [
        ("Ball bearing %gx%gx%g, shielded" % (P.brg_id, P.brg_od, P.brg_w), 4,
         "wind: two per rotor"),
        ("M5 x %d socket-head cap screw, stainless, part-threaded" % P.shaft_len, 2,
         "wind: the two rotor shafts"),
        ("M5 hex nut, stainless", 2 + int((25 - P.vane_boom) // P.m5_nut_h),
         "one trapped in each rotor hub; up to %d on the vane ballast screw (all that fit under "
         "the spine)" % int((25 - P.vane_boom) // P.m5_nut_h)),
        ("M5 x 25 screw, stainless", 1,
         "vane nose ballast: add nuts until the rotor balances (10 to 15 g in all)"),
        ("Disc magnet %gx%g" % (P.mag_d, P.mag_t), P.vane_mag_n + P.anemo_mag_n,
         "vane %d, cups %d" % (P.vane_mag_n, P.anemo_mag_n)),
        ("Disc magnet %gx%g" % (P.rain_mag_d, P.rain_mag_t), 2,
         "rain bucket: one working, one counterweight"),
        ("Reed switch, %g mm glass" % (P.reed_l - 0.5), 2, "anemometer 1, rain 1"),
        ("M3 heat-set insert, about %g mm long" % P.m3_insert_l, 3 + 6 + 3 + 2,
         "wind housing 3, box rim 6, board standoffs 3, screen cap (lightning module) 2"),
        ("M3 x 8 screw, stainless", 3 + 6 + 3 + 2,
         "into inserts: wind lid 3, box lid 6, Board A 3; sky pod head 2 (self-tapping)"),
        ("M3 x 10 screw, stainless", 3, "cup hub cap, self-tapping into plastic"),
        ("M3 x 6 screw, stainless", 3 + 2,
         "rain funnel to base 3 (self-tapping); lightning module to the cap inserts 2"),
        ("M3 x 16 screw, stainless", 2, "rain bucket stops: the heads are the stops"),
        ("M3 x %d screw + nyloc nut (or 3 mm rod)" % axle, 1, "rain bucket axle"),
        ("M4 x %d socket-head screw + M4 nut" % scr, 3, "clamps the screen stack (nut trapped in the base)"),
        ("M5 washer", 12, "one under each foot and tab screw head, to spread the load on ASA"),
        ("M5 x 12 button head + 2020 T-nut", 2 + 2 + 2,
         "6 mm feet: wind kit, sky pod, solar bracket (each foot has 4 holes; use an opposite pair)"),
        ("M5 x 10 button head + 2020 T-nut", 2, "box tabs, %g mm thick" % P.enc_tab_t),
        ("M5 x 8 button head + 2020 T-nut", 2 + 2, "3 mm bases: rain gauge, screen"),
        ("PG7 cable gland", 1, "wind housing"),
        ("GX16-5 socket + plug", 1, "WIND"),
        ("GX16-8 socket + plug", 1, "ENV: screen cable to Board A J4 + J5"),
        ("GX12-3 socket + plug", 1, "RAIN"),
        ("GX12-2 socket + plug", 1, "SOLAR"),
        ("GX12-4 socket + plug", 1, "SKY, to Board A's Qwiic port"),
    ]


def main():
    t0 = time.time()
    problems = P.validate()
    if problems:
        log("PARAMETER CHECK FAILED - nothing was built:")
        for p in problems:
            log("  - " + p)
        return 2

    out = os.path.join(HERE, "out")
    for sub in ("step", "print"):
        os.makedirs(os.path.join(out, sub), exist_ok=True)

    QTY.update({"tpu_washer_gland": 1, "tpu_washer_gx12": 3, "tpu_washer_gx16": 2,
                "wind_spacer": 2, "wind_shim": 2, "cup_arm": int(P.n_cups), "screen_plate": int(P.scr_plates)})
    parts = {}
    for mod in (wind, rain, screen, enclosure, sky):
        log("building %s ..." % mod.__name__)
        parts.update(mod.parts())

    rows, failed = [], []
    for name in sorted(parts):
        s = parts[name]
        bb = bbox(s)
        notes = []
        if not s.isValid():
            notes.append("INVALID SHAPE")
        if len(s.Solids) != 1:
            notes.append("%d solids" % len(s.Solids))
        if abs(bb.ZMin) > 0.02:
            notes.append("not on bed (zmin %.2f)" % bb.ZMin)
        ok, how = fits_bed(bb)
        if not ok:
            notes.append(how)
        m = mesh_of(s)
        if not m.isSolid():
            notes.append("mesh not watertight")
        oh, worst = overhang_report(m)
        ext = "3mf"
        if not CHECK_ONLY:
            s.exportStep(os.path.join(out, "step", name + ".step"))
            try:
                m.write(os.path.join(out, "print", name + ".3mf"))
                steady_zip(os.path.join(out, "print", name + ".3mf"))
            except Exception:
                ext = "stl"
                m.write(os.path.join(out, "print", name + ".stl"))
        if notes:
            failed.append((name, notes))
        rows.append((name, QTY.get(name, 1), bb.XLength, bb.YLength, bb.ZLength,
                     s.Volume / 1000.0, how, oh, worst, notes, ext))
        log("  %-16s %6.1f x %6.1f x %6.1f  %6.1f cm3  overhang %7.1f mm2  %s"
            % (name, bb.XLength, bb.YLength, bb.ZLength, s.Volume / 1000.0, oh,
               "; ".join(notes) or "ok"))

    # parts list for the print tracker (printshop MCP server): one entry per
    # printed part, with how many one station needs and what it is printed in
    if not CHECK_ONLY:
        manifest = {"project": "forsyth-station",
                    "note": "generated by build.py; quantities are per station",
                    "parts": [{"name": name, "file": "print/%s.%s" % (name, ext), "qty": q,
                               "material": "TPU" if name.startswith("tpu_") else "ASA",
                               "color": print_color(name)}
                              for name, q, _x, _y, _z, _v, _how, _oh, _w, _n, ext in rows]}
        with open(os.path.join(out, "parts.json"), "w") as f:
            json.dump(manifest, f, indent=1)

    # vane balance: how much ballast the nose slot needs
    vr = wind.vane_rotor_use()
    cg = vr.CenterOfGravity
    mass = vr.Volume / 1000.0 * ASA_DENSITY
    slot_x = P.vane_nose - 17.0
    ballast = mass * cg.x / slot_x if cg.x > 0 else 0.0

    # assembly document, and a clash check between everything in it
    doc = App.newDocument("station")
    placed = frame_assembly(parts)
    for name, s in placed:
        o = doc.addObject("Part::Feature", name)
        o.Shape = s
    # fits no single part shows: nuts into their hubs, the gland's locknut onto its seat
    fits = wind.fit_checks(parts)
    for what, v in fits:
        if v > CLASH_MM3:
            failed.append(("fit", ["%s: %.1f mm3 in the way" % (what, v)]))
            log("  FIT %s: %.1f mm3 in the way" % (what, v))
    clashes = []
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            (na, a), (nb, b) = placed[i], placed[j]
            if not bbox(a).intersect(bbox(b)):
                continue
            if na.startswith("tpu_") or nb.startswith("tpu_"):
                continue          # gaskets are squeezed on purpose
            v = a.common(b).Volume
            if v > CLASH_MM3:
                clashes.append((na, nb, v))
                log("  CLASH %s / %s: %.1f mm3" % (na, nb, v))
    if clashes:
        failed.append(("assembly", ["%s hits %s" % (a, b) for a, b, _ in clashes]))
    doc.recompute()
    if CHECK_ONLY:
        log("check-only run%s: no files written" % (" with " + str(_over) if _over else ""))
        log("vane rotor: %.0f g solid, CG %.1f mm tailward" % (mass, cg.x))
        for name, notes in failed:
            log("  FAILED %s: %s" % (name, "; ".join(notes)))
        return 1 if failed else 0
    doc.saveAs(os.path.join(out, "station.FCStd"))

    with open(os.path.join(out, "report.md"), "w") as f:
        f.write("# Station build report\n\n")
        f.write("Generated by build.py from params.py. Do not edit by hand.\n\n")
        f.write("## Printed parts\n\n")
        f.write("Sizes are in print orientation (the meshes in `print/` are already "
                "turned that way). Mass assumes solid ASA; expect roughly half with "
                "3 walls and 15-20 % infill.\n\n")
        f.write("| Part | Material | Qty | X | Y | Z | Volume cm3 | Solid mass g | Bed | "
                "Overhang mm2 | Checks |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
        for name, q, x, y, z, vol, how, oh, worst, notes, ext in rows:
            tpu = name.startswith("tpu_")
            f.write("| %s | %s | %d | %.1f | %.1f | %.1f | %.1f | %.1f | %s | %.0f | %s |\n"
                    % (name, "TPU" if tpu else "ASA", q, x, y, z, vol,
                       vol * (TPU_DENSITY if tpu else ASA_DENSITY), how, oh,
                       "; ".join(notes) or "ok"))
        f.write("\nOverhang = down-facing surface shallower than 45 degrees that is not "
                "on the bed. Where it is not zero, the biggest contributors are:\n\n")
        for name, q, x, y, z, vol, how, oh, worst, notes, ext in rows:
            if oh > 1.0:
                f.write("- %s: %s\n" % (name, ", ".join("%.0f mm2 at z=%.0f" % (a, zz)
                                                        for zz, a in worst)))
        f.write("\n## Derived numbers\n\n")
        f.write("- Rain collector area: %.1f cm2, so 1 mm of rain is %.2f ml\n"
                % (P.rain_area_cm2, P.rain_area_cm2 / 10.0))
        f.write("- Screen: %d louvres + cap, %.0f mm tall, %.0f mm diameter\n"
                % (P.scr_plates, screen.height(), 2 * P.scr_r_out))
        f.write("- Box inside: %.1f x %.1f x %.1f mm\n" % (P.enc_in_w, P.enc_in_h, P.enc_in_d))
        f.write("- Cup rotor sweep radius: %.0f mm; rotor axis to 2020 face: %.0f mm\n"
                % (P.cup_sweep_r, P.wind_arm_len))
        f.write("- Vane rotor: %.0f g solid, centre of gravity %.1f mm toward the tail; "
                "about %.0f g of ballast in the nose slot balances it\n"
                % (mass, cg.x, ballast))
        f.write("- Magnet-to-reed distances (centre to centre): vane %.1f mm through the lid; "
                "anemometer %.1f mm through the floor; rain %.1f mm passing, %.1f mm at rest\n"
                % (P.rotor_gap + P.wind_lid_t + P.pcb_standoff + P.vane_pcb_t / 2 + P.mag_d / 2,
                   P.lip_h + P.wind_floor + 0.4 + P.reed_d / 2 + P.mag_d / 2,
                   P.rain_reed_gap, math.hypot(P.rain_reed_gap, P.rain_mag_travel)))
        if P.spacer_wall < 0.8:
            f.write("- NOTE: with this bearing the spacer and shim walls are only %.2f mm. "
                    "They print as a single pass; cut them from %.1f mm OD metal tube "
                    "if they crush when the shaft screw is tightened\n"
                    % (P.spacer_wall, P.race_od))
        f.write("- Sky pod: opening %.0f mm above the mast top, its lowest rim %.0f mm above the "
                "top of the vane; vane tail passes %.0f mm from the pod; view cone +/-%.0f deg, "
                "tilted %.0f deg\n"
                % (P.sky_rise, P.sky_rim_low - (P.wind_lid_t + P.wind_gasket_t + P.vane_top),
                   P.sky_head_xmin - P.vane_tip_x, P.sky_snout_half, P.sky_tilt))
        f.write("- Antenna (inside the box, whip up): %.0f mm clear of the cell, %.0f mm from the "
                "nearest face of the mast\n" % (P.enc_ant_to_cell, P.enc_ant_to_mast))
        f.write("- Fit checks: %s\n" % "; ".join("%s %s" % (w, "ok" if v <= CLASH_MM3 else
                                                                 "BLOCKED (%.1f mm3)" % v) for w, v in fits))
        f.write("- Assembly clash check: %s\n"
                % ("none" if not clashes else "; ".join("%s / %s" % (a, b) for a, b, _ in clashes)))
        f.write("\n## Hardware\n\n| Item | Qty | Where |\n|---|---|---|\n")
        for item, q, where in hardware():
            f.write("| %s | %d | %s |\n" % (item, q, where))

    log("vane rotor: %.0f g solid, CG %.1f mm tailward, ballast ~%.0f g" % (mass, cg.x, ballast))
    log("done in %.0f s -> %s" % (time.time() - t0, out))
    if failed:
        log("FAILED CHECKS:")
        for name, notes in failed:
            log("  %s: %s" % (name, "; ".join(notes)))
        return 1
    return 0


rc = main()
if rc:
    # freecadcmd swallows sys.exit codes on some builds; leave a marker as well
    open(os.path.join(HERE, "out", "BUILD_FAILED") if os.path.isdir(os.path.join(HERE, "out"))
         else os.path.join(HERE, "BUILD_FAILED"), "w").write(str(rc))
else:
    marker = os.path.join(HERE, "out", "BUILD_FAILED")
    if os.path.exists(marker):
        os.remove(marker)
