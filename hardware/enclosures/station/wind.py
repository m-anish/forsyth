"""Wind kit: one housing, vane on top, cups underneath.

Every part is returned in its PRINT orientation (z = 0 on the bed).
place() puts them together in the kit's own frame: rotor axis on Z,
z = 0 at the underside of the housing floor, arm pointing along +X.
"""
import math

import params as P
from lib import *


def _tower_cuts(z0):
    """Two bearing pockets and the bore between them, for a tower starting at z0."""
    od = P.brg_od + P.brg_fit
    return [
        cyl(od, P.brg_w + 0.01, (0, 0, z0 - 0.01)),
        cyl(P.tower_bore, P.tower_h, (0, 0, z0)),
        cyl(od, P.brg_w + 0.02, (0, 0, z0 + P.brg_w + P.brg_sep)),
    ] + bridged_roof(cyl(od, 400, (0, 0, -200)), P.tower_bore, z0 + P.brg_w)   # lower pocket's roof


def _ear_xy():
    return [pol(P.wind_ear_r, a)[:2] for a in P.wind_ear_angles]


# ---------------------------------------------------------------- housing ---
def body():
    h = P.wind_body_h
    L = P.wind_arm_len
    ft = P.wind_foot_t
    fw = P.wind_foot_w / 2
    rw = P.wind_rail_w

    shell = [cyl(2 * P.wind_r_out, h)]
    shell += [cyl(P.wind_ear_d, h, (x, y, 0)) for x, y in _ear_xy()]
    # two rails, one each side, leave the middle of the foot open for a hex key
    for s in (1, -1):
        y0, y1 = sorted((s * (fw - rw), s * fw))
        shell.append(box(0, L - ft, y0, y1, 0, P.wind_rail_h))
        g = h - P.wind_rail_h
        shell.append(prism([(L - ft - g, P.wind_rail_h), (L - ft, P.wind_rail_h), (L - ft, h)],
                           rw, "xz", y0))
    shell.append(box(L - ft, L, -fw, fw, 0, h))
    # flat pad for the cable gland, wide and tall enough for its locknut's seat inside
    gz = P.wind_gland_z
    pw = P.gland_nut_r + 2.0
    pad = box(P.wind_r_out - 2.0, P.wind_r_out + 2.5, -pw, pw, 0, gz + pw)
    shell.append(rz(pad, P.wind_gland_angle))
    s = fuse(shell)

    # the lid sits one gasket thickness above the rim, so the ledge is that much shallower
    rebate = P.vane_pcb_t + P.pcb_standoff - P.wind_gasket_t
    s = cut(s, [
        cyl(2 * P.wind_r_in, h, (0, 0, P.wind_floor)),
        cyl(2 * P.wind_r_pcb, rebate + 0.01, (0, 0, h - rebate)),
    ])

    # bearing tower for the cup rotor rises inside; reed cradle on the floor
    inner = [cyl(P.tower_od, P.tower_h)]
    cw = P.reed_d + 0.3 + 2.4
    r0 = P.anemo_mag_r - P.reed_l / 2
    for a in (r0 + 0.3, r0 + P.reed_l - 4.3):
        inner.append(box(-(a + 4.0), -a, -cw / 2, cw / 2,
                         P.wind_floor - 0.01, P.wind_floor + P.reed_d + 0.4))
    s = fuse([s] + inner)

    cuts = _tower_cuts(0.0)
    # reed channel, open on top
    cuts.append(box(-(P.wind_r_in - 0.5), -(P.tower_od / 2 - 0.5),
                    -(P.reed_d + 0.3) / 2, (P.reed_d + 0.3) / 2,
                    P.wind_floor + 0.4, P.wind_floor + P.reed_d + 2))
    # the channel must not open the tower wall: restore it afterwards (below)
    for x, y in _ear_xy():
        d = P.m3_insert_l + 1.0
        cuts.append(cyl(P.m3_insert_d, d + 0.01, (x, y, h - d)))
    cuts.append(rz(teardrop(P.gland_d, 14, (P.wind_r_in - 4, 0, gz), "x"), P.wind_gland_angle))
    # flat seat for the locknut inside, leaving gland_wall under the flange (the PG7
    # thread is only 8 to 9 mm); its roof slopes at 45 deg so it prints without support
    xs = P.wind_r_out + 2.5 - P.gland_wall
    sr = P.gland_nut_r + 0.5
    d = h + 2.0 - (gz + sr)          # the 45 deg roof runs out past the top: no flat ceiling
    seat = prism([(xs - 14, gz - sr), (xs, gz - sr), (xs, gz + sr), (xs - d, gz + sr + d),
                  (xs - 14, gz + sr + d)], 2 * sr, "xz", -sr)
    cuts.append(rz(seat, P.wind_gland_angle))
    # cable-tie slots through one rail, between the cup sweep and the foot
    x0 = max(P.cup_sweep_r + 6.0, P.wind_r_out + 12.0)
    for x in (x0, (x0 + L - ft - 14.0) / 2 + 4.0):
        if x + 5 < L - ft - (h - P.wind_rail_h):
            cuts.append(box(x, x + 4.5, fw - rw + 2.0, fw - rw + 4.2, -0.5, P.wind_rail_h + 0.5))
    zc = h / 2
    for dy, dz in ((0, P.wind_foot_pv), (0, -P.wind_foot_pv),
                   (P.wind_foot_pitch_h, 0), (-P.wind_foot_pitch_h, 0)):
        cuts.append(cyl(P.m5_clear, ft + 2, (L - ft - 1, dy, zc + dz), (1, 0, 0)))
    # drain / breather, and a drip-break groove round the cup hub
    cuts.append(cyl(2.5, P.wind_floor + 1, pol(P.wind_r_in - 4.5, 240, -0.5)))
    rg = P.cup_flange_r + 2.0
    if rg + 1.5 < P.wind_r_out - 1.0:
        cuts.append(tube(2 * (rg + 1.5), 2 * rg, 1.0, (0, 0, -0.01)))
    s = cut(s, cuts)
    # keep the tower wall whole where the reed channel ran into it
    ring = tube(P.tower_od, P.brg_od + P.brg_fit, P.tower_h)
    return clean(s.fuse(ring))


