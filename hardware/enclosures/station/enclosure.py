"""Core box for Board A and a loose 32xxx cell, plus the solar panel bracket.

Parts are returned in PRINT orientation.

Box frame (also its print frame): the back wall lies on the bed. X runs along
the board's long edge, Y is "up" once the box hangs on the mast, Z comes out
of the back wall toward the lid. The origin is the inside lower-left corner
on the inner face of the back wall, so cavity coordinates read directly.
All five cable entries are in the bottom wall and face the ground.
"""
import math

import params as P
from lib import *


def _ears():
    """(x, y) of the six lid-screw ears, in the box frame."""
    W, H, t = P.enc_in_w, P.enc_in_h, P.enc_wall
    o = t + 2.0
    ym = P.enc_bay + P.brd_w + 12.0
    return [(-o, -o), (W + o, -o), (-o, H + o), (W + o, H + o),
            (-t - 3.0, ym), (W + t + 3.0, ym)]


def _outline(z0, z1):
    """Outer wall outline as a solid slab between z0 and z1, corners rounded."""
    W, H, t = P.enc_in_w, P.enc_in_h, P.enc_wall
    r = 3.0
    s = box(-t + r, W + t - r, -t, H + t, z0, z1).fuse(box(-t, W + t, -t + r, H + t - r, z0, z1))
    for x in (-t + r, W + t - r):
        for y in (-t + r, H + t - r):
            s = s.fuse(cyl(2 * r, z1 - z0, (x, y, z0)))
    return s


def port_positions():
    """Centre X of each cable entry, spread evenly along the bottom wall."""
    n = len(P.enc_ports)
    free = P.enc_in_w - sum(p[2] for p in P.enc_ports)
    gap = free / (n + 1)
    xs, x = [], gap
    for _label, _d, flange in P.enc_ports:
        xs.append(x + flange / 2)
        x += flange + gap
    return xs


def body():
    W, H, D = P.enc_in_w, P.enc_in_h, P.enc_in_d
    t, tb = P.enc_wall, P.enc_back
    parts = [_outline(-tb, D)]
    parts += [cyl(10.0, D + tb, (x, y, -tb)) for x, y in _ears()]
    # mounting tabs in the plane of the back wall: top/bottom for a vertical
    # 2020, left/right for a horizontal one
    tl, tw, tt = P.enc_tab_len, P.enc_tab_w / 2, P.enc_tab_t
    cx, ly = P.enc_tab_x, P.enc_lr_tab_y
    bcx = P.enc_batt_x
    parts.append(box(cx - tw, cx + tw, H + t - 1, H + t + tl, -tb, -tb + tt))
    parts.append(box(cx - tw, cx + tw, -t - tl, -t + 1, -tb, -tb + tt))
    parts.append(box(-t - tl, -t + 1, ly - tw, ly + tw, -tb, -tb + tt))
    parts.append(box(W + t - 1, W + t + tl, ly - tw, ly + tw, -tb, -tb + tt))
    s = fuse(parts)
    s = cut(s, [box(0, W, 0, H, 0, D + 1)])

    inner = []
    bx, by = P.enc_brd_x, P.enc_brd_y
    for hx, hy in P.brd_holes:
        inner.append(cyl(7.5, P.standoff_h + 0.01, (bx + hx, by + hy, -0.01)))
    # rest for the corner of the board that has no mounting hole (under the radio)
    ex = bx + P.brd_l
    inner.append(box(ex - 9, ex, by + P.brd_w - 2.0, by + P.brd_w + 2.2, -0.01, P.standoff_h))
    inner.append(box(ex - 9, ex, by + P.brd_w + 0.4, by + P.brd_w + 2.2,
                     -0.01, P.standoff_h + P.brd_t + 1.5))
    # antenna keeper: a saddle the whip lies in, so it cannot swing on its SMA
    ax, az = P.enc_ant_x, P.standoff_h + P.sma_z
    ky = by + P.sma_y + 0.6 * P.ant_len
    kr = P.ant_d / 2 + 0.4
    inner.append(box(ax - kr - 3.0, min(ax + kr + 3.0, W), ky - 1.5, ky + 1.5, -0.01, az + 1.0))
    # cell cradle: two saddles and two end stops
    cy, cz, r = P.enc_batt_y, P.enc_batt_z, P.batt_d / 2
    for sx in (-1, 1):
        x = bcx + sx * (P.batt_l / 2 - 14.0)
        inner.append(box(x - 2.5, x + 2.5, cy - r - 3, min(cy + r + 3, H), -0.01, cz - r * 0.2))
        xe = bcx + sx * (P.batt_l / 2 + P.batt_end_gap)
        inner.append(box(xe - 1.2, xe + 1.2, cy - 8, cy + 8, -0.01, cz + 5))
    s = fuse([s] + inner)

    cell_span = P.batt_l + 2 * P.batt_end_gap - 2.6          # stops short of the end stops
    cuts = [cyl(P.batt_d + 0.6, cell_span, (bcx - cell_span / 2, cy, cz), (1, 0, 0))]
    cuts.append(cyl(2 * kr, 5, (ax, ky - 2.5, az), (0, 1, 0)))
    cuts.append(box(ax - kr, ax + kr, ky - 2.5, ky + 2.5, az, az + 2))
    for hx, hy in P.brd_holes:
        d = P.standoff_h + tb - 1.2
        cuts.append(cyl(P.m3_insert_d, d + 0.01, (bx + hx, by + hy, P.standoff_h - d)))
    for x, y in _ears():
        d = P.m3_insert_l + 1.0
        cuts.append(cyl(P.m3_insert_d, d + 0.01, (x, y, D - d)))
    # seal groove in the rim
    gw, gd = P.enc_groove_w, P.enc_groove_d
    a, b = t / 2 + gw / 2, t / 2 - gw / 2
    cuts.append(box(-a, W + a, -a, H + a, D - gd, D + 0.01).cut(
        box(-b, W + b, -b, H + b, D - gd - 1, D + 1)))
    # cable entries, bottom wall
    for (label, d, _fl), x in zip(P.enc_ports, port_positions()):
        cuts.append(cyl(d, t + 2, (x, -t - 1, D / 2), (0, 1, 0)))
    # no antenna hole: the antenna stays inside (ASA passes 868 MHz), one leak fewer
    # tab holes
    o = tl / 2 + 0.5
    for x, y in ((cx, H + t + o), (cx, -t - o), (-t - o, ly), (W + t + o, ly)):
        cuts.append(cyl(P.m5_clear, tt + 1, (x, y, -tb - 0.5)))
    return mv(cut(s, cuts), 0, 0, tb)


