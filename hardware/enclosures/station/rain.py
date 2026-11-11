"""Tipping-bucket rain gauge: base, bucket, funnel.

Parts come back in PRINT orientation. place() uses the gauge frame: axis on Z,
z = 0 at the underside of the base, bucket see-saws along X. The four M5 holes
sit on the 45 degree diagonals, so the gauge can straddle a 2020 running either
way underneath without the profile blocking the drains.
"""
import math

import params as P
from lib import *


def _upright_y():
    return P.rain_bucket_w / 2 + P.rain_side_gap


def base():
    R = P.rain_r
    t = P.rain_base_t
    zp = P.rain_pivot_z
    ut = P.rain_upright_t
    y0 = _upright_y()
    mag_z = zp - P.rain_pivot_h + 1.0 + P.rain_mag_d / 2      # magnet height, bucket level

    parts = [cyl(2 * (R + P.rain_wall), t),
             tube(2 * (R - 0.25), 2 * (R - 3.25), P.rain_ring_h, (0, 0, t - 0.01))]
    parts.append(box(-4, 4, -(y0 + ut), -y0, t - 0.01, zp + 5))
    parts.append(box(-4, 4, y0, y0 + ut, t - 0.01, zp + 5))
    # reed post beside one end of the bucket: the reed lies along X in a channel on top
    cw = P.reed_d + 0.3
    rl = P.reed_l / 2 + 1.0
    post_top = mag_z + P.reed_d / 2 + 0.4
    parts.append(box(P.rain_mag_x - rl, P.rain_mag_x + rl,
                     P.rain_reed_y - cw / 2 - 1.2, P.rain_reed_y + cw / 2 + 1.2,
                     t - 0.01, post_top))
    for s in (1, -1):
        parts.append(cyl(8.0, P.rain_stop_boss_h, (s * P.rain_stop_x, 0, t - 0.01)))
        # foot gussets so the uprights do not rely on a butt joint
        y = s * (y0 + ut)
        parts.append(prism([(y, t), (y + s * 6, t), (y, t + 12)], 3.0, "yz", -1.5))
    s = fuse(parts)

    cuts = [cyl(P.rain_axle_d + 0.3, 2 * (y0 + ut) + 2, (0, -(y0 + ut) - 1, zp), (0, 1, 0))]
    cuts.append(box(P.rain_mag_x - rl - 1, P.rain_mag_x + rl + 1,
                    P.rain_reed_y - cw / 2, P.rain_reed_y + cw / 2,
                    post_top - (P.reed_d + 0.2), post_top + 1))
    for sx in (1, -1):
        cuts.append(cyl(P.m3_tap_d, P.rain_stop_boss_h + t + 1, (sx * P.rain_stop_x, 0, -0.5)))
        # drains under each spill end
        x0 = P.rain_stop_x + 7.0
        x1 = R - 8.0
        cuts.append(box(min(sx * x0, sx * x1), max(sx * x0, sx * x1), -13, 13, -0.5, t + 0.5))
    for a in (45, 135, 225, 315):
        cuts.append(cyl(P.m5_clear, t + 1, pol(P.rain_foot_r, a, -0.5)))
    # funnel fixing screws, self-tapping into the ring
    for a in (90, 210, 330):
        cuts.append(rz(cyl(P.m3_tap_d, 8, (R - 5, 0, t + P.rain_ring_h / 2), (1, 0, 0)), a))
    # weep notches so the dish cannot hold water
    for a in (0, 180):
        cuts.append(rz(box(R - 4, R + 0.2, -1.5, 1.5, t - 0.01, t + 2.5), a))
    return cut(s, cuts)


def bucket():
    """Upright as used, floor on the bed. Pivot bore runs along Y."""
    L = P.rain_bucket_l / 2
    W = P.rain_bucket_w / 2
    ft = P.rain_bucket_floor
    wt = P.rain_bucket_wall
    dh = P.rain_divider_h
    bz = P.rain_mag_d + 1.6
    parts = [box(-L, L, -W, W, 0, ft),
             box(-3.5, 3.5, -W, W, 0, 2 * P.rain_pivot_h),
             box(-1.2, 1.2, -W, W, 0, dh)]
    side = [(-L, 0), (L, 0), (L, P.rain_end_h), (1.2, dh), (-1.2, dh), (-L, P.rain_end_h)]
    parts.append(prism(side, wt, "xz", W - wt))
    parts.append(prism(side, wt, "xz", -W))
    # magnet boss on one corner, an identical dummy on the opposite corner for balance.
    # The magnet stands on edge with its axis along the bucket (X), parallel to the reed.
    mx, by = P.rain_mag_x, P.rain_boss_y
    mt = P.rain_mag_t + 0.2
    cuts = [cyl(P.rain_axle_d + 0.5, 2 * W + 2, (0, -W - 1, P.rain_pivot_h), (0, 1, 0))]
    for s in (1, -1):
        y0, y1 = sorted((s * (W - 0.01), s * (W + by)))
        parts.append(box(s * mx - 3.2, s * mx + 3.2, y0, y1, 0, bz))
        p0, p1 = sorted((s * (W + 0.6), s * (W + by + 0.1)))
        cuts.append(box(s * mx - mt / 2, s * mx + mt / 2, p0, p1, 1.0, bz + 0.1))
    return cut(fuse(parts), cuts)


def funnel_use():
    """Funnel in the gauge frame (rim up)."""
    R = P.rain_r
    w = P.rain_wall
    rn = P.rain_nozzle_d / 2
    zn = P.rain_nozzle_z
    zc = P.rain_cone_z
    zw = P.rain_wall_z
    zt = P.rain_top_z
    tv = w * math.sqrt(2.0)
    z_skirt = P.rain_base_t
    prof = [
        (R + w, z_skirt),
        (R + w, zt - w),
        (R + 0.6, zt),              # knife edge, 45 deg chamfer on the outside
        (R, zt),
        (R, zw),
        (rn, zc),
        (rn, zn),
        (rn + w, zn),
        (rn + w, zc + w - tv),
        (R, zw - tv),
        (R, z_skirt),
    ]
    s = revolve(prof)
    cuts = [rz(cyl(P.m3_clear, 8, (R - 2, 0, z_skirt + P.rain_ring_h / 2), (1, 0, 0)), a)
            for a in (90, 210, 330)]
    return cut(s, cuts)


def funnel():
    """Printed upside down, knife edge on the bed: the cone then closes in at 45 deg."""
    return flip(funnel_use())


def parts():
    return {"rain_base": base(), "rain_bucket": bucket(), "rain_funnel": funnel()}


def place(p):
    b = mv(p["rain_bucket"], 0, 0, -P.rain_pivot_h)
    b = rot(b, P.rain_tilt, (0, 1, 0))
    b = mv(b, 0, 0, P.rain_pivot_z)
    return [("rain_base", p["rain_base"]), ("rain_bucket", b), ("rain_funnel", funnel_use())]