def lid():
    t = P.wind_lid_t
    parts = [cyl(2 * P.wind_lid_r, t)]
    parts += [cyl(P.wind_ear_d + 2, t, (x, y, 0)) for x, y in _ear_xy()]
    parts.append(cyl(P.tower_od, P.tower_h))
    s = fuse(parts)
    cuts = _tower_cuts(0.0)
    cuts += [cyl(P.m3_clear, t + 1, (x, y, -0.5)) for x, y in _ear_xy()]
    # north index: an engraved arrow pointing along the arm at the mast. The arm hangs off
    # the mast's south face (README, "Which way round"), so the arrow points north.
    r0 = P.vane_flange_r + 3.0
    r1 = P.wind_lid_r - 1.5
    if r1 - r0 > 3:
        cuts.append(prism([(r0, -2.2), (r0, 2.2), (r1, 0)], 0.61, "xy", t - 0.6))
    return cut(s, cuts)


def lid_gasket():
    """TPU gasket between the housing rim and the lid. Print flat, 100 % infill."""
    t = P.wind_gasket_t
    parts = [tube(2 * P.wind_r_out, 2 * (P.wind_r_pcb + 0.2), t)]
    parts += [cyl(P.wind_ear_d, t, (x, y, 0)) for x, y in _ear_xy()]
    s = fuse(parts)
    return cut(s, [cyl(P.m3_clear, t + 1, (x, y, -0.5)) for x, y in _ear_xy()]
               + [cyl(2 * (P.wind_r_pcb + 0.2), t + 1, (0, 0, -0.5))])


def pcb_ring():
    """Loose spacer that holds the vane PCB down against its ledge."""
    return tube(2 * (P.vane_pcb_d / 2 + 0.1), 2 * (P.wind_r_in + 0.2), P.pcb_standoff - 0.1)


