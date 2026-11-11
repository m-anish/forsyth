"""Sky pod: an MLX90614 thermopile looking up from above the mast top.

Three parts. The MOUNT bolts to the mast face opposite the wind arm and ends
in a tilted plug. The HEAD is a cap that slides over the plug: the sensor
module sits on the plug, its can pokes up through the head's floor into a
recessed, open cone, and a TPU ring round the can seals the gap. Two M3
screws through the head's side hold it on.

Mount frame (use): x = distance out from the mast face, z = height above the
mast top, tilt leans the sensor axis toward +x (mount that face to the north).
Head frame: z along the sensor axis from the head's open rim, +x downhill.
"""
import math

import params as P
from lib import *

SKIRT = 2.0          # head rim hangs this far below the plug, as a drip edge


def _axis_origin():
    """Where the head frame's origin sits in the mount frame."""
    t = math.radians(P.sky_tilt)
    d = SKIRT + P.sky_plug_h / 2
    return (P.sky_pod_x - d * math.sin(t), 0.0, P.sky_zc - d * math.cos(t))


def to_mount(shape):
    """Head frame -> mount frame."""
    x, y, z = _axis_origin()
    return mv(ry(shape, P.sky_tilt), x, y, z)


def head_local():
    ro, rc = P.sky_ro, P.sky_rc
    z_floor = SKIRT + P.sky_plug_h + P.sky_pcb_t + P.sky_ring_c    # underside of the floor
    z_snout = z_floor + P.sky_floor
    ht = P.sky_ht
    r0 = P.sky_can_d / 2 + 0.8
    s = cyl(2 * ro, ht)
    cuts = [
        cyl(2 * rc, z_floor + 0.01, (0, 0, -0.01)),
        cyl(P.sky_can_d + 0.4, P.sky_floor + 0.02, (0, 0, z_floor - 0.01)),
        cone(2 * r0, 2 * P.sky_r1, P.sky_snout + 0.01, (0, 0, z_snout)),
        # drains at floor level, both sides, so the head cannot go on the wrong way round
        box(-(ro + 1), ro + 1, -1.2, 1.2, z_snout, z_snout + 2.2),
        # fixing screws, across the tilt direction
        cyl(P.m3_clear, 2 * ro + 2, (0, -ro - 1, SKIRT + P.sky_plug_h / 2), (0, 1, 0)),
    ]
    return cut(s, cuts)


def head():
    """Printed upside down, rim of the cone on the bed."""
    return flip(head_local())


def can_seal():
    """TPU ring round the sensor can, squeezed between the module and the head's floor."""
    return tube(P.sky_can_d + 5.0, P.sky_can_d - 0.2, P.sky_ring_c + 0.3)


def mount_use():
    ft, fw, fh = P.sky_foot_t, P.sky_foot_w / 2, P.sky_foot_h
    rp = P.sky_rp
    top = SKIRT + P.sky_plug_h                       # plug face the module sits on (head frame)
    ztop = P.sky_zc + 8.0
    s = fuse([box(0, ft, -fw, fw, -fh, 0),
              box(0, ft, -11, 11, -1, ztop),
              box(0, ft + 4, -2, 2, -1, ztop)])
    # nothing but the plug may stand above the head's rim plane, or the head cannot go on
    s = s.cut(to_mount(box(-150, 150, -150, 150, -0.5, 300)))
    s = fuse([s, to_mount(cyl(2 * rp, P.sky_neck + top, (0, 0, -P.sky_neck)))])

    hx = P.sky_hdr_off
    wires = rz(obround(4.0, 6.0, P.sky_neck + top + 4, (0, 0, -P.sky_neck - 2)), 90)
    cuts = [
        box(-80, 0, -80, 80, -200, 300),                                 # flat on the mast face
        to_mount(mv(wires, hx, 0, 0)),                                   # wires drop through here
        to_mount(box(hx - 3, hx + 3, -6.5, 6.5, top - 2.0, top + 0.1)),  # room for solder joints
    ]
    for sy in (1, -1):
        cuts.append(to_mount(cyl(P.m3_tap_d, 7.0, (0, sy * (rp + 0.1), SKIRT + P.sky_plug_h / 2),
                                 (0, -sy, 0))))
        for z in (ztop * 0.2, ztop * 0.45):                              # zip-tie notches
            cuts.append(box(-1, ft + 1, sy * 9.0, sy * 12.0, z, z + 3.5)
                        if sy > 0 else box(-1, ft + 1, -12.0, -9.0, z, z + 3.5))
    zc = -fh / 2
    for dy, dz in ((0, P.sky_foot_pitch), (0, -P.sky_foot_pitch),
                   (P.sky_foot_pitch, 0), (-P.sky_foot_pitch, 0)):
        cuts.append(cyl(P.m5_clear, ft + 2, (-1, dy, zc + dz), (1, 0, 0)))
    return cut(s, cuts)


def mount():
    """Printed with the mast face on the bed."""
    return to_bed(rot(mount_use(), -120, (1, 1, 1)))


def parts():
    return {"sky_mount": mount(), "sky_head": head(), "tpu_sky_can_seal": can_seal()}


def place(p):
    z_pcb = SKIRT + P.sky_plug_h + P.sky_pcb_t
    return [("sky_mount", mount_use()),
            ("sky_head", to_mount(head_local())),
            ("tpu_sky_can_seal", to_mount(mv(p["tpu_sky_can_seal"], 0, 0, z_pcb)))]


def reference():
    z0 = SKIRT + P.sky_plug_h
    w = P.sky_pcb_w / 2
    mod = box(-P.sky_can_off, P.sky_pcb_l - P.sky_can_off, -w, w, z0, z0 + P.sky_pcb_t).fuse(
        cyl(P.sky_can_d, P.sky_can_h, (0, 0, z0 + P.sky_pcb_t)))
    return [("sky_sensor", to_mount(mod))]