def lid():
    """Outside face on the bed; the ridge that presses into the TPU gasket points up."""
    W, H = P.enc_in_w, P.enc_in_h
    t, lt = P.enc_wall, P.enc_lid_t
    parts = [_outline(0, lt)] + [cyl(10.0, lt, (x, y, 0)) for x, y in _ears()]
    tw = 0.8                                  # a narrow ridge seals with far less screw force
    a, b = t / 2 + tw / 2, t / 2 - tw / 2
    th = P.enc_groove_d - P.gasket_h + P.gasket_squeeze
    parts.append(box(-a, W + a, -a, H + a, lt - 0.01, lt + th).cut(
        box(-b, W + b, -b, H + b, lt - 1, lt + th + 1)))
    # pad that presses on the cell (stick 3 mm foam on it)
    cy = P.enc_batt_y
    pad_h = P.enc_in_d - (P.enc_batt_z + P.batt_d / 2) - 3.0
    if pad_h > 0.6:
        px = W - P.enc_batt_x                 # the lid is modelled face down, so X is mirrored
        parts.append(box(px - 20, px + 20, cy - 6, cy + 6, lt - 0.01, lt + pad_h))
    s = fuse(parts)
    cuts = [cyl(P.m3_clear, lt + 1, (x, y, -0.5)) for x, y in _ears()]
    # Port names, laid out as they read from outside the closed box, then turned
    # over with the lid: on the bed they are mirrored, which is correct.
    for (label, _d, _fl), x in zip(P.enc_ports, port_positions()):
        txt = text_solid(label, P.label_h, P.label_depth + 0.01, P.label_font)
        if txt is None:
            continue
        txt = mv(txt, x, P.label_h / 2 + 3.0, -0.01)
        cuts.append(mv(rot(txt, 180, (0, 1, 0), (W / 2, 0, 0)), 0, 0, P.label_depth - 0.01))
    return cut(s, cuts)


def lid_use():
    """Lid turned over and seated on the box (box frame, back wall at z = 0..)."""
    s = rot(lid(), 180, (0, 1, 0), (P.enc_in_w / 2, 0, 0))
    return mv(s, 0, 0, P.enc_back + P.enc_in_d + P.enc_lid_t)


def lid_gasket():
    """TPU ring that lies in the rim groove. Print flat, 100 % infill."""
    W, H, t = P.enc_in_w, P.enc_in_h, P.enc_wall
    gk = P.enc_groove_w - 0.2
    a, b = t / 2 + gk / 2, t / 2 - gk / 2
    return box(-a, W + a, -a, H + a, 0, P.gasket_h).cut(box(-b, W + b, -b, H + b, -1, P.gasket_h + 1))


def washer(hole_d, flange_d):
    """TPU washer for under a connector or gland flange."""
    return tube(flange_d + 1.0, hole_d + 0.2, P.port_gasket_t)


_WASHERS = (("tpu_washer_gland", "gland_d", "gland_flange"),
            ("tpu_washer_gx12", "gx12_d", "gx12_flange"),
            ("tpu_washer_gx16", "gx16_d", "gx16_flange"))