def spacer():
    """Sleeve between the two inner races; print two."""
    return tube(P.race_od, P.brg_id + 0.3, P.brg_sep + 0.3)


def shim():
    """Ring under each shaft screw head, so the head bears on the inner race only; print two."""
    return tube(P.race_od, P.brg_id + 0.3, P.shim_h)


# ------------------------------------------------------------- vane rotor ---
def _vane_dims():
    g = P.rotor_gap
    ht = P.tower_h - P.wind_lid_t            # tower top above the roof
    zc = ht + P.lip_h                        # cavity ceiling
    rc = P.tower_od / 2 + 1.5
    rh = P.vane_hub_r
    z_ht = zc + 3.5 + (P.m5_nut_h + 0.4) + 3.0
    cone_h = rh - 1.0
    z_top = P.vane_top
    return g, ht, zc, rc, rh, z_ht, cone_h, z_top


def vane_rotor_use():
    """Vane rotor in the use frame: z = 0 on the roof, tail along +X."""
    g, ht, zc, rc, rh, z_ht, cone_h, z_top = _vane_dims()
    b = P.vane_boom
    rf = P.vane_flange_r
    fl = P.rotor_flange_h

    parts = [cyl(2 * rh, z_ht - g, (0, 0, g)),
             cone(2 * rh, 2.0, cone_h, (0, 0, z_ht))]
    if rf > rh + 0.01:
        parts.append(cyl(2 * rf, fl, (0, 0, g)))
        parts.append(cone(2 * rf, 2 * rh, rf - rh, (0, 0, g + fl)))
    parts.append(box(-rh, rh, -1.5, 1.5, z_ht, z_top - 0.01))               # web
    parts.append(box(-(P.vane_nose - 30), P.vane_tail, -b / 2, b / 2, z_top - b, z_top))
    parts.append(box(P.vane_tail - P.vane_fin_len, P.vane_tail,
                     -P.vane_fin_t / 2, P.vane_fin_t / 2, P.vane_fin_clear, z_top))
    n = P.vane_nose
    nose = [(-(n - 30), -b / 2), (-(n - 26), -7), (-(n - 8), -7), (-n, 0),
            (-(n - 8), 7), (-(n - 26), 7), (-(n - 30), b / 2)]
    parts.append(prism(nose, b, "xy", z_top - b))
    s = fuse(parts)

    s = cut(s, [cyl(2 * rc, zc - g + 0.01, (0, 0, g - 0.01))])
    s = fuse([s, cyl(P.race_od, P.lip_h + 0.01, (0, 0, ht))])

    nz = zc + 3.5
    nh = P.m5_nut_h + 0.4
    af = P.m5_nut_af + 0.3
    ml = P.vane_mag_len
    mw = P.mag_d + 0.2
    cuts = [
        cyl(P.brg_id + 0.3, P.vane_bore_top - ht, (0, 0, ht - 0.01)),         # shaft bore
        rz(hexprism(af, nh, (0, 0, nz)), 30),                                 # flats face the slot walls
        box(-af / 2, af / 2, 0, max(rh, rf) + 1, nz, nz + nh),                # nut slides in from +Y
    ]
    slot_fp = fuse([rz(hexprism(af, 400, (0, 0, -200)), 30), box(-af / 2, af / 2, 0, max(rh, rf) + 1, -200, 200)])
    cuts += bridged_roof(slot_fp, P.brg_id + 0.3, nz, toward=-1, angle=0)
    cuts += [
        box(P.vane_reed_r - ml / 2, P.vane_reed_r + ml / 2, -mw / 2, mw / 2,
            g - 0.01, g + P.mag_d + 0.3),                                     # magnet, axis radial
        obround(P.m5_clear, 12.0, b + 0.02, (-(n - 17), 0, z_top - b - 0.01)),  # ballast slot
    ]
    return cut(s, cuts)


def vane_rotor():
    """Printed upside down: the flat top of the spine and fin sits on the bed."""
    return flip(vane_rotor_use())


