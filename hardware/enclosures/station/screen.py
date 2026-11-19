"""Stevenson screen (multi-plate radiation shield) for the sensor carrier (Board B).

A stack of identical 45 degree louvres on a base, closed by a cap, clamped by
three M4 screws. Parts are returned in PRINT orientation. place() uses the screen
frame: axis on Z, z = 0 at the underside of the base.
"""
import math

import params as P
from lib import *

_POST_ANGLES = (90.0, 210.0, 330.0)


def _cone_shell(closed):
    """Louvre profile: rim low and outside, rising 45 deg to the inner opening."""
    ro, ri, h = P.scr_r_out, P.scr_r_in, P.scr_plate_h
    tv = P.scr_plate_t * math.sqrt(2.0)
    s = revolve([(ro, 0), (ro, tv), (ri, h + tv), (ri, h)])
    if closed:
        s = s.fuse(cyl(2 * ri + 0.2, tv, (0, 0, h)))
    return clean(s)


def plate():
    """One louvre; rim on the bed. The posts stand on the bed and stack post-on-post."""
    s = fuse([_cone_shell(False)]
             + [cyl(P.scr_post_d, P.scr_pitch, pol(P.scr_post_r, a)) for a in _POST_ANGLES])
    return cut(s, [cyl(P.scr_rod_d + 0.4, P.scr_pitch + 1, pol(P.scr_post_r, a, -0.5))
                   for a in _POST_ANGLES])


_LTG_BOSS_L = P.m3_insert_l + 1.0      # boss length below the cap's underside


def _ltg_holes():
    """Lightning-module hole centres, carrier frame (before the 45 deg turn)."""
    x = P.scr_ltg_cx - P.scr_ltg_l / 2 + P.scr_ltg_hole_in
    return [(x, P.scr_ltg_cy - P.scr_ltg_hole_pitch / 2), (x, P.scr_ltg_cy + P.scr_ltg_hole_pitch / 2)]


def _ltg_fixture(h):
    """Bosses and rib under the cap disk (its underside at z = h), plus the insert pilots.

    In print orientation the cap lies upside down, so these stand straight up from the
    disk, inside the cone: no supports. Press the inserts in from the boss tips.
    """
    L = _LTG_BOSS_L
    add, holes = [], []
    for x, y in _ltg_holes():
        add.append(cyl(P.scr_ltg_boss_d, L + 0.5, (x, y, h - L)))
        holes.append(cyl(P.m3_insert_d, P.m3_insert_l + 0.5, (x, y, h - L - 0.01)))
    xr = P.scr_ltg_cx + P.scr_ltg_l / 2 - 5.0                  # rib under the connector end
    add.append(box(xr - P.scr_ltg_rib_t, xr, P.scr_ltg_cy - 6.0, P.scr_ltg_cy + 6.0,
                   h - L, h + 0.5))
    return [rz(s, 45) for s in add], [rz(s, 45) for s in holes]


def cap_use():
    """Closed top louvre, in the use frame (rim at z = 0)."""
    tv = P.scr_plate_t * math.sqrt(2.0)
    shell = _cone_shell(True)
    fix_add, fix_holes = _ltg_fixture(P.scr_plate_h)
    shell = shell.fuse(fuse(fix_add))
    seat = 3.0
    # nothing may stand proud of the cone: printed upside down it would start in
    # mid-air. Keep only the part of each post that lies under the cone's top skin.
    e = 0.05
    ro1 = P.scr_r_out + 1
    under = cyl(2 * ro1, tv - e, (0, 0, -1)).fuse(
        cone(2 * ro1, 2 * P.scr_r_in, ro1 - P.scr_r_in, (0, 0, tv - 1 - e)))
    posts = []
    for a in _POST_ANGLES:
        posts.append(cyl(P.scr_post_d, P.scr_pitch, pol(P.scr_post_r, a)).common(under))
    s = fuse([shell] + posts)
    cuts = []
    for a in _POST_ANGLES:
        cuts.append(cyl(P.scr_rod_d + 0.4, P.scr_pitch + 1, pol(P.scr_post_r, a, -0.5)))
        cuts.append(cyl(P.scr_head_d + 1.0, P.scr_pitch, pol(P.scr_post_r, a, seat)))  # head pocket
    return cut(s, cuts + fix_holes)


def cap():
    return flip(cap_use())


