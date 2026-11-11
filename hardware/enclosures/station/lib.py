"""Small solid-modelling helpers on top of FreeCAD's Part kernel. Units: mm."""
import math
import os

import FreeCAD as App
import Part

V = App.Vector


def cyl(d, h, at=(0, 0, 0), axis=(0, 0, 1)):
    return Part.makeCylinder(d / 2.0, h, V(*at), V(*axis))


def cone(d0, d1, h, at=(0, 0, 0), axis=(0, 0, 1)):
    if abs(d0 - d1) < 1e-6:
        return cyl(d0, h, at, axis)
    return Part.makeCone(d0 / 2.0, d1 / 2.0, h, V(*at), V(*axis))


def tube(do, di, h, at=(0, 0, 0)):
    return cyl(do, h, at).cut(cyl(di, h + 0.02, (at[0], at[1], at[2] - 0.01)))


def box(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box given by its extents."""
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def prism(pts, h, plane="xy", at=0.0):
    """Extrude a closed 2-D polygon by h along the plane normal, starting at `at`."""
    if plane == "xy":
        vs = [V(a, b, at) for a, b in pts]
        d = V(0, 0, h)
    elif plane == "xz":
        vs = [V(a, at, b) for a, b in pts]
        d = V(0, h, 0)
    elif plane == "yz":
        vs = [V(at, a, b) for a, b in pts]
        d = V(h, 0, 0)
    else:
        raise ValueError(plane)
    face = Part.Face(Part.makePolygon(vs + [vs[0]]))
    return face.extrude(d)


def revolve(pts):
    """Revolve a closed (r, z) polygon 360 degrees about the Z axis."""
    vs = [V(r, 0, z) for r, z in pts]
    face = Part.Face(Part.makePolygon(vs + [vs[0]]))
    return face.revolve(V(0, 0, 0), V(0, 0, 1), 360)


def hexprism(af, h, at=(0, 0, 0)):
    """Hexagonal prism, `af` across flats, flats facing +/-Y."""
    r = af / math.sqrt(3.0)
    pts = [(at[0] + r * math.cos(math.radians(a)), at[1] + r * math.sin(math.radians(a)))
           for a in range(0, 360, 60)]
    return prism(pts, h, "xy", at[2])


def obround(d, length, h, at=(0, 0, 0)):
    """Slot along X: two half-circles of diameter d, centres `length` apart."""
    x, y, z = at
    s = box(x - length / 2, x + length / 2, y - d / 2, y + d / 2, z, z + h)
    return s.fuse(cyl(d, h, (x - length / 2, y, z))).fuse(cyl(d, h, (x + length / 2, y, z)))


def clean(s):
    try:
        r = s.removeSplitter()
        if r.isValid():
            return r
    except Exception:
        pass
    return s


def fuse(shapes):
    shapes = [s for s in shapes if s is not None]
    out = shapes[0]
    for s in shapes[1:]:
        out = out.fuse(s)
    return clean(out)


def cut(base, tools):
    for t in tools:
        if t is not None:
            base = base.cut(t)
    return clean(base)


def mv(s, x=0.0, y=0.0, z=0.0):
    r = s.copy()
    r.translate(V(x, y, z))
    return r


def rot(s, deg, axis=(0, 0, 1), about=(0, 0, 0)):
    r = s.copy()
    r.rotate(V(*about), V(*axis), deg)
    return r


def rz(s, deg):
    return rot(s, deg, (0, 0, 1))


def rx(s, deg):
    return rot(s, deg, (1, 0, 0))


def ry(s, deg):
    return rot(s, deg, (0, 1, 0))


def polar(s, n, start=0.0):
    return [rz(s, start + i * 360.0 / n) for i in range(n)]


def pol(r, deg, z=0.0):
    a = math.radians(deg)
    return (r * math.cos(a), r * math.sin(a), z)


def bbox(s):
    """Tight bounding box. Shape.BoundBox can keep the extent of material that a
    boolean cut has since removed from a curved face, so never size or seat a
    part from it."""
    try:
        return s.optimalBoundingBox(False, False)
    except Exception:
        return s.BoundBox


def to_bed(s):
    """Drop a shape so its lowest point sits on z = 0."""
    return mv(s, 0, 0, -bbox(s).ZMin)


def flip(s):
    """Turn a shape upside down (about X) and sit it on the bed."""
    return to_bed(rx(s, 180))


def text_solid(text, height, depth, font):
    """Flat lettering centred on the origin, reading normally from +Z, z = 0..depth.

    Returns None if the font file is not there, so labels degrade to "no labels".
    """
    if not font or not os.path.exists(font):
        return None
    chars = Part.makeWireString(text, os.path.dirname(font) + "/", os.path.basename(font),
                                height, 0.0)
    faces = []
    for wires in chars:
        if not wires:
            continue
        wires = sorted(wires, key=lambda w: -w.BoundBox.DiagonalLength)
        f = Part.Face(wires[0])
        for inner in wires[1:]:
            f = f.cut(Part.Face(inner))
        faces.append(f)
    if not faces:
        return None
    s = Part.makeCompound(faces).extrude(V(0, 0, depth))
    bb = bbox(s)
    return mv(s, -(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, 0)