def vane_height():
    return _vane_dims()[7]


# -------------------------------------------------------------- cup rotor ---
def _hub_h():
    """Hub length. Long enough for the nut and arm slots, and long enough that
    the tops of the cups pass under the housing floor with cup_floor_gap to spare."""
    return P.cup_hub_h


def cup_hub():
    """Bottom (the end away from the housing) on the bed."""
    H = _hub_h()
    r = P.cup_hub_d / 2
    rf = P.cup_flange_r
    fl = P.rotor_flange_h
    parts = [cyl(2 * r, H)]
    if rf > r + 0.01:
        z_fl = H - fl
        parts.append(cyl(2 * rf, fl, (0, 0, z_fl)))
        z0 = max(0.0, z_fl - (rf - r))
        parts.append(cone(2 * (rf - (z_fl - z0)), 2 * rf, z_fl - z0, (0, 0, z0)))
    parts.append(cyl(P.race_od, P.lip_h, (0, 0, H - 0.01)))
    s = fuse(parts)

    at = P.cup_arm_t + 0.3
    sh = P.cup_arm_h + 0.2
    nh = P.m5_nut_h + 0.4
    nz = H - 3.5 - nh
    af = P.m5_nut_af + 0.3
    ml = P.anemo_mag_len
    mw = P.mag_d + 0.2
    bore = P.shaft_in_hub + 1.5
    cuts = [cyl(P.brg_id + 0.3, bore + 0.02, (0, 0, H + P.lip_h - bore))]
    cuts.append(hexprism(af, nh, (0, 0, nz)))
    cuts.append(box(0, rf + 1, -af / 2, af / 2, nz, nz + nh))                 # nut from +X
    slot_fp = fuse([hexprism(af, 400, (0, 0, -200)), box(0, rf + 1, -af / 2, af / 2, -200, 200)])
    cuts += bridged_roof(slot_fp, P.brg_id + 0.3, nz + nh, toward=1, angle=90)
    cuts.append(box(-(P.anemo_mag_r + ml / 2), -(P.anemo_mag_r - ml / 2), -mw / 2, mw / 2,
                    H - (P.mag_d + 0.3), H + 0.01))                           # magnet at 180 deg
    slot = fuse([box(4.35, rf + 2, -at / 2, at / 2, -0.01, sh),
                 box(4.35, 4.5 + P.cup_key + 0.15, -at / 2, at / 2 + P.cup_key, -0.01, sh)])
    cuts += polar(slot, P.n_cups, 60.0)
    pilot = cyl(P.m3_tap_d, 9.0, (10.0, 0, -0.01))
    cuts += polar(pilot, P.n_cups, 0.0)
    return cut(s, cuts)


def cup_hub_cap():
    s = cyl(P.cup_hub_d, 2.4)
    return cut(s, polar(cyl(P.m3_clear, 3, (10.0, 0, -0.3)), P.n_cups, 0.0))


def cup_arm():
    """One cup with its arm; print three. Cone mouth on the bed, arm along +X."""
    R = P.cup_arm_r
    d = P.cup_d
    wv = P.cup_wall * math.sqrt(2.0)
    outer = cone(d, 3.0, (d - 3.0) / 2)
    di = d - 2 * wv
    inner = cone(di, 0.0, di / 2, (0, 0, -0.001))
    t = P.cup_arm_t
    hh = P.cup_arm_h / 2
    parts = [outer,
             tube(d + 2 * P.cup_rim, di, 1.6),
             box(d / 2 - 10, R - 4.65, -hh, hh, 0, t),
             box(R - 4.5 - P.cup_key, R - 4.65, -hh, hh, 0, t + P.cup_key),
             prism([(d / 2 - 6, t), (d / 2 + 8, t), (d / 2 - 12, t + 7)], 3.0, "xz", -1.5)]
    return cut(fuse(parts), [inner])