def base():
    t = P.scr_base_t
    ro = P.scr_r_out
    hub_r = P.scr_r_in - 1.0
    ring_w = P.scr_post_d + 2.0
    parts = [cyl(2 * hub_r, t), tube(2 * ro, 2 * (ro - ring_w), t)]
    for a in _POST_ANGLES:
        parts.append(rz(box(hub_r - 2, ro - ring_w + 2, -6, 6, 0, t), a))

    # carrier rails: the PCB plane runs along the 45 deg diagonal, clear of the M5 holes
    hw = P.scr_pcb_w / 2
    g = P.scr_pcb_groove
    rail_h = t + P.scr_pcb_lift + P.scr_pcb_h * 0.85
    # The carrier's two bottom corners rest on the solid rail below each groove. There
    # is no sill across the middle: the cable plug faces down out of the bottom edge.
    rails = [box(hw - g, hw + 0.3 + 4.0, -4, 4, t - 0.01, rail_h),
             box(-(hw + 0.3 + 4.0), -(hw - g), -4, 4, t - 0.01, rail_h)]
    groove = box(-(hw + 0.3), hw + 0.3, -(P.scr_pcb_t + 0.3) / 2, (P.scr_pcb_t + 0.3) / 2,
                 t + P.scr_pcb_lift, rail_h + 1)
    sled = cut(fuse(rails), [groove])
    parts.append(rz(sled, 45))
    s = fuse(parts)

    cuts = []
    for a in (0, 90, 180, 270):
        cuts.append(cyl(P.m5_clear, t + 1, pol(P.scr_foot_r, a, -0.5)))
    cuts.append(cyl(P.scr_cable_d, t + 1, pol(P.scr_foot_r + 1.0, 135, -0.5)))
    for a in _POST_ANGLES:
        x, y, _ = pol(P.scr_post_r, a)
        cuts.append(cyl(P.scr_rod_d + 0.4, t + 1, (x, y, -0.5)))
        cuts.append(rz(hexprism(P.scr_nut_af + 0.2, P.scr_nut_h - 0.4, (P.scr_post_r, 0, -0.01)), a))
    # floor vents either side of the sill
    for a in (315,):
        cuts.append(cyl(9.0, t + 1, pol(P.scr_foot_r + 1.0, a, -0.5)))
    return cut(s, cuts)


def parts():
    return {"screen_base": base(), "screen_plate": plate(), "screen_cap": cap()}


def place(p):
    out = [("screen_base", p["screen_base"])]
    z = P.scr_base_t
    for i in range(P.scr_plates):
        out.append((f"screen_plate_{i + 1}", mv(p["screen_plate"], 0, 0, z)))
        z += P.scr_pitch
    out.append(("screen_cap", mv(cap_use(), 0, 0, z)))
    return out


def reference():
    """Carrier (Board B) and the PMS7003 on its back, drawn for context.

    Carrier frame before the 45 deg turn: X across the board, Y normal to it, Z up.
    The front faces +Y (towards the base's cable hole, which J1's cable uses); the
    back faces -Y (towards the floor vent, under the PMS's own vents). Seen from the
    front, board x runs towards -X, so board x maps to X = w/2 - x.
    """
    t = P.scr_base_t
    hw = P.scr_pcb_w / 2
    z0 = t + P.scr_pcb_lift
    pcb = box(-hw, hw, -P.scr_pcb_t / 2, P.scr_pcb_t / 2, z0, z0 + P.scr_pcb_h)
    y_back = -P.scr_pcb_t / 2 - P.scr_pms_gap
    pms = box(hw - P.scr_pms_x[1], hw - P.scr_pms_x[0],
              y_back - P.scr_pms_t, y_back,
              z0 + P.scr_pms_y[0], z0 + P.scr_pms_y[1])
    # J2 (PH-5 vertical, carrier x 4..18, y 61) with its plug, on the front
    j2 = box(hw - 18.0, hw - 4.0, P.scr_pcb_t / 2, P.scr_pcb_t / 2 + 6.6 + 8.0,
             z0 + 61.0 - 3.0, z0 + 61.0 + 3.0)
    # lightning module, hanging parts-side down from the cap bosses
    zc = t + P.scr_plates * P.scr_pitch + P.scr_plate_h           # cap underside
    zb = zc - _LTG_BOSS_L                                          # module's bare back face
    x0, x1 = P.scr_ltg_cx - P.scr_ltg_l / 2, P.scr_ltg_cx + P.scr_ltg_l / 2
    y0, y1 = P.scr_ltg_cy - P.scr_ltg_w / 2, P.scr_ltg_cy + P.scr_ltg_w / 2
    zp = zb - P.scr_ltg_t
    ltg = fuse([box(x0, x1, y0, y1, zp, zb),
                box(x0 + 1.0, x1 - 1.0, y0 + 1.0, y1 - 1.0, zp - P.scr_ltg_parts_h, zp),
                box(x1 - 1.0, x1 + P.scr_ltg_plug, P.scr_ltg_cy - 5.0, P.scr_ltg_cy + 5.0,
                    zp - 6.0, zp)])
    return [("screen_pcb", rz(pcb, 45)), ("screen_pms7003", rz(pms, 45)),
            ("screen_j2_plug", rz(j2, 45)), ("screen_lightning", rz(ltg, 45))]


def height():
    tv = P.scr_plate_t * math.sqrt(2.0)
    return P.scr_base_t + P.scr_plates * P.scr_pitch + P.scr_plate_h + tv