# ----------------------------------------------------------- solar bracket ---
def solar_bracket():
    """Foot plate on the bed; the tray leans at solar_tilt from vertical while printing.

    Frame: X across the panel, Y "up" in use, Z out from the 2020 face.
    """
    t = math.radians(P.solar_tilt)
    S, TW = P.solar_slope, P.solar_tray_w / 2
    ft, fw = P.solar_foot_t, P.solar_foot_w / 2
    fl, rim = P.solar_floor, P.solar_rim
    yh = P.solar_high_y
    y_lo = -(P.solar_foot_pitch + P.m5_head_d / 2 + 3.0)

    # tray built flat (local y = panel normal, local z = down the slope), then tilted
    tray = [box(-TW, TW, -fl, 0, 0, S)]
    rh = P.panel_t + 0.5
    tray.append(box(-TW, -TW + rim, 0, rh, 0, S))
    tray.append(box(TW - rim, TW, 0, rh, 0, S))
    tray.append(box(-TW, TW, 0, 1.2, 0, rim))                 # low locating lips only:
    tray.append(box(-TW, TW, 0, 1.2, S - rim, S))             # a full rim would overhang
    tray = fuse(tray)
    tray = cut(tray, [cyl(16.0, fl + 2, (0, 1, S / 2), (0, -1, 0)),          # cable exit
                      box(-TW / 2 - 3, -TW / 2 + 3, 0, 2, S - rim - 0.1, S + 0.1),
                      box(TW / 2 - 3, TW / 2 + 3, 0, 2, S - rim - 0.1, S + 0.1)])
    tray = mv(rx(tray, P.solar_tilt), 0, yh, ft - 0.5)

    def under(s):                                              # point on the tray underside
        return (yh - s * math.sin(t) - fl * math.cos(t) + 0.3 * math.cos(t),
                ft - 0.5 + s * math.cos(t) - fl * math.sin(t) + 0.3 * math.sin(t))

    # T-shaped foot: the bar across the top is what the whole width of the tray grows from
    parts = [box(-fw, fw, y_lo, yh + 2.0, 0, ft), box(-TW, TW, yh - 7.0, yh + 2.0, 0, ft), tray]
    for x0 in (-fw, fw - 4.0):
        parts.append(prism([(y_lo, ft - 0.01), under(0.0), under(S * 0.92)], 4.0, "yz", x0))
    s = fuse(parts)
    p = P.solar_foot_pitch
    cuts = [cyl(P.m5_clear, ft + 1, (x, y, -0.5)) for x, y in ((0, p), (0, -p), (p, 0), (-p, 0))]
    return cut(s, cuts)


def parts():
    out = {"enclosure_body": body(), "enclosure_lid": lid(), "solar_bracket": solar_bracket(),
           "tpu_box_lid_gasket": lid_gasket()}
    for name, d, fl in _WASHERS:
        out[name] = washer(getattr(P, d), getattr(P, fl))
    return out


def place(p):
    t, tb, D = P.enc_wall, P.enc_back, P.enc_in_d
    out = [("enclosure_body", p["enclosure_body"]), ("enclosure_lid", lid_use()),
           ("tpu_box_lid_gasket", mv(p["tpu_box_lid_gasket"], 0, 0, tb + D - P.enc_groove_d))]
    for i, ((label, d, fl), x) in enumerate(zip(P.enc_ports, port_positions())):
        w = rx(washer(d, fl), 90)                      # axis along Y, lying under the flange
        out.append(("tpu_washer_%d_%s" % (i + 1, label.lower()), mv(w, x, -t, tb + D / 2)))
    return out


def reference():
    bx, by = P.enc_brd_x, P.enc_brd_y
    z = P.enc_back + P.standoff_h
    ref = [("board_a", box(bx, bx + P.brd_l, by, by + P.brd_w, z, z + P.brd_t)),
           ("cell", cyl(P.batt_d, P.batt_l,
                        (P.enc_batt_x - P.batt_l / 2, P.enc_batt_y, P.enc_back + P.enc_batt_z),
                        (1, 0, 0)))]
    # the antenna: SMA elbow out of the board's end, whip pointing up
    az = z + P.sma_z
    sx = bx + P.brd_l
    ref.append(("antenna", cyl(7.0, P.sma_out + P.ant_elbow, (sx, by + P.sma_y, az), (1, 0, 0)).fuse(
        cone(P.ant_d, P.ant_d * 0.7, P.ant_len, (P.enc_ant_x, by + P.sma_y, az), (0, 1, 0)))))
    return ref


def solar_reference():
    t = P.solar_tilt
    TW = P.panel_l / 2
    pan = box(-TW, TW, 0.2, 0.2 + P.panel_t, P.solar_rim + P.fit_slide,
              P.solar_rim + P.fit_slide + P.panel_w)
    return [("solar_panel", mv(rx(pan, t), 0, P.solar_high_y, P.solar_foot_t - 0.5))]