# ------------------------------------------------------------- fit checks ---
def fit_checks(p):
    """Fits no single-part check can see: [(what, mm3 of plastic in the way)].
    Anything above about 0.5 mm3 means the part cannot go in. Run by build.py."""
    out = []
    nut = hexprism(P.m5_nut_af, P.m5_nut_h, (0, 0, 0))
    hub = p["cup_hub"]
    nz = P.cup_hub_h - 3.5 - (P.m5_nut_h + 0.4) + 0.2
    out.append(("cup_hub: M5 nut slides into its slot and over the bore",
                max(hub.common(mv(nut, x, 0, nz)).Volume for x in (0, 2, 4, 7, 10, 14, 18, 22))))
    vane = vane_rotor_use()
    zc = _vane_dims()[2]
    nv = rz(nut, 30)
    out.append(("vane_rotor: M5 nut slides into its slot and over the bore",
                max(vane.common(mv(nv, 0, y, zc + 3.7)).Volume for y in (0, 2, 4, 7, 10, 14, 18, 22))))
    body = p["wind_body"]
    xs = P.wind_r_out + 2.5 - P.gland_wall
    worst = 0.0
    for rot in (0, 30):
        ln = cut(rz(hexprism(P.gland_nut_af, 4.0, (0, 0, 0)), rot), [cyl(P.gland_d, 6, (0, 0, -1))])
        ln = rz(mv(ry(ln, 90), xs - 4.0 - 0.01, 0, P.wind_gland_z), P.wind_gland_angle)
        worst = max(worst, body.common(ln).Volume)
    out.append(("wind_body: gland locknut seats flat inside (%g mm of thread left for it)"
                % (P.gland_thread - P.gland_wall - P.port_gasket_t), worst))
    return out


# ---------------------------------------------------------------- assembly ---
def parts():
    return {
        "wind_body": body(),
        "wind_lid": lid(),
        "wind_pcb_ring": pcb_ring(),
        "wind_spacer": spacer(),
        "wind_shim": shim(),
        "tpu_wind_lid_gasket": lid_gasket(),
        "vane_rotor": vane_rotor(),
        "cup_hub": cup_hub(),
        "cup_hub_cap": cup_hub_cap(),
        "cup_arm": cup_arm(),
    }


def place(p):
    """Return [(name, shape)] positioned in the kit frame."""
    h = P.wind_body_h
    hl = h + P.wind_gasket_t                    # underside of the lid
    out = [("wind_body", p["wind_body"]),
           ("tpu_wind_lid_gasket", mv(p["tpu_wind_lid_gasket"], 0, 0, h)),
           ("wind_lid", mv(p["wind_lid"], 0, 0, hl)),
           ("wind_pcb_ring", mv(p["wind_pcb_ring"], 0, 0, hl - P.pcb_standoff))]
    out.append(("vane_rotor", mv(vane_rotor_use(), 0, 0, hl + P.wind_lid_t)))
    zh = -(_hub_h() + P.lip_h)
    out.append(("cup_hub", mv(p["cup_hub"], 0, 0, zh)))
    out.append(("cup_hub_cap", mv(p["cup_hub_cap"], 0, 0, zh - 2.4)))
    arm = rz(rx(p["cup_arm"], 90), 180)          # mouth faces -Y, arm runs to the axis
    arm = mv(arm, P.cup_arm_r, -P.cup_arm_t / 2, zh + P.cup_arm_h / 2)
    for i, a in enumerate(polar(arm, P.n_cups, 60.0)):
        out.append((f"cup_arm_{i + 1}", a))
    return out


def reference():
    """Bought-in parts drawn for context: PCB, bearings, shaft screws."""
    h = P.wind_body_h + P.wind_gasket_t
    ref = [("vane_pcb", tube(P.vane_pcb_d, P.vane_pcb_hole, P.vane_pcb_t,
                             (0, 0, h - P.pcb_standoff - P.vane_pcb_t)))]
    for i, z in enumerate((0.0, P.brg_w + P.brg_sep, h, h + P.brg_w + P.brg_sep)):
        ref.append((f"bearing_{i + 1}", tube(P.brg_od, P.brg_id, P.brg_w, (0, 0, z))))
    return ref
