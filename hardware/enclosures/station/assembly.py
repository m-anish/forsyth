"""Illustrated assembly guide for the station kit, regenerated from params.py.

    ./build.sh                                   (runs this after build.py)
    STATION_DIR=$PWD freecadcmd assembly.py      (on its own)

Builds every printed part from the same modules build.py uses, adds simple
models of the bought-in hardware (screws, bearings, inserts, magnets, boards),
renders exploded and section views with VTK (bundled with FreeCAD, works
headless), and writes:

    docs/assembly/*.png       one picture per step
    docs/assembly.html        the guide: steps, parts, hardware, numbers

Every number in the guide is read from params.py (or computed the way the
part modules compute it), so a rebuild after a parameter change keeps the
pictures and the text in step with the parts. Do not edit the HTML by hand.

Set STATION_ONLY=wind_body,wind_cups to re-render a few figures while working.
"""
import html
import json
import math
import os
import sys
import time

HERE = os.environ.get("STATION_DIR") or os.getcwd()
sys.path.insert(0, HERE)

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

import params as P  # noqa: E402
from lib import *  # noqa: E402,F401,F403
import wind  # noqa: E402
import rain  # noqa: E402
import screen  # noqa: E402
import enclosure  # noqa: E402
import sky  # noqa: E402

import numpy as np  # noqa: E402
import vtk  # noqa: E402
from vtkmodules.util import numpy_support as vns  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage  # noqa: E402

DOCS = os.path.join(HERE, "docs")
FIG_DIR = os.path.join(DOCS, "assembly")
ONLY = set(filter(None, os.environ.get("STATION_ONLY", "").split(",")))

# ------------------------------------------------------------------ colours ---
# Printed parts use the filament colours from build.py's print_color(); bought-in
# parts get their material's colour so the two read apart at a glance.
COL = {
    "white": (0.93, 0.93, 0.91),      # white ASA
    "accent": (0.86, 0.38, 0.18),     # second ASA colour (vane, cups)
    "tpu": (0.20, 0.52, 0.62),        # TPU seals
    "steel": (0.60, 0.62, 0.66),
    "brass": (0.86, 0.66, 0.26),
    "magnet": (0.55, 0.20, 0.55),
    "pcb": (0.16, 0.48, 0.28),
    "glass": (0.62, 0.84, 0.90),
    "alu": (0.74, 0.77, 0.82),
    "black": (0.18, 0.18, 0.20),
    "cell": (0.22, 0.35, 0.65),
    "solar": (0.16, 0.20, 0.36),
}


def printed_color(name):
    if name.startswith("tpu_"):
        return "tpu"
    return "accent" if name.startswith(("vane_", "cup_")) else "white"


def fmt(v, nd=1):
    """Millimetre value for the text: at most nd decimals, no trailing zeros."""
    s = ("%." + str(nd) + "f") % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# ======================================================= bought-in hardware ===
# Each is modelled in a local frame with its axis on Z, then put in place with
# put(shape, at, axis): local z = 0 goes to `at`, local +Z points along `axis`.

def put(s, at=(0, 0, 0), axis=(0, 0, 1)):
    a = App.Vector(*axis)
    a.normalize()
    z = App.Vector(0, 0, 1)
    r = s.copy()
    c = z.cross(a)
    if c.Length > 1e-9:
        ang = math.degrees(math.atan2(c.Length, z.dot(a)))
        r.rotate(App.Vector(0, 0, 0), c, ang)
    elif z.dot(a) < 0:
        r.rotate(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 180)
    r.translate(App.Vector(*at))
    return r


def hw_shcs(d, L, head_d=None, head_h=None):
    """Socket-head cap screw. z = 0 is the underside of the head; the head is
    above (+Z), the shank runs down to z = -L."""
    head_d = head_d or 1.6 * d + 0.5
    head_h = head_h or d
    head = cyl(head_d, head_h)
    head = head.cut(hexprism(0.8 * d, 0.6 * head_h, (0, 0, head_h * 0.4 + 0.01)))
    return clean(head.fuse(cyl(d * 0.98, L, (0, 0, -L))))


def hw_button(d, L):
    """ISO 7380 button head (M5: 9.5 mm across, 2.75 high)."""
    hd, hh = 1.9 * d, 0.55 * d
    head = cone(hd, hd * 0.55, hh)
    head = head.cut(hexprism(0.6 * d, hh * 0.6, (0, 0, hh * 0.45)))
    return clean(head.fuse(cyl(d * 0.98, L, (0, 0, -L))))


def hw_nut(af, h, d):
    return cut(hexprism(af, h, (0, 0, 0)), [cyl(d, h + 1, (0, 0, -0.5))])


def hw_washer(di, do, t):
    return tube(do, di, t)


def hw_insert(od=4.2, L=6.0):
    """Brass heat-set insert. z = 0 is its top face; it goes down to z = -L."""
    body = cyl(od - 0.4, L, (0, 0, -L))
    for z in (-L + 0.8, -L / 2 - 0.6):
        body = body.fuse(cyl(od, 1.4, (0, 0, z)))
    body = body.fuse(cyl(od, 0.8, (0, 0, -0.8)))
    return cut(body, [cyl(2.6, L + 1, (0, 0, -L - 0.5))])


def hw_bearing(di, do, w):
    span = do - di
    outer = tube(do, do - 0.4 * span, w)
    inner = tube(di + 0.55 * span, di, w)
    shield = tube(do - 0.38 * span, di + 0.5 * span, w - 0.6, (0, 0, 0.3))
    return fuse([outer, inner, shield])


def hw_magnet(d, t):
    return cyl(d, t, (0, 0, -t / 2))


def hw_reed(glass_l, glass_d=2.0, lead=8.0):
    """Reed switch lying along X, centred on the origin."""
    g = cyl(glass_d, glass_l, (-glass_l / 2, 0, 0), (1, 0, 0))
    leads = [cyl(0.6, lead, (glass_l / 2, 0, 0), (1, 0, 0)),
             cyl(0.6, lead, (-glass_l / 2 - lead, 0, 0), (1, 0, 0))]
    return g, fuse(leads)


def hw_tnut(d=5.0):
    """2020 slot-6 T-nut (hammer-head style, simplified). Top face at z = 0."""
    s = box(-5.0, 5.0, -5.5, 5.5, -4.0, 0.0)
    s = s.fuse(box(-5.0, 5.0, -3.0, 3.0, 0.0, 1.8))
    return cut(s, [cyl(d, 8, (0, 0, -5))])


def hw_gland():
    """PG7 cable gland, seen with its flange at z = 0, dome up (+Z), thread down."""
    flange = hexprism(19.0, 3.0, (0, 0, 0))
    dome = cone(15.0, 10.0, 9.0, (0, 0, 3.0))
    thread = cyl(12.4, 8.0, (0, 0, -8.0))
    return cut(fuse([flange, dome, thread]), [cyl(5.0, 30, (0, 0, -15))])


def hw_gland_nut():
    return hw_nut(19.0, 4.0, 12.4)


def hw_gx(d, flange):
    """GX12/GX16 panel socket: flange at z = 0, front face up (+Z), threaded body down."""
    f = cyl(flange, 2.0)
    face = cyl(d - 0.6, 4.0, (0, 0, 2.0))
    body = cyl(d - 0.2, 14.0, (0, 0, -14.0))
    s = fuse([f, face, body])
    return cut(s, [cyl(d - 3.0, 3.0, (0, 0, 3.01))])


def hw_gx_nut(d, flange):
    return hw_nut(flange - 1.0, 2.5, d - 0.2)


def profile_2020(length, axis="z"):
    """20 x 20 slot-6 profile, centred on its axis, z = 0 .. length."""
    s = box(-10, 10, -10, 10, 0, length)
    cuts = [cyl(4.2, length + 2, (0, 0, -1))]
    for a in (0, 90, 180, 270):
        slot = fuse([box(10 - 6.1, 10.5, -3.1, 3.1, -1, length + 1),
                     box(10 - 6.1, 10 - 1.8, -5.6, 5.6, -1, length + 1)])
        cuts.append(rz(slot, a))
    s = cut(s, cuts)
    if axis == "x":
        s = ry(s, 90)
    elif axis == "y":
        s = rx(s, -90)
    return s


# ================================================================ renderer ===
class Item:
    """One thing to draw."""

    def __init__(self, shape, color, label=None, ctx=False, cut=True, opacity=1.0, lw=1.0):
        self.shape = shape
        self.color = COL[color] if isinstance(color, str) else color
        self.label = label        # legend text; items with the same label share a balloon
        self.ctx = ctx            # already assembled: drawn faded
        self.cut = cut            # cut by the scene's section plane
        self.opacity = opacity
        self.lw = lw


def _tess(shape, tol):
    pts, tris = shape.tessellate(tol)
    if not tris:
        return None, None
    return (np.array([[p.x, p.y, p.z] for p in pts], dtype=np.float64),
            np.array(tris, dtype=np.int64))


def _polydata(pts, tris):
    pd = vtk.vtkPolyData()
    vp = vtk.vtkPoints()
    vp.SetData(vns.numpy_to_vtk(pts, deep=True))
    pd.SetPoints(vp)
    cells = np.hstack([np.full((len(tris), 1), 3, dtype=np.int64), tris]).ravel()
    ca = vtk.vtkCellArray()
    ca.SetCells(len(tris), vns.numpy_to_vtkIdTypeArray(cells, deep=True))
    pd.SetPolys(ca)
    return pd


def _lines_polydata(polylines):
    pd = vtk.vtkPolyData()
    vp = vtk.vtkPoints()
    ca = vtk.vtkCellArray()
    for pl in polylines:
        ids = []
        for p in pl:
            ids.append(vp.InsertNextPoint(*p))
        line = vtk.vtkPolyLine()
        line.GetPointIds().SetNumberOfIds(len(ids))
        for i, k in enumerate(ids):
            line.GetPointIds().SetId(i, k)
        ca.InsertNextCell(line)
    pd.SetPoints(vp)
    pd.SetLines(ca)
    return pd


def _crease_edges(shape, tol):
    """B-rep edges worth drawing: skip seams and edges between tangent faces."""
    owners = {}
    for fi, f in enumerate(shape.Faces):
        for e in f.Edges:
            owners.setdefault(e.hashCode(), [e, []])[1].append(fi)
    out = []
    faces = shape.Faces
    for key, (e, fis) in owners.items():
        fis = sorted(set(fis))
        if len(fis) == 1:
            continue        # in a closed solid, an edge with one face is a seam
        if len(fis) == 2:
            try:
                p = e.valueAt((e.FirstParameter + e.LastParameter) / 2)
                ns_ = []
                for fi in fis:
                    f = faces[fi]
                    u, v = f.Surface.parameter(p)
                    ns_.append(f.normalAt(u, v))
                if ns_[0].dot(ns_[1]) > math.cos(math.radians(12)):
                    continue
            except Exception:
                pass
        try:
            pts = e.discretize(Deflection=tol)
        except Exception:
            continue
        if len(pts) >= 2:
            out.append([(p.x, p.y, p.z) for p in pts])
    return out


def _section(shape, plane):
    """Keep the part of `shape` behind the section plane (point, normal toward the viewer)."""
    (px, py, pz), n = plane
    n = App.Vector(*n)
    n.normalize()
    big = 4000.0
    half = Part.makeBox(2 * big, 2 * big, big, App.Vector(-big, -big, 0))
    half = put(half, (px, py, pz), (n.x, n.y, n.z))
    try:
        r = shape.cut(half)
        return r if r.Solids or r.Faces else None
    except Exception:
        return shape


def _faded(c, k=0.55):
    return tuple(x + (1.0 - x) * k for x in c)


class Scene:
    def __init__(self, name, items, view=(1, -1, 0.8), up=(0, 0, 1), size=(1200, 900),
                 section=None, dashes=(), margin=0.13, zoom=1.0, fit=None, dims=(),
                 compass=None):
        self.fit = fit            # points to frame instead of everything drawn (crops the rest)
        self.dims = dims          # [(p0, p1, text, offset_px)] drawn over the picture
        self.compass = compass    # world direction of north, for a north arrow
        self.text_labels = False  # name the parts in the picture instead of numbering them
        self.name = name
        self.items = items
        self.view = view          # direction from the model toward the camera
        self.up = up
        self.size = size
        self.section = section    # ((x, y, z), normal toward camera) or None
        self.dashes = dashes      # explode guide lines: [(p0, p1)]
        self.margin = margin      # fraction of the width kept free each side for balloons
        self.zoom = zoom


SS = 2  # supersampling


def _actor_for(pd, color, opacity=1.0, flat=False):
    nf = vtk.vtkPolyDataNormals()
    nf.SetInputData(pd)
    nf.SetFeatureAngle(35.0)
    nf.SplittingOn()
    nf.ConsistencyOn()
    nf.AutoOrientNormalsOff()
    nf.Update()
    m = vtk.vtkPolyDataMapper()
    m.SetInputData(nf.GetOutput())
    m.SetResolveCoincidentTopologyToPolygonOffset()
    m.SetRelativeCoincidentTopologyPolygonOffsetParameters(1.5, 1.5)
    a = vtk.vtkActor()
    a.SetMapper(m)
    p = a.GetProperty()
    p.SetColor(*color)
    p.SetOpacity(opacity)
    p.SetAmbient(0.28)
    p.SetDiffuse(0.72)
    p.SetSpecular(0.12)
    p.SetSpecularPower(18)
    return a


def _line_actor(pd, color, width):
    m = vtk.vtkPolyDataMapper()
    m.SetInputData(pd)
    a = vtk.vtkActor()
    a.SetMapper(m)
    p = a.GetProperty()
    p.SetColor(*color)
    p.SetLineWidth(width)
    p.SetLighting(False)
    return a


def render(scene):
    global SS
    W, H = scene.size
    # macOS caps an offscreen window at about the screen's size; keep under it
    SS = min(2.0, 1800.0 / H, 2400.0 / W)
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetSize(int(W * SS), int(H * SS))
    win.AddRenderer(ren)

    view = np.array(scene.view, float)
    view /= np.linalg.norm(view)
    up = np.array(scene.up, float)
    right = np.cross(-view, up)
    right /= np.linalg.norm(right)
    up = np.cross(right, -view)

    surf, ids, lines, sil_inputs = [], [], [], []
    all_pts = []
    labels = []
    for it in scene.items:
        s = it.shape
        if s is None:
            continue
        if scene.section and it.cut:
            s = _section(s, scene.section)
            if s is None:
                continue
        bb = s.BoundBox
        tol = max(0.03, min(0.25, bb.DiagonalLength / 1500.0))
        pts, tris = _tess(s, tol)
        if pts is None:
            continue
        all_pts.append(pts)
        pd = _polydata(pts, tris)
        col = _faded(it.color) if it.ctx else it.color
        a = _actor_for(pd, col, it.opacity)
        surf.append(a)
        ren.AddActor(a)
        # section caps: faces lying in the cut plane, drawn a shade darker
        if scene.section and it.cut:
            (px, py, pz), n = scene.section
            nn = np.array(n, float) / np.linalg.norm(n)
            capf = []
            for f in s.Faces:
                try:
                    if f.Surface.TypeId != "Part::GeomPlane":
                        continue
                    c = f.CenterOfMass
                    fn = f.normalAt(*f.Surface.parameter(c))
                except Exception:
                    continue
                d = (c.x - px) * nn[0] + (c.y - py) * nn[1] + (c.z - pz) * nn[2]
                if abs(d) < 1e-3 and abs(fn.x * nn[0] + fn.y * nn[1] + fn.z * nn[2]) > 0.999:
                    capf.append(f)
            for f in capf:
                cp, ct = _tess(f, tol)
                if cp is None:
                    continue
                cp = cp + nn * 0.02
                ca = _actor_for(_polydata(cp, ct), tuple(x * 0.78 for x in col))
                surf.append(ca)
                ids.append((ca, it.label))
                ren.AddActor(ca)
        ec = (0.55, 0.55, 0.58) if it.ctx else (0.08, 0.08, 0.10)
        edges = _crease_edges(s, tol)
        if edges:
            la = _line_actor(_lines_polydata(edges), ec, 1.6 * SS * it.lw)
            lines.append(la)
            ren.AddActor(la)
        sil_inputs.append((pd, ec, it))
        ids.append((a, it.label))
        if it.label and it.label not in labels:
            labels.append(it.label)

    if scene.text_labels and labels:
        scene.margin = max(scene.margin, min(0.34, (max(len(l) for l in labels) * 15.5 + 50) / W))
    # camera: parallel projection fitted to everything drawn (or to scene.fit)
    P_all = np.array(scene.fit, float) if scene.fit is not None else np.vstack(all_pts)
    xs, ys = P_all @ right, P_all @ up
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    centre = cx * right + cy * up + (P_all @ view).mean() * view
    w_ext, h_ext = xs.max() - xs.min(), ys.max() - ys.min()
    usable_w = W * (1 - 2 * scene.margin)
    usable_h = H * 0.90
    scale = max(w_ext / usable_w, h_ext / usable_h) / scene.zoom   # mm per pixel
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    dist = 3000.0
    cam.SetFocalPoint(*centre)
    cam.SetPosition(*(centre + view * dist))
    cam.SetViewUp(*up)
    cam.SetParallelScale(scale * H / 2)
    cam.SetClippingRange(1.0, 2 * dist)

    for pd, ec, it in sil_inputs:
        sf = vtk.vtkPolyDataSilhouette()
        sf.SetInputData(pd)
        sf.SetCamera(cam)
        sf.SetEnableFeatureAngle(0)
        sf.BorderEdgesOff()
        sf.PieceInvariantOn()
        sf.Update()
        la = _line_actor(sf.GetOutput(), ec, 1.6 * SS * it.lw)
        lines.append(la)
        ren.AddActor(la)

    # explode guide lines, dashed, depth-tested like everything else
    dash_pl = []
    for p0, p1 in scene.dashes:
        p0, p1 = np.array(p0, float), np.array(p1, float)
        L = np.linalg.norm(p1 - p0)
        if L < 1e-6:
            continue
        step = 2.4 * scale * SS * 3
        n = max(1, int(L / step))
        for k in range(n):
            a_ = p0 + (p1 - p0) * (k / n)
            b_ = p0 + (p1 - p0) * ((k + 0.55) / n)
            dash_pl.append([tuple(a_), tuple(b_)])
    if dash_pl:
        da = _line_actor(_lines_polydata(dash_pl), (0.35, 0.45, 0.62), 1.4 * SS)
        lines.append(da)
        ren.AddActor(da)

    light = vtk.vtkLightKit()
    light.SetKeyLightIntensity(0.95)
    light.AddLightsToRenderer(ren)

    win.Render()
    img = _grab(win)
    if img.shape[:2] != (int(H * SS), int(W * SS)):
        raise RuntimeError("%s: rendered %s, wanted %dx%d" % (scene.name, img.shape[:2], W * SS, H * SS))
    out = Image.fromarray(img).resize((W, H), Image.LANCZOS)
    os.makedirs(FIG_DIR, exist_ok=True)
    out = out.quantize(colors=192, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out.save(os.path.join(FIG_DIR, scene.name + ".png"), optimize=True)

    def project(p):
        p = np.array(p, float)
        return (W / 2 + (p @ right - cx) / scale, H / 2 - (p @ up - cy) / scale)

    dims = []
    for p0, p1, text, off in scene.dims:
        dims.append({"a": project(p0), "b": project(p1), "text": text, "off": off})
    compass = None
    if scene.compass is not None:
        d = np.array(scene.compass, float)
        v = np.array([d @ right, -(d @ up)])
        if np.linalg.norm(v) > 1e-6:
            compass = list(v / np.linalg.norm(v))

    # ID pass: flat colours, no lines, to find where each labelled part shows
    for la in lines:
        la.VisibilityOff()
    lab_index = {l: i + 1 for i, l in enumerate(labels)}
    for a, lab in ids:
        k = lab_index.get(lab, 0)
        p = a.GetProperty()
        p.SetLighting(False)
        p.SetColor(*_id_color(k))
        p.SetOpacity(1.0)
    for a in surf:
        if a not in [x for x, _ in ids]:
            a.GetProperty().SetLighting(False)
            a.GetProperty().SetColor(*_id_color(0))
    ren.RemoveAllLights()
    win.Render()
    idimg = _grab(win)
    anchors = _anchors(idimg, labels, W, H)
    win.Finalize()
    return {"name": scene.name, "w": W, "h": H, "labels": labels, "anchors": anchors,
            "dims": dims, "compass": compass, "text": scene.text_labels}


def _id_color(k):
    # well separated flat colours; index 0 = unlabelled but still occluding
    return ((k * 47 % 251) / 255.0, (k * 97 % 241 + 7) / 255.0, ((k * 13) % 200 + 30) / 255.0)


def _grab(win):
    f = vtk.vtkWindowToImageFilter()
    f.SetInput(win)
    f.ReadFrontBufferOff()
    f.Update()
    im = f.GetOutput()
    w, h, _ = im.GetDimensions()
    arr = vns.vtk_to_numpy(im.GetPointData().GetScalars()).reshape(h, w, -1)[:, :, :3]
    return np.flipud(arr).copy()


def _anchors(idimg, labels, W, H):
    out = {}
    pal = np.array([[c * 255 for c in _id_color(k)] for k in range(len(labels) + 1)])
    for i, lab in enumerate(labels, start=1):
        d = np.abs(idimg.astype(np.int32) - pal[i].astype(np.int32)).sum(axis=2)
        mask = d < 6
        if mask.sum() < 20:
            continue
        lbl, n = ndimage.label(mask)
        if n > 1:
            sizes = ndimage.sum(mask, lbl, range(1, n + 1))
            mask = lbl == (1 + int(np.argmax(sizes)))
        dt = ndimage.distance_transform_edt(mask)
        y, x = np.unravel_index(int(np.argmax(dt)), dt.shape)
        out[lab] = (x / SS, y / SS)
    return out


# ------------------------------------------------------------ balloon layout ---
def layout_balloons(fig, r=30):
    """Numbered balloons in a column either side of the drawing, leaders to anchors."""
    W, H = fig["w"], fig["h"]
    left, right = [], []
    for n, lab in enumerate(fig["labels"], start=1):
        a = fig["anchors"].get(lab)
        if a is None:
            continue
        (left if a[0] < W / 2 else right).append([n, lab, a])
    placed = []
    gap = 2 * r + 10
    for side, group in (("l", left), ("r", right)):
        group.sort(key=lambda g: g[2][1])
        ys = [min(max(g[2][1], r + 8), H - r - 8) for g in group]
        for _ in range(200):          # push apart until no two overlap
            moved = False
            for i in range(1, len(ys)):
                if ys[i] - ys[i - 1] < gap:
                    mid = (ys[i] + ys[i - 1]) / 2
                    ys[i - 1], ys[i] = mid - gap / 2, mid + gap / 2
                    moved = True
            ys = [min(max(y, r + 8), H - r - 8) for y in ys]
            if not moved:
                break
        x = r + 12 if side == "l" else W - r - 12
        for (n, lab, a), y in zip(group, ys):
            placed.append({"n": n, "label": lab, "ax": a[0], "ay": a[1], "bx": x, "by": y, "r": r})
    return placed


# ============================================================ from build.py ===
def _from_build(*names):
    """Borrow functions from build.py without running it (it builds on import), so
    the frame layout and the screw lengths here are the build's own."""
    import ast
    with open(os.path.join(HERE, "build.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = dict(globals())
    exec(compile(ast.Module(body=keep, type_ignores=[]), "build.py", "exec"), ns)
    return [ns[n] for n in names]


frame_assembly, build_hardware = _from_build("frame_assembly", "hardware")


# ================================================================= numbers ===
def numbers(parts):
    """Every derived number the text quotes, computed the way the parts are."""
    import re
    n = {"hw": {}, "fits": dict(wind.fit_checks(parts))}
    for item, q, where in build_hardware():
        n["hw"][item] = (q, where)
        m = re.match(r"M4 x (\d+)", item)
        if m:
            n["scr_screw"] = int(m.group(1))
        m = re.match(r"M3 x (\d+) screw \+ nyloc", item)
        if m:
            n["axle"] = int(m.group(1))
        m = re.match(r"M3 x (\d+) screw", item)
        if m and "stops" in where:
            n["stop_len"] = int(m.group(1))
    n["washer_t"] = 1.0                                  # DIN 125 M5 washer
    n["ear_depth"] = P.m3_insert_l + 1.0
    n["standoff_depth"] = P.standoff_h + P.enc_back - 1.2
    n["boss_depth"] = P.m3_insert_l + 0.5
    n["pocket"] = P.brg_od + P.brg_fit
    n["rebate"] = P.vane_pcb_t + P.pcb_standoff - P.wind_gasket_t
    n["ring_h"] = P.pcb_standoff - 0.1
    n["ring_id"] = 2 * (P.wind_r_in + 0.2)
    n["ring_od"] = 2 * (P.vane_pcb_d / 2 + 0.1)
    n["gz"] = P.wind_gland_z
    n["gland_left"] = P.gland_thread - P.gland_wall - P.port_gasket_t
    n["vane_mag_dist"] = (P.rotor_gap + P.wind_lid_t + P.pcb_standoff + P.vane_pcb_t / 2
                          + P.mag_d / 2)
    n["anemo_mag_dist"] = P.lip_h + P.wind_floor + 0.4 + P.reed_d / 2 + P.mag_d / 2
    n["rain_rest"] = math.hypot(P.rain_reed_gap, P.rain_mag_travel)
    n["hub_nut_top"] = 3.5
    n["hub_bore"] = P.shaft_in_hub + 1.5
    n["vane_head_drop"] = P.shim_h + P.shaft_head_h
    vr = wind.vane_rotor_use()
    cg = vr.CenterOfGravity
    n["vane_mass"] = vr.Volume / 1000.0 * 1.07
    n["vane_cg"] = cg.x
    n["ballast_x"] = P.vane_nose - 17.0
    n["ballast"] = n["vane_mass"] * cg.x / n["ballast_x"] if cg.x > 0 else 0.0
    n["ballast_free"] = 25.0 - P.vane_boom
    n["ballast_nuts"] = int(n["ballast_free"] // P.m5_nut_h)
    n["scr_seat"] = P.scr_base_t + P.scr_plates * P.scr_pitch + 3.0
    n["scr_nut_proud"] = P.scr_nut_h - P.scr_nut_pocket
    n["scr_need"] = n["scr_seat"] + n["scr_nut_proud"]
    n["scr_height"] = screen.height()
    n["stop_proud"] = n.get("stop_len", 16) - (P.rain_stop_boss_h + P.rain_base_t)
    n["stop_side"] = P.rain_stop_x * math.sin(math.radians(45)) - 1.5 - P.profile / 2
    n["ports"] = list(zip([p[0] for p in P.enc_ports], [p[1] for p in P.enc_ports],
                          enclosure.port_positions()))
    o = P.enc_tab_len / 2 + 0.5
    n["tab_pitch"] = P.enc_in_h + 2 * P.enc_wall + 2 * o
    n["sky_rim_above_vane"] = P.sky_rim_low - (P.wind_lid_t + P.wind_gasket_t + P.vane_top)
    n["vane_tail_gap"] = P.sky_head_xmin - P.vane_tip_x
    n["solar_gap"] = 6.0                                  # frame_assembly(): tab end to foot
    n["groove_w"] = P.scr_pcb_t + 0.3
    n["ridge_h"] = P.enc_groove_d - P.gasket_h + P.gasket_squeeze
    n["wind_top_drop"] = P.wind_gasket_t
    return n


# ============================================================ hardware list ===
def catalogue(n):
    """key -> (name in the guide, text that finds its line in BOM.md, or None)."""
    b = "%g x %g x %g" % (P.brg_id, P.brg_od, P.brg_w)
    gx = {"ENV": "gx16_8", "SOLAR": "gx12_2", "RAIN": "gx12_3", "WIND": "gx16_5", "SKY": "gx12_4"}
    c = {
        "brg": ("Ball bearing %s, shielded%s" % (b, " (625ZZ)" if b == "5 x 16 x 5" else ""), b),
        "shaft": ("M5 x %g socket head (rotor shaft)" % P.shaft_len,
                  "M5 x %g socket head" % P.shaft_len),
        "m5x25": ("M5 x 25 socket head (vane ballast)", "M5 x 25 socket head"),
        "m5x12": ("M5 x 12 button head", "M5 x 12 button head"),
        "m5x10": ("M5 x 10 button head", "M5 x 10 button head"),
        "m5x8": ("M5 x 8 button head", "M5 x 8 button head"),
        "m5nut": ("M5 hex nut", "M5 hex nut"),
        "washer": ("M5 washer", "M5 washer"),
        "tnut": ("M5 profile nut for 2020", "M5 profile nut"),
        "m3x8": ("M3 x 8 socket head", "M3 x 8 socket head"),
        "m3x10": ("M3 x 10 socket head", "M3 x 10 socket head"),
        "m3x6": ("M3 x 6 socket head", "M3 x 6 socket head"),
        "m3x16": ("M3 x %d socket head (bucket stops)" % n.get("stop_len", 16),
                  "M3 x %d socket head" % n.get("stop_len", 16)),
        "axle": ("M3 x %d socket head (bucket axle)" % n["axle"], "M3 x %d socket head" % n["axle"]),
        "nyloc": ("M3 nyloc nut", "M3 nyloc"),
        "insert": ("M3 x %g brass heat-set insert, OD 4.2" % P.m3_insert_l,
                   "M3 x %g brass heat-set insert" % P.m3_insert_l),
        "mag6": ("Disc magnet %g x %g" % (P.mag_d, P.mag_t), "disc %g x %g" % (P.mag_d, P.mag_t)),
        "mag4": ("Disc magnet %g x %g" % (P.rain_mag_d, P.rain_mag_t),
                 "disc %g x %g" % (P.rain_mag_d, P.rain_mag_t)),
        "m4": ("M4 x %d socket head (screen clamp)" % n["scr_screw"], "M4 x %d" % n["scr_screw"]),
        "m4nut": ("M4 hex nut", "M4 hex nut"),
        "gland": ("PG7 cable gland", "PG7"),
        "gx16_8": ("GX16 8-pin socket + plug (ENV)", "GX16 8-pin"),
        "gx16_5": ("GX16 5-pin socket + plug (WIND)", "GX16 5-pin"),
        "gx12_2": ("GX12 2-pin socket + plug (SOLAR)", "GX12 2-pin"),
        "gx12_3": ("GX12 3-pin socket + plug (RAIN)", "GX12 3-pin"),
        "gx12_4": ("GX12 4-pin socket + plug (SKY)", "GX12 4-pin"),
        "bracket": ("2020 right-angle connector", "right-angle connector"),
        "foam": ("3 mm closed-cell foam, 40 x 12 mm", "closed-cell foam"),
        "epoxy": ("Two-part epoxy (for the magnets)", "epoxy"),
        "silica": ("Silica gel sachet", "Silica gel"),
        "ipa": ("Isopropyl alcohol, 99% (cleans the cup bearings)", "Isopropyl alcohol"),
        "oil": ("Light oil: sewing-machine, clock or instrument", "Light oil"),
        "silicone": ("Neutral-cure silicone", "silicone"),
        "ties": ("UV-stable black cable ties", "cable ties"),
        "cable5": ("Shielded 5-core outdoor cable (wind), mast height + 0.5 m", "Shielded 5-core"),
        "cable8": ("8-core cable (screen), about 1.5 m", "8-core cable (screen"),
        "cable4": ("4-core cable (sky pod), about 1.5 m", "4-core cable"),
        "cable3": ("3-core cable (rain), about 1.5 m", "3-core"),
        "cable2": ("2-core cable (solar), about 1.5 m", "2-core"),
        # already owned: deliberately not in BOM.md
        "reed": ("Reed switch, %g mm glass" % (P.reed_l - 0.5), None),
        "vanepcb": ("Wind-vane PCB, %g mm disc" % P.vane_pcb_d, None),
        "boardA": ("Board A", None),
        "boardB": ("Board B (sensor carrier, %g x %g)" % (P.scr_pcb_w, P.scr_pcb_h), None),
        "pms": ("PMS7003 particle sensor", None),
        "ltg": ("DFRobot SEN0290 lightning module", None),
        "mlx": ("MLX90614 breakout (GY-906)", None),
        "ant": ("868 MHz right-angle stubby antenna, SMA", None),
        "cell": ("32700 cell", None),
        "panel": ("Solar panel, up to %g x %g mm" % (P.panel_l, P.panel_w), None),
    }
    return c, gx


OWNED = ("reed", "vanepcb", "boardA", "boardB", "pms", "ltg", "mlx", "ant", "cell", "panel")


def read_bom():
    """Rows of BOM.md tables that have a Need column: [(item, need, order)]."""
    rows = []
    path = os.path.join(HERE, "BOM.md")
    if not os.path.exists(path):
        return rows
    cols = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                cols = None
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cols is None:
                cols = {name: i for i, name in enumerate(cells)}
                continue
            if set(line) <= set("|-: "):
                continue
            if "Need" not in cols:
                continue
            item = cells[0]
            need = cells[cols["Need"]] if cols["Need"] < len(cells) else ""
            order = cells[cols["Order"]] if "Order" in cols and cols["Order"] < len(cells) else ""
            rows.append((item, need, order))
    return rows


# =================================================================== steps ===
class Step:
    def __init__(self, title, scene=None, printed=(), hw=(), do=(), nums=(), flags=(),
                 caption=None, bench=()):
        self.title = title
        self.scene = scene        # Scene, rendered to docs/assembly/<name>.png
        self.printed = printed    # [(part name as in out/parts.json, qty)]
        self.hw = hw              # [(catalogue key, qty)]
        self.do = do              # instructions (HTML)
        self.nums = nums          # [(what, value)] numbers that matter while doing it
        self.flags = flags        # things the model leaves open, or gets wrong (HTML)
        self.caption = caption
        self.bench = bench        # measurements or checks only the real parts can answer (HTML)


def c(name):
    return "<code>%s</code>" % html.escape(name)


def mm(v, nd=1):
    return fmt(v, nd) + "&nbsp;mm"


SECTION_Y = ((0, 0, 0), (0, -1, 0))      # keep the +Y half, look from -Y


def _box_pts(x0, x1, y0, y1, z0, z1):
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def wind_steps(p, n):
    pl = dict(wind.place(p))
    h, g, lt = P.wind_body_h, P.wind_gasket_t, P.wind_lid_t
    hl = h + g
    roof = hl + lt
    B = hw_bearing(P.brg_id, P.brg_od, P.brg_w)
    sep = P.brg_w + P.brg_sep
    shaft = hw_shcs(5, P.shaft_len, P.shaft_head_d, P.shaft_head_h)
    ears = wind._ear_xy()
    body = pl["wind_body"]
    ins = [put(hw_insert(), (x, y, h)) for x, y in ears]
    b_lo, b_hi = mv(B, 0, 0, 0), mv(B, 0, 0, sep)
    spc = mv(wind.spacer(), 0, 0, P.brg_w - 0.15)
    body_done = ([Item(body, "white", ctx=True)] + [Item(s, "brass", ctx=True) for s in ins]
                 + [Item(b_lo, "steel", ctx=True), Item(b_hi, "steel", ctx=True),
                    Item(spc, "white", ctx=True)])
    # reed (anemometer): glass in the floor channel at -X
    glass, leads = hw_reed(P.reed_l - 0.5, 2.0, 9.0)
    rz_ = P.wind_floor + 0.4 + 1.1
    reed = [mv(glass, -P.anemo_mag_r, 0, rz_), mv(leads, -P.anemo_mag_r, 0, rz_)]
    # cup rotor, in place
    zh = -(P.cup_hub_h + P.lip_h)
    cup_mag = put(hw_magnet(P.mag_d, P.mag_t), (-P.anemo_mag_r, 0, -P.lip_h - 3.3), (1, 0, 0))
    hub_nz = zh + (P.cup_hub_h - 3.5 - (P.m5_nut_h + 0.4)) + 0.2
    cup_nut = mv(hw_nut(P.m5_nut_af, P.m5_nut_h, 5.0), 0, 0, hub_nz)
    arms = [pl["cup_arm_%d" % i] for i in (1, 2, 3)]
    cap_z = zh - 2.4
    cap_scr = [put(hw_shcs(3, 10), pol(10.0, a, cap_z), (0, 0, -1)) for a in (0, 120, 240)]
    rotor = ([pl["cup_hub"], pl["cup_hub_cap"]] + arms, [cup_mag, cup_nut] + cap_scr)
    cup_shim = mv(wind.shim(), 0, 0, P.tower_h)
    cup_shaft = put(shaft, (0, 0, P.tower_h + P.shim_h))

    def rotor_items(dz=0.0, ctx=True, label=None):
        out = [Item(mv(s, 0, 0, dz), "accent", label, ctx=ctx) for s in rotor[0]]
        out += [Item(mv(cup_mag, 0, 0, dz), "magnet", ctx=ctx),
                Item(mv(cup_nut, 0, 0, dz), "steel", ctx=ctx)]
        out += [Item(mv(s, 0, 0, dz), "steel", ctx=ctx, cut=False) for s in cap_scr]
        return out

    # lid and vane, in place
    lid = pl["wind_lid"]
    l_lo, l_hi = mv(B, 0, 0, hl), mv(B, 0, 0, hl + sep)
    l_spc = mv(wind.spacer(), 0, 0, hl + P.brg_w - 0.15)
    vane = pl["vane_rotor"]
    vz = roof                                   # vane frame z = 0
    _g, ht, zc, *_r = wind._vane_dims()
    vane_mag = put(hw_magnet(P.mag_d, P.mag_t), (P.vane_reed_r, 0, vz + P.rotor_gap + 0.3 + P.mag_d / 2),
                   (1, 0, 0))
    vane_nut = mv(rz(hw_nut(P.m5_nut_af, P.m5_nut_h, 5.0), 0), 0, 0, vz + zc + 3.5 + 0.2)
    bx = -n["ballast_x"]
    spine_lo = vz + P.vane_top - P.vane_boom
    ball_scr = put(hw_shcs(5, 25), (bx, 0, vz + P.vane_top))
    ball_nuts = [mv(hw_nut(P.m5_nut_af, P.m5_nut_h, 5.0), bx, 0, spine_lo - P.m5_nut_h * (k + 1))
                 for k in range(n["ballast_nuts"])]
    vane_shim = mv(wind.shim(), 0, 0, hl - P.shim_h)
    vane_shaft = put(shaft, (0, 0, hl - P.shim_h), (0, 0, -1))
    vane_set = [vane, vane_mag, vane_nut, ball_scr] + ball_nuts
    vane_cols = ["accent", "magnet", "steel", "steel"] + ["steel"] * len(ball_nuts)
    pcb = dict(wind.reference())["vane_pcb"]
    ring = pl["wind_pcb_ring"]
    gasket = pl["tpu_wind_lid_gasket"]
    lid_scr = [put(hw_shcs(3, 8), (x, y, roof)) for x, y in ears]
    housing_fit = _box_pts(-45, 45, -42, 42, -2, h + 4)

    steps = {}
    # ---------------------------------------------------------------- housing
    ex = 16
    items = [Item(body, "white", "wind_body")]
    items += [Item(mv(s, 0, 0, ex), "brass", "M3 heat-set insert") for s in ins]
    steps["housing"] = [Step(
        "Heat-set inserts in the housing ears",
        Scene("wind-01-inserts", items, view=(1, -1.3, 0.9), section=SECTION_Y,
              dashes=[((x, y, h - n["ear_depth"]), (x, y, h + ex)) for x, y in ears]),
        printed=[("wind_body", 1)], hw=[("insert", 3)],
        do=["Press one insert into each of the three ears on the housing rim, from the top, "
            "with a soldering iron and an insert tip. Keep it square and stop when its top face "
            "is flush with the rim.",
            "Let each one cool before the next. The lid screws pull on these."],
        nums=[("Insert pilot", "&Oslash;%s, %s deep" % (fmt(P.m3_insert_d), mm(n["ear_depth"]))),
              ("Insert length", "%s, so %s of hole is left under it" %
               (mm(P.m3_insert_l), mm(n["ear_depth"] - P.m3_insert_l))),
              ("Ears", "radius %s, at %s&deg;" % (mm(P.wind_ear_r), ", ".join(
                  fmt(a, 0) for a in P.wind_ear_angles)))]),
    ]
    items = body_done[:1] + body_done[1:4]
    items += [Item(mv(b_lo, 0, 0, -22), "steel", "bearing"),
              Item(mv(b_hi, 0, 0, 42), "steel", "bearing"),
              Item(mv(spc, 0, 0, 24), "white", "wind_spacer")]
    steps["housing"].append(Step(
        "Bearings and spacer in the floor tower",
        Scene("wind-02-bearings", items, view=(1, -1.3, 0.9), section=SECTION_Y,
              dashes=[((0, 0, -30), (0, 0, h + 52))],
              fit=_box_pts(-40, 45, -40, 40, -26, h + 50)),
        printed=[("wind_spacer", 1)], hw=[("brg", 2), ("ipa", 1), ("oil", 1)],
        do=["These two carry the cups. They arrive packed with grease, which is enough to stall a "
            "light breeze, so clean them before they go in. The vane's pair (step 3.1) can stay as "
            "they come.",
            "Leave the shields on. A ZZ shield does not touch the inner race, so solvent gets in "
            "round it; prising one off usually bends it, and outdoors it keeps the grit out.",
            "Thread each bearing onto an M5 screw and spin it under 99% isopropyl alcohol (naphtha "
            "also works) in a small jar. Change the alcohol two or three times, until it stays clear "
            "and the bearing runs on instead of slowing at once. Not 70%: its water rusts the races.",
            "Let them dry for 15 to 30 minutes, or under a hairdryer on low. If you use compressed "
            "air, hold the inner race: a dry bearing spun up by air wears its own races.",
            "Oil them straight away, before the air does its work: one small drop of light oil on each "
            "side, a spin to spread it, the excess wiped off. More oil is only more drag and more dust.",
            "Press the first bearing into the pocket that opens under the floor, until its outer "
            "race stops on the shoulder inside the tower.",
            "Drop a %s into the tower from above. It stands on the lower bearing's inner race." % c("wind_spacer"),
            "Press the second bearing in from above, again down to the shoulder.",
            "Push on the outer race only: a socket the size of the race works. Pressing on the "
            "inner race or the shields damages the bearing.",
            "Both should spin freely. If a pocket is too loose or too tight, change "
            "<code>brg_fit</code> in <code>params.py</code> and reprint; this is why the README says "
            "to print %s first and check the fit." % c("wind_lid")],
        nums=[("Bearing pocket", "&Oslash;%s for a %s bearing (%s over), %s deep" %
               (fmt(n["pocket"], 2), mm(P.brg_od), mm(P.brg_fit, 2), mm(P.brg_w))),
              ("A clean, oiled bearing", "runs for several seconds after a flick on a screw, smooth, "
               "not gritty"),
              ("Shoulder between the pockets", "&Oslash;%s" % mm(P.tower_bore, 2)),
              ("Bearing faces apart", mm(P.brg_sep)),
              ("Spacer", "&Oslash;%s outside, &Oslash;%s bore, %s long" %
               (fmt(P.race_od), fmt(P.brg_id + 0.3), mm(P.brg_sep + 0.3)))]))
    items = body_done[:]
    items += [Item(mv(reed[0], 0, 0, 12), "glass", "reed switch"),
              Item(mv(reed[1], 0, 0, 12), "steel")]
    steps["housing"].append(Step(
        "Anemometer reed switch",
        Scene("wind-03-reed", items, view=(0.35, -0.75, 1.0),
              dashes=[((-P.anemo_mag_r, 0, rz_), (-P.anemo_mag_r, 0, rz_ + 12))],
              fit=housing_fit),
        hw=[("reed", 1), ("silicone", 1)],
        do=["Solder two wires to the reed switch. Bend its leads well away from the glass, never "
            "at the seal.",
            "Lay it in the channel on the housing floor, on the side away from the arm, between the "
            "two cradles, with the glass centred %s from the axis and the leads toward the wall." %
            mm(P.anemo_mag_r),
            "Hold it down with a dab of neutral-cure silicone on the leads, not on the glass.",
            "Lead the wires up the wall to where the vane PCB (Board D) will sit: they go to its "
            "anemometer reed pads, SW9 in <code>hardware/boards/board-d-wind.md</code>."],
        nums=[("Reed centre from the axis", mm(P.anemo_mag_r)),
              ("Channel", "%s wide, open on top, its floor %s above the housing floor" %
               (mm(P.reed_d + 0.3), mm(0.4))),
              ("Magnet to reed, through the floor", mm(n["anemo_mag_dist"]) + " centre to centre")]))
    gx0 = P.wind_r_out + 2.5
    gland = put(hw_gland(), (gx0 + P.port_gasket_t, 0, n["gz"]), (1, 0, 0))
    gwash = put(enclosure.washer(P.gland_d, P.gland_flange), (gx0, 0, n["gz"]), (1, 0, 0))
    gnut = put(hw_gland_nut(), (P.wind_r_in - 4.0, 0, n["gz"]), (1, 0, 0))
    items = body_done[:]
    items += [Item(mv(gland, 26, 0, 0), "white", "PG7 gland"),
              Item(mv(gwash, 12, 0, 0), "tpu", "tpu_washer_gland"),
              Item(mv(gnut, -12, 0, 0), "white", "gland locknut")]
    steps["housing"].append(Step(
        "Cable gland",
        Scene("wind-04-gland", items, view=(0.55, -1, 0.45), section=SECTION_Y,
              dashes=[((P.wind_r_in - 18, 0, n["gz"]), (gx0 + 40, 0, n["gz"]))],
              fit=_box_pts(-12, 75, -30, 30, -2, h + 4)),
        printed=[("tpu_washer_gland", 1)], hw=[("gland", 1), ("cable5", 1)],
        do=["The gland goes in the wall that faces the mast, between the arm's two rails.",
            "From outside: the TPU washer, then the gland through the wall. From inside: its locknut, "
            "flat against the seat cut into the wall.",
            "Feed the 5-core cable in now and leave the dome nut loose. Tighten it after the lid "
            "is on (step 4.2)."],
        nums=[("Hole", "&Oslash;%s, centre %s above the housing's underside" %
               (fmt(P.gland_d), mm(n["gz"], 1))),
              ("TPU washer", "&Oslash;%s outside, &Oslash;%s hole, %s thick" %
               (fmt(P.gland_flange + 1.0), fmt(P.gland_d + 0.2), mm(P.port_gasket_t))),
              ("Wall under the flange", "%s (a flat seat inside takes the locknut); %s with the washer" %
               (mm(P.gland_wall), mm(P.gland_wall + P.port_gasket_t))),
              ("Thread left for the locknut", "%s of a %s PG7 thread (Flyrobo lists 9)" %
               (mm(n["gland_left"]), mm(P.gland_thread)))]))

    # ------------------------------------------------------------ cup rotor
    hub = pl["cup_hub"]
    items = [Item(hub, "accent", "cup_hub"),
             Item(mv(cup_mag, 0, 0, 16), "magnet", "magnet %g x %g" % (P.mag_d, P.mag_t)),
             Item(mv(cup_nut, 30, 0, 0), "steel", "M5 nut")]
    steps["cups"] = [Step(
        "Magnet and nut into the hub",
        Scene("cups-01-hub", items, view=(0.9, -1.1, 1.0),
              dashes=[((-P.anemo_mag_r, 0, -P.lip_h - 3.3), (-P.anemo_mag_r, 0, 14)),
                      ((0, 0, hub_nz + 2), (30, 0, hub_nz + 2))]),
        printed=[("cup_hub", 1)], hw=[("mag6", 1), ("m5nut", 1), ("epoxy", 1)],
        do=["The hub's top is the face with the small raised lip round the bore.",
            "Push a %s magnet into the slot in that face, standing on its edge, flat faces toward "
            "and away from the axis. Either pole outward works: a reed closes for both." %
            ("%g x %g" % (P.mag_d, P.mag_t)),
            "Fix the magnet with a drop of epoxy: its slot is a clearance fit.",
            "Slide an M5 nut into the slot in the hub's side until it sits over the bore. Its flats "
            "run along the slot walls."],
        nums=[("Magnet slot", "%s across, %s along the radius, %s deep, at radius %s" %
               (fmt(P.mag_d + 0.2), fmt(P.anemo_mag_len), fmt(P.mag_d + 0.3), mm(P.anemo_mag_r))),
              ("Nut slot", "%s wide, %s tall, its top %s below the hub's top face" %
               (fmt(P.m5_nut_af + 0.3), fmt(P.m5_nut_h + 0.4), mm(3.5)))])]
    ex = 24
    items = [Item(hub, "accent", ctx=True), Item(cup_mag, "magnet", ctx=True)]
    items += [Item(mv(a, 0, 0, -ex), "accent", "cup_arm") for a in arms]
    items += [Item(mv(pl["cup_hub_cap"], 0, 0, -ex - 16), "accent", "cup_hub_cap")]
    items += [Item(mv(s, 0, 0, -ex - 30), "steel", "M3 x 10") for s in cap_scr]
    steps["cups"].append(Step(
        "Arms and cap (seen from below)",
        Scene("cups-02-arms", items, view=(0.9, -1.1, -0.85),
              dashes=[(pol(10, a, zh), pol(10, a, cap_z - ex - 40)) for a in (0, 120, 240)]),
        printed=[("cup_arm", 3), ("cup_hub_cap", 1)], hw=[("m3x10", 3)],
        do=["Turn the hub over. Push each %s straight up into a slot from the hub's underside. "
            "The hook on the arm's inner end only goes in one way round and only from below; it "
            "will not slide in from the side." % c("cup_arm"),
            "All three cups then face the same way round.",
            "Lay %s over the slots and drive three M3 x 10 through it into the pilot holes. They cut "
            "their own thread: go slowly and stop when the cap is tight." % c("cup_hub_cap")],
        nums=[("Pilot holes", "&Oslash;%s, 9 mm deep, at radius %s" % (fmt(P.m3_tap_d), mm(10))),
              ("Thread in the hub", "%s (10 mm screw, %s cap)" % (mm(10 - 2.4), mm(2.4))),
              ("Cups sweep", "radius %s" % mm(P.cup_sweep_r))]))
    items = body_done[:] + [Item(s, "glass", ctx=True) for s in reed[:1]]
    items += [Item(mv(cup_shim, 0, 0, 22), "white", "wind_shim"),
              Item(mv(cup_shaft, 0, 0, 34), "steel", "M5 x %g shaft" % P.shaft_len, cut=False)]
    items += rotor_items(-26, ctx=False, label="cup rotor (2.2)")
    steps["cups"].append(Step(
        "Hang the rotor from the housing",
        Scene("cups-03-shaft", items, view=(0.35, -1, 0.3), section=SECTION_Y,
              dashes=[((0, 0, -60), (0, 0, P.tower_h + 80))],
              fit=_box_pts(-90, 90, -10, 10, -70, P.tower_h + 70)),
        printed=[("wind_shim", 1)], hw=[("shaft", 1)],
        do=["Put a %s on an M5 x %g and drop the screw into the floor tower from inside the "
            "housing. The shim sits on the upper bearing's inner race." % (c("wind_shim"), P.shaft_len),
            "From below, push the cup rotor onto the screw, lip first, until the lip meets the lower "
            "bearing's inner race.",
            "Hold the rotor and turn the screw from inside with a 4 mm hex key until it catches the "
            "nut and pulls the stack together. Stop at snug: shim, both inner races, spacer and hub "
            "lip clamped into one piece.",
            "Spin it. It should coast to a stop, not stop dead. If it stops dead, the bearings still "
            "hold their grease (step 1.2) or the screw is past snug."],
        nums=[("Shim", "&Oslash;%s, &Oslash;%s bore, %s thick" %
               (fmt(P.race_od), fmt(P.brg_id + 0.3), mm(P.shim_h))),
              ("Screw past the bearing stack", "%s, into a %s bore through the nut" %
               (mm(P.shaft_in_hub), mm(n["hub_bore"]))),
              ("Cup tops below the housing floor", mm(P.cup_floor_gap))]))

    # ----------------------------------------------------------------- vane
    lid_items = [Item(lid, "white", ctx=True), Item(l_lo, "steel", ctx=True),
                 Item(l_hi, "steel", ctx=True), Item(l_spc, "white", ctx=True)]
    items = [Item(lid, "white", "wind_lid"),
             Item(mv(l_lo, 0, 0, -20), "steel", "bearing"),
             Item(mv(l_hi, 0, 0, 30), "steel", "bearing"),
             Item(mv(l_spc, 0, 0, 16), "white", "wind_spacer")]
    steps["vane"] = [Step(
        "Bearings and spacer in the lid",
        Scene("vane-01-lid", items, view=(1, -1.3, 0.9), section=SECTION_Y,
              dashes=[((0, 0, hl - 26), (0, 0, hl + sep + 40))]),
        printed=[("wind_lid", 1), ("wind_spacer", 1)], hw=[("brg", 2)],
        do=["The same as step 1.2: one bearing into the pocket that opens under the lid, the "
            "spacer, then the second bearing into the top of the tower. Outer races only, each "
            "pushed to the shoulder.",
            "These two can keep their factory grease: the README only asks for the cup bearings to "
            "be cleaned.",
            "The arrow engraved on the lid's top points along the arm, at the mast. With the mast "
            "turned as in step 10.5 (wind arm on the south face) that is north."],
        nums=[("Pockets and spacer", "as step 1.2")])]
    items = [Item(vane, "accent", "vane_rotor"),
             Item(mv(vane_mag, 0, 0, -16), "magnet", "magnet %g x %g" % (P.mag_d, P.mag_t)),
             Item(mv(vane_nut, 0, 32, 0), "steel", "M5 nut (hub)"),
             Item(mv(ball_scr, 0, 0, 18), "steel", "M5 x 25 ballast screw")]
    items += [Item(mv(s, 0, 0, -16 - 3 * k), "steel", "M5 nuts (ballast)")
              for k, s in enumerate(ball_nuts)]
    steps["vane"].append(Step(
        "Prepare the vane rotor (seen from below)",
        Scene("vane-02-rotor", items, view=(0.55, 1.15, -0.6),
              dashes=[((P.vane_reed_r, 0, vz - 12), (P.vane_reed_r, 0, vz + 5)),
                      ((0, 2, vz + zc + 5.9), (0, 34, vz + zc + 5.9)),
                      ((bx, 0, spine_lo - 40), (bx, 0, vz + P.vane_top + 25))]),
        printed=[("vane_rotor", 1)],
        hw=[("mag6", 1), ("m5nut", 1 + n["ballast_nuts"]), ("m5x25", 1), ("epoxy", 1)],
        bench=[],
        do=["Push a %s magnet into the slot under the flange on the tail side, standing on edge, "
            "flat faces along the radius, as in the cup hub." % ("%g x %g" % (P.mag_d, P.mag_t)),
            "Fix the magnet with a drop of epoxy.",
            "Slide an M5 nut into the slot in the side of the hub, flats along the slot walls, until it "
            "sits over the bore.",
            "Put the M5 x 25 down through the slot in the nose, head on top of the spine, and run "
            "M5 nuts onto it under the spine. Leave them loose: they are set in step 3.4."],
        nums=[("Magnet", "radius %s, under the tail side" % mm(P.vane_reed_r)),
              ("Ballast slot", "&Oslash;%s, centres 12 mm apart, centre %s from the axis" %
               (fmt(P.m5_clear), mm(n["ballast_x"]))),
              ("Room for ballast nuts", "%s of screw under the %s spine: %d nuts" %
               (mm(n["ballast_free"]), mm(P.vane_boom), n["ballast_nuts"]))],
        flags=[f for f in ["<b>The hub nut does not fit.</b> <code>build.py</code>'s fit check finds "
               "%.1f mm&sup3; of plastic in its way; fix <code>vane_rotor_use()</code> in "
               "<code>wind.py</code> before printing %s." % (v, c("vane_rotor"))
               for v in [n["fits"].get("vane_rotor: M5 nut slides into its slot and over the bore", 0.0)]
               if v > 0.5]]))
    items = lid_items[:]
    items += [Item(mv(s, 0, 0, 28), col, "vane_rotor (3.2)" if k == 0 else None)
              for k, (s, col) in enumerate(zip(vane_set, vane_cols))]
    items += [Item(mv(vane_shim, 0, 0, -14), "white", "wind_shim"),
              Item(mv(vane_shaft, 0, 0, -30), "steel", "M5 x %g shaft" % P.shaft_len, cut=False)]
    steps["vane"].append(Step(
        "Vane onto the lid",
        Scene("vane-03-shaft", items, view=(0.35, -1, 0.25), section=SECTION_Y,
              dashes=[((0, 0, hl - 80), (0, 0, roof + 110))],
              fit=_box_pts(-75, 135, -10, 10, hl - 75, roof + 100)),
        printed=[("wind_shim", 1)], hw=[("shaft", 1)],
        do=["Put a %s on the second M5 x %g and push it up through the lid's tower from underneath." %
            (c("wind_shim"), P.shaft_len),
            "Set the vane over the tower so its lip meets the upper bearing's inner race.",
            "Hold the vane and turn the screw from under the lid with a 4 mm hex key until it is "
            "snug in the hub nut.",
            "The vane must turn freely without touching the lid."],
        nums=[("Screw head below the lid's underside", "%s (shim %s + head %s)" %
               (mm(n["vane_head_drop"]), fmt(P.shim_h), fmt(P.shaft_head_h))),
              ("Screw into the vane hub", mm(P.shaft_in_hub)),
              ("Running gap, vane to lid", mm(P.rotor_gap)),
              ("Fin above the lid", mm(P.vane_fin_clear))]))
    lid_set = [lid, l_lo, l_hi]
    turn = lambda s: ry(mv(s, 0, 0, -roof), 90)
    spin = lambda s: turn(rz(s, 35))
    items = [Item(turn(s), "white", "wind_lid" if k == 0 else None, ctx=k > 0)
             for k, s in enumerate(lid_set)]
    items += [Item(spin(s), col, ("vane_rotor" if k == 0 else
                                  "ballast screw and nuts" if k >= 3 else None))
              for k, (s, col) in enumerate(zip(vane_set, vane_cols))]
    steps["vane"].append(Step(
        "Balance the vane",
        Scene("vane-04-balance", items, view=(0.35, -1, 0.25),
              dashes=[((-30, 0, 0), (90, 0, 0))]),
        hw=[],
        do=["Hold the lid with the shaft horizontal, as drawn. A balanced vane stays at whatever "
            "angle you leave it; an unbalanced one swings round until its heavy end is down.",
            "Add or take off nuts on the ballast screw, or slide it along its slot, until the vane "
            "stays put. Then lock the nuts against the spine."],
        nums=[("Model's estimate", "about %s g at the slot, for a solid print (rotor %s g solid, "
               "centre of gravity %s toward the tail)" %
               (fmt(n["ballast"], 0), fmt(n["vane_mass"], 0), mm(n["vane_cg"]))),
              ("What fits", "the M5 x 25 and %d nuts" % n["ballast_nuts"])],
        bench=["The %s g estimate is for solid plastic. A rotor printed at 15 to 20 %% infill is "
               "lighter, so expect to need less. If %d nuts are not enough, an M5 x 30 hangs clear of "
               "the lid (the slot is outside the lid's %s radius)." % (fmt(n["ballast"], 0),
                                                                       n["ballast_nuts"], mm(P.wind_lid_r))]))

    # --------------------------------------------------------------- closing
    done = body_done[:] + [Item(reed[0], "glass", ctx=True)] + rotor_items(0) + \
        [Item(cup_shim, "white", ctx=True), Item(cup_shaft, "steel", ctx=True)]
    items = done[:]
    items += [Item(mv(pcb, 0, 0, 20), "pcb", "wind-vane PCB"),
              Item(mv(ring, 0, 0, 36), "white", "wind_pcb_ring")]
    steps["close"] = [Step(
        "Vane PCB and its ring",
        Scene("close-01-pcb", items, view=(0.8, -1.1, 1.15),
              fit=_box_pts(-45, 45, -42, 42, -10, h + 40)),
        printed=[("wind_pcb_ring", 1)], hw=[("vanepcb", 1)],
        do=["Solder the floor reed's two wires to the PCB's anemometer reed pads (SW9), and the "
            "5-core cable to its J1 pads: 1 VBAT, 2 GND, 3 vane analog, 4 anemometer pulse, 5 shield "
            "(<code>hardware/boards/board-d-wind.md</code>). The same numbers go on the GX16-5 plug at "
            "the box end.",
            "Lay the PCB in the pocket at the top of the housing so its rim rests on the ledge, "
            "then lay %s on top of it." % c("wind_pcb_ring"),
            "Either face can go up: the reeds lie in slots through the board, level with its middle, "
            "and the room above it is for solder joints.",
            "Turn the PCB so its N reed points along the arm, toward the mast, where the lid's arrow "
            "will point. Nothing keys the angle, so mark the N reed on the PCB and the housing rim."],
        nums=[("PCB", "&Oslash;%s in a &Oslash;%s pocket; the ledge carries %s of its rim" %
               (fmt(P.vane_pcb_d, 2), fmt(2 * P.wind_r_pcb, 2), mm(P.pcb_edge_grip))),
              ("Pocket depth", mm(n["rebate"])),
              ("Ring", "&Oslash;%s outside, &Oslash;%s inside, %s thick; it stops %s short of the "
               "lid, so the lid clamps the gasket, not the PCB" %
               (fmt(n["ring_od"], 1), fmt(n["ring_id"], 1), mm(n["ring_h"]), mm(0.1))),
              ("Room above the PCB", "%s, for solder joints" % mm(P.pcb_standoff))])]
    items = done[:] + [Item(pcb, "pcb", ctx=True), Item(ring, "white", ctx=True)]
    lift = 30
    items += [Item(mv(gasket, 0, 0, 12), "tpu", "tpu_wind_lid_gasket")]
    items += [Item(mv(s, 0, 0, lift), col, "wind_lid with vane (3.3)" if k == 0 else None,
                   ctx=k > 0)
              for k, (s, col) in enumerate(zip([lid, l_lo, l_hi, l_spc, vane_shim, vane_shaft] + vane_set,
                                               ["white", "steel", "steel", "white", "white", "steel"]
                                               + vane_cols))]
    items += [Item(mv(s, 0, 0, lift + 26), "steel", "M3 x 8") for s in lid_scr]
    steps["close"].append(Step(
        "Gasket and lid",
        Scene("close-02-lid", items, view=(0.9, -1.2, 0.8),
              dashes=[((x, y, h - 6), (x, y, roof + lift + 30)) for x, y in ears],
              fit=_box_pts(-80, 135, -45, 45, -10, roof + lift + 60)),
        printed=[("tpu_wind_lid_gasket", 1)], hw=[("m3x8", 3)],
        do=["Lay the TPU gasket on the rim, its three ear holes over the inserts.",
            "Lower the lid and vane onto it. The vane screw's head goes down through the PCB's "
            "centre hole.",
            "Drive three M3 x 8 through the lid's ears into the inserts. Turn the vane to get the "
            "spine out of the way of the hex key. Tighten evenly, snug.",
            "Tighten the gland's dome nut on the cable.",
            "Check with a meter on the cable: the anemometer reed closes once per turn of the cups, "
            "and each vane reed closes as the magnet passes over it."],
        nums=[("M3 x 8 thread into the insert", "%s (through %s lid and %s gasket)" %
               (mm(8 - P.wind_lid_t - P.wind_gasket_t), fmt(P.wind_lid_t), fmt(P.wind_gasket_t))),
              ("Vane screw head through the PCB hole", "&Oslash;%s through &Oslash;%s" %
               (fmt(P.shaft_head_d), mm(P.vane_pcb_hole, 2))),
              ("Vane magnet to the reeds", mm(n["vane_mag_dist"]) + " centre to centre")],
        bench=["Magnet strength (README, bench item 1): if three vane positions close at once, "
               "raise <code>pcb_standoff</code> or use a smaller magnet; if none close between "
               "sectors, set <code>vane_mag_n = 2</code>."]))
    return steps


def rain_steps(p, n):
    pl = dict(rain.place(p))
    base, bucket, funnel = pl["rain_base"], pl["rain_bucket"], pl["rain_funnel"]
    t = P.rain_base_t
    zp = P.rain_pivot_z
    stop_z = t + P.rain_stop_boss_h
    stops = [put(hw_shcs(3, n.get("stop_len", 16)), (s * P.rain_stop_x, 0, stop_z)) for s in (1, -1)]
    mag_z = zp - P.rain_pivot_h + 1.0 + P.rain_mag_d / 2
    glass, leads = hw_reed(P.reed_l - 0.5, 2.0, 9.0)
    reed = [mv(glass, P.rain_mag_x, P.rain_reed_y, mag_z), mv(leads, P.rain_mag_x, P.rain_reed_y, mag_z)]

    def bucket_xf(s):
        s = mv(s, 0, 0, -P.rain_pivot_h)
        s = rot(s, P.rain_tilt, (0, 1, 0))
        return mv(s, 0, 0, zp)

    W = P.rain_bucket_w / 2
    mags = [bucket_xf(put(hw_magnet(P.rain_mag_d, P.rain_mag_t),
                          (s * P.rain_mag_x, s * (W + 0.6 + (P.rain_mag_d + 0.2) / 2),
                           1.0 + P.rain_mag_d / 2), (1, 0, 0))) for s in (1, -1)]
    y0 = W + P.rain_side_gap + P.rain_upright_t
    axle = put(hw_shcs(3, n["axle"]), (0, -y0, zp), (0, -1, 0))
    nyl = put(hw_nut(5.5, 4.0, 3.0), (0, y0, zp), (0, 1, 0))
    base_done = [Item(base, "white", ctx=True)] + [Item(s, "steel", ctx=True) for s in stops] + \
        [Item(reed[0], "glass", ctx=True)]
    steps = []
    items = [Item(base, "white", "rain_base")]
    items += [Item(mv(s, 0, 0, 18), "steel", "M3 x %d stop screw" % n.get("stop_len", 16))
              for s in stops]
    items += [Item(mv(reed[0], 0, 0, 14), "glass", "reed switch"), Item(mv(reed[1], 0, 0, 14), "steel")]
    steps.append(Step(
        "Stop screws and reed",
        Scene("rain-01-base", items, view=(1, -1.2, 1.0),
              dashes=[((s * P.rain_stop_x, 0, t), (s * P.rain_stop_x, 0, stop_z + 20)) for s in (1, -1)]),
        printed=[("rain_base", 1)], hw=[("m3x16", 2), ("reed", 1), ("cable3", 1), ("silicone", 1)],
        do=["Drive an M3 x %d into each of the two round bosses either side of the uprights. They "
            "cut their own thread. Leave the heads down on the bosses for now; the heads are the "
            "bucket's stops and are set in step 5.5." % n.get("stop_len", 16),
            "Lay the reed switch in the channel on top of the post beside the uprights, glass along "
            "the bucket's length, and hold it with neutral-cure silicone on the leads. Its wires "
            "leave through the drain opening beside the post: GX12-3 pin 1 pulse, pin 2 GND, pin 3 "
            "the cable's shield (<code>hardware/boards/board-a-core.md</code>)."],
        nums=[("Stop pilots", "&Oslash;%s, through the %s boss and the %s base" %
               (fmt(P.m3_tap_d), mm(P.rain_stop_boss_h), mm(t))),
              ("Stops from the pivot", mm(P.rain_stop_x)),
              ("Stop head top above its boss", "%s nominal (an M3 head seated)" % mm(P.rain_stop_adj)),
              ("Reed", "%s along the bucket from the pivot, %s off the centre line; channel %s wide, "
               "%s deep" % (mm(P.rain_mag_x), mm(P.rain_reed_y), fmt(P.reed_d + 0.3),
                            mm(P.reed_d + 0.2))),
              ("Stop screw tips", "%s out under the base with the heads seated, passing %s beside the "
               "2020 once the base is turned 45&deg; on it" % (mm(n["stop_proud"]), mm(n["stop_side"])))]))
    L = 170.0
    arm = mv(profile_2020(L, "x"), -L / 2, 0, -10)
    turn = lambda s: rz(s, 45)
    holes = [(20.0, 0.0), (-20.0, 0.0)]
    scr = [put(hw_button(5, 8), (x, y, t + n["washer_t"])) for x, y in holes]
    wsh = [put(hw_washer(5.3, 10.0, n["washer_t"]), (x, y, t)) for x, y in holes]
    tn = [put(hw_tnut(), (x, y, -1.8)) for x, y in holes]
    items = [Item(turn(it.shape), it.color, ctx=True) for it in base_done]
    items += [Item(arm, "alu", "2020 crossarm")]
    items += [Item(mv(s, 0, 0, 30), "steel", "M5 x 8 button head") for s in scr]
    items += [Item(mv(s, 0, 0, 18), "steel", "M5 washer") for s in wsh]
    items += [Item(s, "steel", "profile nut") for s in tn]
    steps.append(Step(
        "Bolt the base to the crossarm",
        Scene("rain-02-mount", items, view=(0.8, -1.4, 1.1),
              dashes=[((x, y, -4), (x, y, t + 45)) for x, y in holes]),
        hw=[("m5x8", 2), ("washer", 2), ("tnut", 2)],
        do=["Do this before the bucket goes in: two of the foot screws sit under the bucket's edge.",
            "Set the base on the crossarm's top face turned 45&deg;, so the two drain openings under "
            "the bucket's ends lie off the profile. Two of the four M5 holes then sit over the slot.",
            "Profile nuts into the slot, then two M5 x 8 with washers. Snug.",
            "Check the crossarm is level along and across: the bucket tips by weight."],
        nums=[("Foot holes", "&Oslash;%s at radius %s on the 45&deg; diagonals" %
               (fmt(P.m5_clear), mm(P.rain_foot_r))),
              ("Thread past the washer and base", mm(8 - t - n["washer_t"])),
              ("As drawn", "gauge centre %s in from the crossarm's end" % mm(62))]))
    bucket_items = [Item(bucket, "white")] + [Item(m, "magnet") for m in mags]
    items = base_done[:]
    items += [Item(mv(bucket, 0, 0, 30), "white", "rain_bucket")]
    items += [Item(mv(m, 0, 0, 46), "magnet", "magnet %g x %g" % (P.rain_mag_d, P.rain_mag_t))
              for m in mags]
    items += [Item(mv(axle, 0, -34, 0), "steel", "M3 x %d axle" % n["axle"]),
              Item(mv(nyl, 0, 22, 0), "steel", "M3 nyloc nut")]
    steps.append(Step(
        "Bucket, magnets and axle",
        Scene("rain-03-bucket", items, view=(1, -1.25, 0.8),
              dashes=[((0, -y0 - 40, zp), (0, y0 + 30, zp))]
              + [((P.rain_mag_x * s, s * P.rain_mag_y, mag_z), (P.rain_mag_x * s, s * P.rain_mag_y, mag_z + 52))
                 for s in (1, -1)]),
        printed=[("rain_bucket", 1)], hw=[("mag4", 2), ("axle", 1), ("nyloc", 1), ("epoxy", 1)],
        do=["Drop a %s magnet into the slot in each of the bucket's two corner bosses, on edge, flat "
            "faces toward the bucket's ends, and fix each with a drop of epoxy. One passes the reed; "
            "the other balances it. The bucket works either way round." %
            ("%g x %g" % (P.rain_mag_d, P.rain_mag_t)),
            "Set the bucket between the uprights and push the M3 x %d through the first upright, "
            "the bucket and the second upright." % n["axle"],
            "Nyloc nut on the end, only far enough to stay on: the uprights must not squeeze the "
            "bucket.",
            "Tip the bucket by hand. It should fall onto either stop by itself."],
        nums=[("Axle holes", "&Oslash;%s in the uprights, &Oslash;%s in the bucket" %
               (fmt(P.rain_axle_d + 0.3), fmt(P.rain_axle_d + 0.5))),
              ("Gap each side of the bucket", mm(P.rain_side_gap)),
              ("Pivot above the base's underside", mm(zp)),
              ("Rest angle", "%s&deg; either way" % fmt(P.rain_tilt))]))
    fz = 44
    fscr = [rz(put(hw_shcs(3, 6), (P.rain_r + P.rain_wall, 0, t + P.rain_ring_h / 2), (1, 0, 0)), a)
            for a in (90, 210, 330)]
    items = base_done[:] + [Item(bucket_xf(p["rain_bucket"]), "white", ctx=True)]
    items += [Item(m, "magnet", ctx=True) for m in mags]
    items += [Item(mv(funnel, 0, 0, fz), "white", "rain_funnel"),
              Item(mv(pl["rain_mesh"], 0, 0, fz + 40), "white", "rain_mesh")]
    items += [Item(mv(rz(mv(rz(s, -a), 16, 0, fz), a), 0, 0, 0), "steel", "M3 x 6")
              for s, a in zip(fscr, (90, 210, 330))]
    steps.append(Step(
        "Funnel",
        Scene("rain-04-funnel", items, view=(1, -1.3, 0.75)),
        printed=[("rain_funnel", 1), ("rain_mesh", 1)], hw=[("m3x6", 3)],
        do=["Lower the funnel over the base so its skirt slides down over the base's ring, and turn "
            "it until its three side holes line up with the pilot holes in the ring.",
            "Drive three M3 x 6 through the skirt into the ring. They cut their own thread; snug.",
            "Drop %s into the funnel. It rests on the cone above the nozzle and keeps insects and "
            "leaves out; lift it out to clean it." % c("rain_mesh")],
        nums=[("Collector", "&Oslash;%s inside at the knife edge: %s cm&sup2;, so 1 mm of rain is "
               "%s ml" % (mm(P.rain_collector_d), fmt(P.rain_area_cm2), fmt(P.rain_area_cm2 / 10, 2))),
              ("Ring under the skirt", "%s tall" % mm(P.rain_ring_h)),
              ("Screws", "at 90, 210 and 330&deg;; %s of thread into the ring" %
               mm(6 - P.rain_wall)),
              ("Mesh", "&Oslash;%s, %s thick, %s square holes; rests %s above the nozzle's top" %
               (fmt(P.rain_mesh_d), fmt(P.rain_mesh_t), mm(P.rain_mesh_hole),
                mm(P.rain_mesh_d / 2 - P.rain_nozzle_d / 2)))]))
    items = [Item(base, "white", "rain_base"), Item(bucket_xf(p["rain_bucket"]), "white", "rain_bucket"),
             Item(funnel, "white", "rain_funnel"), Item(pl["rain_mesh"], "white", "rain_mesh")]
    items += [Item(s, "steel", "stop screw", cut=False) for s in stops]
    items += [Item(mags[0], "magnet", cut=False), Item(reed[0], "glass", cut=False),
              Item(axle, "steel", cut=False)]
    steps.append(Step(
        "Set and calibrate the tip",
        Scene("rain-05-section", items, view=(0.12, -1, 0.3), section=((0, 0, 0), (0, -1, 0)),
              size=(1200, 1000)),
        do=["Stand the gauge level.",
            "Pour a known volume of water slowly into the funnel and count the tips. Volume per tip "
            "= volume / tips; mm of rain per tip = ml per tip / %s." % fmt(P.rain_area_cm2 / 10, 2),
            "The stop screws set the tip volume. Turn both by the same amount and measure again.",
            "Use the measured mm per tip downstream; it will differ from the SparkFun bucket's."],
        nums=[("Magnet to reed", "%s as it passes, %s at rest" %
               (mm(P.rain_reed_gap), mm(n["rain_rest"]))),
              ("Rest angle", "%s&deg;" % fmt(P.rain_tilt)),
              ("Nozzle", "&Oslash;%s" % mm(P.rain_nozzle_d))]))
    return steps


def screen_steps(p, n):
    pl = screen.place(p)
    base = pl[0][1]
    plates = [s for name, s in pl if name.startswith("screen_plate")]
    cap = [s for name, s in pl if name == "screen_cap"][0]
    ref = dict(screen.reference())
    t = P.scr_base_t
    posts = [pol(P.scr_post_r, a) for a in screen._POST_ANGLES]
    nuts = [rz(mv(hw_nut(P.scr_nut_af, P.scr_nut_h, 4.0), P.scr_post_r, 0, -n["scr_nut_proud"]), a)
            for a in screen._POST_ANGLES]
    steps = []
    items = [Item(base, "white", "screen_base")]
    items += [Item(mv(s, 0, 0, -16), "steel", "M4 nut") for s in nuts]
    steps.append(Step(
        "M4 nuts into the base (seen from below)",
        Scene("screen-01-nuts", items, view=(0.8, -1.1, -0.9),
              dashes=[((x, y, -24), (x, y, t)) for x, y, _ in posts]),
        printed=[("screen_base", 1)], hw=[("m4nut", 3)],
        do=["Push an M4 nut into each of the three hex pockets under the base, at the post "
            "positions. A strip of tape holds them until the screws catch in step 6.6."],
        nums=[("Pockets", "%s across flats, %s deep; the %s nut stands %s proud underneath" %
               (fmt(P.scr_nut_af + 0.2), mm(P.scr_nut_pocket), fmt(P.scr_nut_h), mm(n["scr_nut_proud"]))),
              ("Posts", "radius %s, at %s&deg;; none sits over a 2020 under the base, whichever "
               "pair of foot holes you use" % (mm(P.scr_post_r), ", ".join(fmt(a, 0) for a in screen._POST_ANGLES)))],
        bench=[]))
    L = 200.0
    arm = mv(profile_2020(L, "x"), -L / 2, 0, -10)
    holes = [(P.scr_foot_r, 0.0), (-P.scr_foot_r, 0.0)]
    scr = [put(hw_button(5, 8), (x, y, t + n["washer_t"])) for x, y in holes]
    wsh = [put(hw_washer(5.3, 10.0, n["washer_t"]), (x, y, t)) for x, y in holes]
    tn = [put(hw_tnut(), (x, y, -1.8)) for x, y in holes]
    items = [Item(base, "white", ctx=True)] + [Item(s, "steel", ctx=True) for s in nuts]
    items += [Item(arm, "alu", "2020 crossarm")]
    items += [Item(mv(s, 0, 0, 30), "steel", "M5 x 8 button head") for s in scr]
    items += [Item(mv(s, 0, 0, 18), "steel", "M5 washer") for s in wsh]
    items += [Item(s, "steel", "profile nut") for s in tn]
    steps.append(Step(
        "Bolt the base to the crossarm",
        Scene("screen-02-mount", items, view=(0.8, -1.4, 1.1),
              dashes=[((x, y, -4), (x, y, t + 45)) for x, y in holes]),
        hw=[("m5x8", 2), ("washer", 2), ("tnut", 2)],
        do=["Set the base on the crossarm with two of its four M5 holes over the slot. Either "
            "pair works; the cable hole and the floor vent stay off the profile both ways.",
            "Profile nuts into the slot, two M5 x 8 with washers. Snug."],
        nums=[("Foot holes", "&Oslash;%s on the axes at radius %s" % (fmt(P.m5_clear), mm(P.scr_foot_r))),
              ("Thread past the washer and base", mm(8 - t - n["washer_t"])),
              ("As drawn", "screen centre %s in from the crossarm's other end" % mm(66))]))
    done = [Item(base, "white", ctx=True)] + [Item(s, "steel", ctx=True) for s in nuts] + \
        [Item(arm, "alu", ctx=True)]
    carrier = [(ref["screen_pcb"], "pcb", "Board B"), (ref["screen_pms7003"], "black", "PMS7003"),
               (ref["screen_j2_plug"], "black", None)]
    items = done[:] + [Item(mv(s, 0, 0, 70), col, lab) for s, col, lab in carrier]
    steps.append(Step(
        "Board B on its rails",
        Scene("screen-03-carrier", items, view=(1, -1.15, 0.6),
              fit=_box_pts(-70, 70, -70, 70, -20, 180)),
        hw=[("boardB", 1), ("pms", 1), ("cable8", 1)],
        do=["Plug the 8-core cable into J1, which faces down out of the board's bottom edge, and feed "
            "the cable down through the hole in the base.",
            "Slide the board down into the grooves of the two rails, sensors (front) toward the cable "
            "hole and the PMS7003 (back) toward the floor vent.",
            "It comes to rest on its two bottom corners; nothing else holds it, so its hole pattern "
            "does not matter."],
        nums=[("Board", "%s x %s x %s" % (fmt(P.scr_pcb_w), fmt(P.scr_pcb_h), mm(P.scr_pcb_t))),
              ("Grooves", "%s wide, %s deep each side" % (fmt(n["groove_w"]), mm(P.scr_pcb_groove))),
              ("Board's bottom edge above the base", "%s, room for the J1 plug and the cable's bend" %
               mm(P.scr_pcb_lift)),
              ("Cable hole and vent", "&Oslash;%s each, %s from the centre" %
               (fmt(P.scr_cable_d), mm(P.scr_foot_r + 1.0))),
              ("PMS7003 gap to the board", "%s on J3, foam tape in the gap" % mm(P.scr_pms_gap))]))
    done += [Item(s, col, ctx=True) for s, col, lab in carrier]
    items = done[:]
    items += [Item(mv(s, 0, 0, 30 + 16 * k), "white", "screen_plate") for k, s in enumerate(plates)]
    steps.append(Step(
        "Louvres",
        Scene("screen-04-plates", items, view=(1, -1.2, 0.7),
              dashes=[((x, y, t), (x, y, 260)) for x, y, _ in posts],
              fit=_box_pts(-75, 75, -75, 75, -20, 250)),
        printed=[("screen_plate", P.scr_plates)],
        do=["Stack the %d plates over the board, rims down, each plate's three posts on the posts "
            "of the one below, holes over the nuts." % P.scr_plates],
        nums=[("Pitch", mm(P.scr_pitch)),
              ("Louvre", "45&deg;, %s thick, &Oslash;%s outside, &Oslash;%s opening" %
               (fmt(P.scr_plate_t), fmt(2 * P.scr_r_out), mm(2 * P.scr_r_in)))]))
    ltg = ref["screen_lightning"]
    zcap = t + P.scr_plates * P.scr_pitch
    L_ = P.m3_insert_l + 1.0
    hpts = [rz(cyl(0.1, 0.1, (x, y, 0)), 45).BoundBox.Center for x, y in screen._ltg_holes()]
    tip = zcap + P.scr_plate_h - L_
    ins = [put(hw_insert(), (q.x, q.y, tip), (0, 0, -1)) for q in hpts]
    zp = tip - P.scr_ltg_t
    lscr = [put(hw_shcs(3, 6), (q.x, q.y, zp), (0, 0, -1)) for q in hpts]
    items = [Item(cap, "white", "screen_cap")]
    items += [Item(mv(s, 0, 0, -14), "brass", "M3 heat-set insert") for s in ins]
    items += [Item(mv(ltg, 0, 0, -26), "pcb", "lightning module")]
    items += [Item(mv(s, 0, 0, -44), "steel", "M3 x 6") for s in lscr]
    steps.append(Step(
        "Lightning module under the cap (seen from below)",
        Scene("screen-05-lightning", items, view=(0.8, -1.1, -0.9),
              dashes=[((q.x, q.y, tip - 60), (q.x, q.y, tip + 4)) for q in hpts]),
        printed=[("screen_cap", 1)], hw=[("insert", 2), ("m3x6", 2), ("ltg", 1)],
        do=["Press two inserts into the bosses under the cap, from the boss tips.",
            "Screw the module to them parts side down (its bare back against the bosses), connector "
            "end over the rib, with two M3 x 6.",
            "Plug its Gravity cable in now; the other end goes to J2 on Board B in the next step."],
        nums=[("Insert pilots", "&Oslash;%s, %s deep" % (fmt(P.m3_insert_d), mm(n["boss_depth"]))),
              ("Holes", "%s apart, %s from the coil end" % (mm(P.scr_ltg_hole_pitch),
                                                           mm(P.scr_ltg_hole_in))),
              ("M3 x 6 thread into the insert", "%s (through the %s board)" %
               (mm(6 - P.scr_ltg_t), mm(P.scr_ltg_t)))]))
    items = [Item(it.shape, it.color, ctx=True) for it in done]
    items += [Item(s, "white", ctx=True) for s in plates]
    items += [Item(mv(cap, 0, 0, 40), "white", "screen_cap (6.5)"),
              Item(mv(ltg, 0, 0, 40), "pcb", ctx=True)]
    clamp = [put(hw_shcs(4, n["scr_screw"], P.scr_head_d, 4.0), (x, y, n["scr_seat"])) for x, y, _ in posts]
    items += [Item(mv(s, 0, 0, 120), "steel", "M4 x %d" % n["scr_screw"]) for s in clamp]
    steps.append(Step(
        "Cap and clamp screws",
        Scene("screen-06-cap", items, view=(1, -1.2, 0.75),
              dashes=[((x, y, t), (x, y, n["scr_seat"] + 125)) for x, y, _ in posts],
              size=(1200, 1050)),
        hw=[("m4", 3)],
        do=["Hold the cap above the stack, plug the lightning module's cable into J2, then lower the "
            "cap onto the top plate's posts.",
            "Drop an M4 x %d down through each post into its nut and tighten them in turn until the "
            "stack stops rattling. The plates are %s thick: snug is enough." %
            (n["scr_screw"], mm(P.scr_plate_t))],
        nums=[("Screw needed", "%s from the head's seat to the far face of the nut" % mm(n["scr_need"])),
              ("Left under the nut", "%s of an M4 x %d" % (mm(n["scr_screw"] - n["scr_need"]),
                                                          n["scr_screw"])),
              ("Screen", "%s tall, &Oslash;%s" % (mm(n["scr_height"], 0), mm(2 * P.scr_r_out, 0)))]))
    return steps


def box_steps(p, n):
    pl = enclosure.place(p)
    pd = dict(pl)
    body, lid_u, gasket = pd["enclosure_body"], pd["enclosure_lid"], pd["tpu_box_lid_gasket"]
    ref = dict(enclosure.reference())
    W, H, D = P.enc_in_w, P.enc_in_h, P.enc_in_d
    t, tb, lt = P.enc_wall, P.enc_back, P.enc_lid_t
    rim = tb + D
    ears = enclosure._ears()
    bx, by = P.enc_brd_x, P.enc_brd_y
    ins = [put(hw_insert(), (x, y, rim)) for x, y in ears]
    ins += [put(hw_insert(), (bx + hx, by + hy, tb + P.standoff_h)) for hx, hy in P.brd_holes]
    steps = []
    items = [Item(body, "white", "enclosure_body")]
    items += [Item(mv(s, 0, 0, 18), "brass", "M3 heat-set insert") for s in ins]
    steps.append(Step(
        "Heat-set inserts",
        Scene("box-01-inserts", items, view=(0.45, -1, 1.35),
              dashes=[((x, y, rim - 7), (x, y, rim + 18)) for x, y in ears]),
        printed=[("enclosure_body", 1)], hw=[("insert", 9)],
        do=["Six inserts into the ears round the rim, from the top, flush.",
            "Three into the board standoffs on the back wall, flush with their tops."],
        nums=[("Rim ears", "&Oslash;%s, %s deep" % (fmt(P.m3_insert_d), mm(n["ear_depth"]))),
              ("Standoffs", "&Oslash;%s, %s deep; standoff &Oslash;7.5 x %s tall" %
               (fmt(P.m3_insert_d), mm(n["standoff_depth"]), mm(P.standoff_h)))]))
    done = [Item(body, "white", ctx=True)] + [Item(s, "brass", ctx=True) for s in ins]
    socks, washers, gnuts = [], [], []
    labels = {"ENV": "GX16-8", "SOLAR": "GX12-2", "RAIN": "GX12-3", "WIND": "GX16-5", "SKY": "GX12-4"}
    zc = tb + D / 2
    for (lab, d, fl), x in zip(P.enc_ports, enclosure.port_positions()):
        socks.append((lab, put(hw_gx(d, fl), (x, -t - P.port_gasket_t, zc), (0, -1, 0))))
        washers.append(("tpu_washer_gx16" if d > 14 else "tpu_washer_gx12",
                        put(enclosure.washer(d, fl), (x, -t, zc), (0, -1, 0))))
        gnuts.append(put(hw_gx_nut(d, fl), (x, 0.0, zc), (0, 1, 0)))
    items = done[:]
    items += [Item(mv(s, 0, -34, 0), "steel", "%s %s" % (lab, labels.get(lab, ""))) for lab, s in socks]
    items += [Item(mv(s, 0, -16, 0), "tpu", lab) for lab, s in washers]
    items += [Item(mv(s, 0, 16, 0), "steel", "socket nuts") for s in gnuts]
    steps.append(Step(
        "Connector sockets in the bottom wall",
        Scene("box-02-ports", items, view=(0.3, -1, 0.75),
              dashes=[((x, -t - 55, zc), (x, 22, zc)) for x in enclosure.port_positions()]),
        printed=[("tpu_washer_gx16", 2), ("tpu_washer_gx12", 3)],
        hw=[("gx16_8", 1), ("gx12_2", 1), ("gx12_3", 1), ("gx16_5", 1), ("gx12_4", 1)],
        do=["Each socket goes in from outside with a TPU washer under its flange; its nut goes on "
            "inside.",
            "Left to right, seen from the front (the lid side): %s. Each name is engraved on the lid "
            "above its socket." % ", ".join("%s (%s)" % (lab, labels.get(lab, "")) for lab, _d, _f in P.enc_ports),
            "Tighten each nut until its washer just squeezes.",
            "Pins (<code>hardware/boards/board-a-core.md</code> and the README): SOLAR 1 panel +, 2 "
            "panel &minus;. RAIN 1 pulse, 2 GND, 3 shield. WIND 1 VBAT, 2 GND, 3 vane analog, 4 "
            "anemometer pulse, 5 shield. SKY 1 VBAT, 2 GND, 3 SDA, 4 SCL to Board A's Qwiic port. ENV "
            "pin n = Board B J1 pin n, split inside to Board A J4 (XH-5, pins 1 to 5) and J5 (XH-4, "
            "pins 6, 2, 7, 8)."],
        nums=[("Holes", "&Oslash;%s for GX16, &Oslash;%s for GX12" % (fmt(P.gx16_d), mm(P.gx12_d))),
              ("Centres from the inside of the left wall", ", ".join(
                  "%s %s" % (lab, fmt(x)) for lab, _d, x in n["ports"]) + " mm"),
              ("Wall plus washer", "%s + %s = %s" % (fmt(t), fmt(P.port_gasket_t),
                                                     mm(t + P.port_gasket_t)))],
        bench=["Each socket's nut gets full thread past %s of wall and washer." % mm(t + P.port_gasket_t)]))
    done += [Item(s, "steel", ctx=True) for _l, s in socks] + [Item(s, "tpu", ctx=True) for _l, s in washers]
    done += [Item(s, "steel", ctx=True) for s in gnuts]
    zb = tb + P.standoff_h + P.brd_t
    bscr = [put(hw_shcs(3, 8), (bx + hx, by + hy, zb)) for hx, hy in P.brd_holes]
    items = done[:]
    items += [Item(mv(ref["board_a"], 0, 0, 24), "pcb", "Board A"),
              Item(mv(ref["antenna"], 0, 0, 24), "black", "antenna")]
    items += [Item(mv(s, 0, 0, 44), "steel", "M3 x 8") for s in bscr]
    steps.append(Step(
        "Board A and the antenna",
        Scene("box-03-board", items, view=(0.45, -1, 1.35),
              dashes=[((bx + hx, by + hy, tb), (bx + hx, by + hy, zb + 50)) for hx, hy in P.brd_holes]),
        hw=[("boardA", 1), ("m3x8", 3), ("ant", 1)],
        do=["Connect the socket pigtails to Board A first if they are easier to reach with the board "
            "out.",
            "Set Board A on the three standoffs, its connector row toward the sockets, and fix it with "
            "three M3 x 8. The fourth corner, under the radio, has no hole and rests on a ledge.",
            "Screw the right-angle stubby onto the radio's SMA so the whip points up and lies in its "
            "saddle."],
        nums=[("Standoffs", mm(P.standoff_h) + " tall"),
              ("M3 x 8 thread into the insert", "%s (through the %s board)" %
               (mm(8 - P.brd_t), mm(P.brd_t))),
              ("Whip", "%s from the cell, %s from the mast" %
               (mm(P.enc_ant_to_cell, 0), mm(P.enc_ant_to_mast, 0)))],
        bench=["The antenna's sizes (<code>ant_elbow</code>, <code>ant_d</code>, <code>ant_len</code>) "
               "are estimates from a photo; measure yours and rebuild (README, bench item 6).",
               "Check nothing on Board A's underside sits on the %s ledge under the radio corner "
               "(README, bench item 4)." % mm(2)]))
    done += [Item(ref["board_a"], "pcb", ctx=True), Item(ref["antenna"], "black", ctx=True)]
    done += [Item(s, "steel", ctx=True) for s in bscr]
    items = done[:] + [Item(mv(ref["cell"], 0, 0, 34), "cell", "cell")]
    steps.append(Step(
        "The cell",
        Scene("box-04-cell", items, view=(0.45, -1, 1.35)),
        hw=[("cell", 1), ("foam", 1), ("silica", 1)],
        do=["Lay the cell in its cradle above the board, between the two end stops.",
            "Stick the 3 mm closed-cell foam on the pad inside the lid; it presses on the cell when "
            "the lid closes.",
            "Put a silica gel sachet in the box."],
        nums=[("Cradle", "&Oslash;%s x %s cell, %s free at each end for tabs and wires" %
               (fmt(P.batt_d), mm(P.batt_l), mm(P.batt_end_gap))),
              ("Lid pad", "40 x 12 mm")],
        bench=["Defaults fit a 32700. For a 32650 set <code>batt_l = 66</code> and rebuild."]))
    done += [Item(ref["cell"], "cell", ctx=True)]
    lscr = [put(hw_shcs(3, 8), (x, y, rim + lt)) for x, y in ears]
    items = done[:]
    items += [Item(mv(gasket, 0, 0, 14), "tpu", "tpu_box_lid_gasket"),
              Item(mv(lid_u, 0, 0, 34), "white", "enclosure_lid")]
    items += [Item(mv(s, 0, 0, 56), "steel", "M3 x 8") for s in lscr]
    steps.append(Step(
        "Gasket and lid",
        Scene("box-05-lid", items, view=(0.45, -1, 1.2),
              dashes=[((x, y, rim - 4), (x, y, rim + lt + 60)) for x, y in ears]),
        printed=[("tpu_box_lid_gasket", 1), ("enclosure_lid", 1)], hw=[("m3x8", 6)],
        do=["Press the TPU gasket into the groove round the rim, all the way down, without twists.",
            "Put the lid on with its lettering outside, each name over its socket.",
            "Six M3 x 8 into the rim inserts. Tighten in a cross pattern, a little at a time, until "
            "the lid is down all round; snug.",
            "The box is sealed. If condensation shows up, the README's fix is a membrane vent plug "
            "(M12 x 1.5, in <code>BOM.md</code>) drilled through the bottom wall."],
        nums=[("Groove", "%s wide, %s deep" % (fmt(P.enc_groove_w), mm(P.enc_groove_d))),
              ("Gasket", "%s tall as printed; the lid's ridge (%s wide, %s tall) presses %s into it" %
               (mm(P.gasket_h), fmt(0.8), mm(n["ridge_h"]), mm(P.gasket_squeeze))),
              ("M3 x 8 thread into the insert", "%s (through the %s lid)" % (mm(8 - lt), mm(lt)))],
        bench=["The %s squeeze is a guess (README, bench item 7): if the lid bows between screws, "
               "lower <code>gasket_squeeze</code>." % mm(P.gasket_squeeze)]))
    return steps


def solar_steps(p, n):
    br = p["solar_bracket"]
    pan = enclosure.solar_reference()[0][1]
    nrm = (0, math.cos(math.radians(P.solar_tilt)), math.sin(math.radians(P.solar_tilt)))
    d = 34
    items = [Item(br, "white", "solar_bracket"),
             Item(mv(pan, nrm[0] * d, nrm[1] * d, nrm[2] * d), "solar", "solar panel")]
    return [Step(
        "Panel into the tray",
        Scene("solar-01-panel", items, view=(0.75, 0.55, 1.2), up=(0, 1, 0)),
        printed=[("solar_bracket", 1)], hw=[("panel", 1), ("cable2", 1), ("silicone", 1)],
        do=["Feed the panel's lead through the hole in the tray floor. It, or a 2-core cable joined "
            "to it, runs down to the box's SOLAR socket.",
            "Lay the panel in the tray, between the side rims and the two low lips at the ends.",
            "Run a bead of neutral-cure silicone along both side rims to hold it; the rims and lips "
            "only locate it."],
        nums=[("Tray inside", "%s x %s, for a panel up to %s x %s x %s" %
               (fmt(P.panel_l + 2 * P.fit_slide), fmt(P.panel_w + 2 * P.fit_slide),
                fmt(P.panel_l), fmt(P.panel_w), mm(P.panel_t))),
              ("Tilt", "%s&deg; from horizontal" % fmt(P.solar_tilt)),
              ("Cable hole", "&Oslash;%s, middle of the tray" % mm(16))],
        )]


def sky_steps(p, n):
    pl = dict(sky.place(p))
    mount, head, seal = pl["sky_mount"], pl["sky_head"], pl["tpu_sky_can_seal"]
    sensor = dict(sky.reference())["sky_sensor"]
    t = math.radians(P.sky_tilt)
    a = (math.sin(t), 0.0, math.cos(t))
    along = lambda s, dd: mv(s, a[0] * dd, a[1] * dd, a[2] * dd)
    stub = mv(profile_2020(90), -10, 0, -90)
    scr = [sky.to_mount(put(hw_shcs(3, 8), (0, s * P.sky_ro, sky.SKIRT + P.sky_plug_h / 2), (0, s, 0)))
           for s in (1, -1)]
    items = [Item(stub, "alu", ctx=True), Item(mount, "white", "sky_mount"),
             Item(along(sensor, 16), "pcb", "MLX90614 breakout"),
             Item(along(seal, 30), "tpu", "tpu_sky_can_seal"),
             Item(along(head, 46), "white", "sky_head")]
    items += [Item(mv(along(s, 46), 0, k * 14, 0), "steel", "M3 x 8") for s, k in zip(scr, (1, -1))]
    o = sky._axis_origin()
    steps = [Step(
        "Sensor, seal and head",
        Scene("sky-01-exploded", items, view=(0.45, -1.2, 0.55),
              dashes=[(o, (o[0] + a[0] * 90, 0, o[2] + a[2] * 90))],
              fit=_box_pts(-20, 62, -22, 22, -60, 118), size=(1000, 1100)),
        printed=[("sky_mount", 1), ("tpu_sky_can_seal", 1), ("sky_head", 1)],
        hw=[("mlx", 1), ("m3x8", 2), ("silicone", 1), ("cable4", 1)],
        do=["Solder four wires to the breakout's header and drop them down the slot through the "
            "plug; they come out under the head.",
            "Lay the breakout on the plug's top face, can up, header end over the slot.",
            "Slip the TPU seal over the can.",
            "Slide the head down over the plug until the can comes up through the hole in its floor. "
            "Either way round fits: the drains run both ways.",
            "Two M3 x 8 through the head's sides into the plug. They cut their own thread; snug.",
            "Seal the cable exit under the pod with neutral-cure silicone."],
        nums=[("Can", "&Oslash;%s through a &Oslash;%s hole" % (fmt(P.sky_can_d), mm(P.sky_can_d + 0.4))),
              ("Seal", "&Oslash;%s x &Oslash;%s, %s thick, squeezed to %s" %
               (fmt(P.sky_can_d + 5.0), fmt(P.sky_can_d - 0.2), fmt(P.sky_ring_c + 0.3),
                mm(P.sky_ring_c))),
              ("Can above the cone floor", mm(P.sky_can_proud)),
              ("View", "&plusmn;%s&deg; cone, axis leaning %s&deg; away from the mast" %
               (fmt(P.sky_snout_half), fmt(P.sky_tilt)))],
        bench=["README bench item 8: read the letters on the can (this pod assumes BAA: 3 V, 90&deg; "
               "view); the breakout sizes in <code>params.py</code> are typical, not measured; and "
               "the sensor's 1 to 2 mA needs sleeping or gating."])]
    items = [Item(stub, "alu", ctx=True, cut=False), Item(mount, "white", "sky_mount"),
             Item(sensor, "pcb", "MLX90614 can"), Item(seal, "tpu", "tpu_sky_can_seal"),
             Item(head, "white", "sky_head")]
    steps.append(Step(
        "Check the fit (section)",
        Scene("sky-02-section", items, view=(0.08, -1, 0.1), section=((0, 0, 0), (0, -1, 0)),
              fit=_box_pts(-25, 60, -20, 20, -50, 82)),
        nums=[("Opening above the mast top", mm(P.sky_rise)),
              ("Lowest rim above the top of the vane", mm(n["sky_rim_above_vane"], 0)),
              ("Vane tail to the pod", mm(n["vane_tail_gap"], 0))]))
    return steps


# -------------------------------------------------------------- mast / frame
def _frame_color(name):
    if name.startswith("ref_"):
        k = name[4:]
        if "bearing" in k:
            return "steel"
        if k in ("vane_pcb", "screen_pcb", "board_a", "sky_sensor", "screen_lightning"):
            return "pcb"
        if k == "cell":
            return "cell"
        if k == "solar_panel":
            return "solar"
        return "black"
    base = name
    for pre in ("cup_arm", "screen_plate", "tpu_washer"):
        if name.startswith(pre):
            base = pre + ("_gx12" if pre == "tpu_washer" else "")
    return printed_color(base)


def _frame_group(name):
    k = name[4:] if name.startswith("ref_") else name
    if k.startswith(("wind_", "vane", "cup_", "tpu_wind", "bearing")):
        return "wind kit"
    if k.startswith(("sky", "tpu_sky")):
        return "sky pod"
    if k.startswith("rain"):
        return "rain gauge"
    if k.startswith("screen"):
        return "Stevenson screen"
    if k.startswith(("enclosure", "tpu_box", "tpu_washer", "board_a", "cell", "antenna")):
        return "core box"
    if k.startswith("solar"):
        return "solar bracket"
    return None


def frame_steps(parts, n):
    Lm = P.mast_len
    za = Lm - P.arm_drop
    placed = frame_assembly(parts)
    mast = profile_2020(Lm)
    arm = mv(profile_2020(P.arm_len, "y"), 20, -P.arm_len / 2, za - 10)
    brk = []
    for s in (1, -1):
        z0 = za if s > 0 else za - 20
        leg_h = box(-10, 10, 10, 30, z0, z0 + 3) if s > 0 else box(-10, 10, 10, 30, z0 - 3, z0)
        leg_v = box(-10, 10, 10, 13, z0, z0 + 20) if s > 0 else box(-10, 10, 10, 13, z0 - 20, z0)
        brk.append(rz(fuse([leg_h, leg_v]), -90))          # on the north face, like the crossarm
    groups = {}
    for name, s in placed:
        if name.startswith("frame_"):
            continue
        g = _frame_group(name)
        groups.setdefault(g, []).append((name, s))

    def station(highlight=(), label_all=False, extra=()):
        items = [Item(mast, "alu", "2020 mast" if label_all else None,
                      ctx=bool(highlight) and "mast" not in highlight),
                 Item(arm, "alu", "2020 crossarm" if (label_all or "crossarm" in highlight) else None,
                      ctx=bool(highlight) and "crossarm" not in highlight)]
        for g, lst in groups.items():
            on = g in highlight
            for k, (name, s) in enumerate(lst):
                lab = g if (label_all or on) else None
                items.append(Item(s, _frame_color(name), lab, ctx=bool(highlight) and not on))
        items += [Item(b, "steel", "right-angle connector" if "crossarm" in highlight else None,
                       ctx=bool(highlight) and "crossarm" not in highlight) for b in brk]
        return items + list(extra)

    def up_box(s):
        return mv(rz(rx(s, 90), -90), -10, P.enc_tab_x, Lm - P.enc_drop - P.enc_in_h / 2)

    def up_sol(s):
        y_lo = -(P.solar_foot_pitch + P.m5_head_d / 2 + 3.0)
        sz = (Lm - P.enc_drop - P.enc_in_h / 2) + P.enc_in_h + P.enc_wall + P.enc_tab_len + 6.0 - y_lo
        return mv(rz(rx(s, 90), -90), -10, 0, sz)

    wt = n["washer_t"]

    def mount_set(points, length, plate_t, xf, axis=(0, 0, 1)):
        out = []
        for q in points:
            out.append((xf(put(hw_button(5, length), (q[0], q[1], plate_t + wt), axis)), "screw"))
            out.append((xf(put(hw_washer(5.3, 10.0, wt), (q[0], q[1], plate_t), axis)), "washer"))
            out.append((xf(put(hw_tnut(), (q[0], q[1], -1.8), axis)), "tnut"))
        return out

    cx = P.enc_tab_x
    o = P.enc_tab_len / 2 + 0.5
    tabs = [(cx, P.enc_in_h + P.enc_wall + o), (cx, -P.enc_wall - o)]
    box_hw = mount_set(tabs, 10, P.enc_tab_t, up_box)
    sol_hw = mount_set([(0, P.solar_foot_pitch), (0, -P.solar_foot_pitch)], 12, P.solar_foot_t, up_sol)
    L, ft, h = P.wind_arm_len, P.wind_foot_t, P.wind_body_h
    kz = Lm - h - P.wind_gasket_t
    wind_pts = [(0, h / 2 + P.wind_foot_pv), (0, h / 2 - P.wind_foot_pv)]

    wind_hw = []
    for dy, dz in wind_pts:
        wind_hw.append((mv(put(hw_button(5, 12), (-10 - ft - wt, dy, kz + dz), (-1, 0, 0)), 0, 0, 0), "screw"))
        wind_hw.append((put(hw_washer(5.3, 10.0, wt), (-10 - ft, dy, kz + dz), (-1, 0, 0)), "washer"))
        wind_hw.append((put(hw_tnut(), (-10 + 1.8, dy, kz + dz), (-1, 0, 0)), "tnut"))
    sky_hw = []
    zc = -P.sky_foot_h / 2
    for dz in (P.sky_foot_pitch, -P.sky_foot_pitch):
        z = Lm + zc + dz
        sky_hw.append((put(hw_button(5, 12), (10 + P.sky_foot_t + wt, 0, z), (1, 0, 0)), "screw"))
        sky_hw.append((put(hw_washer(5.3, 10.0, wt), (10 + P.sky_foot_t, 0, z), (1, 0, 0)), "washer"))
        sky_hw.append((put(hw_tnut(), (10 - 1.8, 0, z), (1, 0, 0)), "tnut"))

    def hw_items(lst, length):
        names = {"screw": "M5 x %d button head" % length, "washer": "M5 washer", "tnut": "profile nut"}
        return [Item(s, "steel", names[k]) for s, k in lst]

    steps = []
    steps.append(Step(
        "Crossarm onto the mast",
        Scene("mast-01-crossarm", station(("crossarm",)), view=(1, -0.45, 0.42), size=(1100, 1300),
              dims=[((10, 0, Lm), (10, 0, za), "%s" % fmt(P.arm_drop, 0), -70)]),
        hw=[("bracket", 2), ("m5x10", 4), ("tnut", 4)],
        do=["Fit the rain gauge and the screen to the crossarm first (sections 5 and 6).",
            "Fix the crossarm across the mast's north face, the same face as the sky pod, running "
            "east to west, with two right-angle connectors: one in the corner above it and one below. "
            "Each leg takes an M5 x 10 into a profile nut; the connectors come without them.",
            "Rain gauge to the east, screen to the west. On the north face neither of them can stand "
            "between the sun and the solar panel on the south face; on an arm running north to south "
            "the screen shaded the panel around midday from late February to October.",
            "The frame lengths and heights here are the ones drawn; cut the profiles and set the "
            "heights to suit the site.",
            "Level it, along and across; the rain gauge needs it."],
        nums=[("As drawn", "crossarm top %s below the mast top; mast %s, crossarm %s long; rain gauge "
               "on the east end, screen on the west end" %
               (mm(P.arm_drop, 0), mm(P.mast_len, 0), mm(P.arm_len, 0)))],
        ))
    steps.append(Step(
        "Box and solar bracket on the south face",
        Scene("mast-02-box", station(("core box", "solar bracket"), extra=hw_items(box_hw, 10)
                                    + hw_items(sol_hw, 12)),
              view=(-1, -0.75, 0.35), size=(1100, 1300),
              dims=[((-10, 10, Lm), (-10, 10, Lm - P.enc_drop), fmt(P.enc_drop, 0), 70)]),
        hw=[("m5x10", 2), ("washer", 4), ("tnut", 4), ("m5x12", 2)],
        do=["Box: its top and bottom tabs into the slot of the mast's south face, each with an M5 x 10, "
            "a washer and a profile nut. Its left and right tabs are for a horizontal 2020.",
            "The tabs sit %s left of the box's centre, so the antenna end (the right-hand end, seen "
            "from the lid) stands further from the mast. The README says to hang the box on the "
            "side of the mast that faces the coordinator." % mm(P.enc_tab_shift),
            "Solar bracket: its foot on the same face, above the box, with two M5 x 12, washers and "
            "profile nuts through the two holes one above the other. As drawn, its foot stops %s "
            "above the box's top tab, so the panel shades the box." % mm(n["solar_gap"], 0),
            "Plug the cables in from below, each with a drip loop under its plug."],
        nums=[("As drawn", "box centre %s below the mast top" % mm(P.enc_drop, 0)),
              ("Tab holes", "%s apart, centre to centre" % mm(n["tab_pitch"])),
              ("Thread past washer and part", "box tab (%s): %s; solar foot (%s): %s" %
               (fmt(P.enc_tab_t), mm(10 - P.enc_tab_t - n["washer_t"]), fmt(P.solar_foot_t),
                mm(12 - P.solar_foot_t - n["washer_t"]))),
              ("Solar foot holes", "&plusmn;%s from its centre" % mm(P.solar_foot_pitch))]))
    top_fit = _box_pts(-235, 60, -60, 60, Lm - 95, Lm + 85)
    steps.append(Step(
        "Wind kit at the top",
        Scene("mast-03-wind", station(("wind kit",), extra=hw_items(wind_hw, 12)),
              view=(-0.55, -1, 0.45), fit=top_fit, size=(1200, 820)),
        hw=[("m5x12", 2), ("washer", 2), ("tnut", 2)],
        do=["Bolt the wind kit's foot to the mast's south face, arm pointing south, top of the foot "
            "level with the mast top.",
            "On a vertical mast use the two holes one above the other; the pair side by side is for "
            "a horizontal 2020. Reach the screws with a 3 mm hex key between the arm's two rails.",
            "Run the cable along the rail (it has tie slots), down past the foot and into the mast's "
            "east or west slot: the south slot carries the solar bracket and the box."],
        nums=[("Foot holes", "&plusmn;%s vertically, &plusmn;%s side by side" %
               (fmt(P.wind_foot_pv), mm(P.wind_foot_pitch_h))),
              ("Rotor axis to the mast face", mm(P.wind_arm_len)),
              ("Thread past washer and foot", mm(12 - P.wind_foot_t - n["washer_t"])),
              ("As drawn", "foot top %s below the mast top (the lid's underside is level with it)" %
               mm(n["wind_top_drop"]))]))
    steps.append(Step(
        "Sky pod on the north face",
        Scene("mast-04-sky", station(("sky pod",), extra=hw_items(sky_hw, 12)),
              view=(0.75, -1, 0.4), fit=top_fit, size=(1200, 820)),
        hw=[("m5x12", 2), ("washer", 2), ("tnut", 2)],
        do=["Bolt %s to the face opposite the wind arm (north), top of its foot level with the mast "
            "top, using the two holes one above the other." % c("sky_mount"),
            "Run its cable down the riser (tie notches) and into the mast's east or west slot: the "
            "north slot carries the crossarm's connectors lower down."],
        nums=[("Foot", "%s x %s x %s; holes &plusmn;%s round a point %s below the mast top" %
               (fmt(P.sky_foot_w), fmt(P.sky_foot_h), mm(P.sky_foot_t), fmt(P.sky_foot_pitch),
                mm(P.sky_foot_h / 2))),
              ("Sensor opening above the mast top", mm(P.sky_rise))]))
    items = station(label_all=True)
    steps.append(Step(
        "Which way round, and the cables",
        Scene("mast-05-plan", items, view=(0, 0, 1), up=(1, 0, 0), size=(1100, 1000),
              compass=(1, 0, 0), fit=_box_pts(-240, 130, -260, 260, 0, Lm + 100)),
        hw=[("ties", 20)],
        do=["Turn the mast so the sky pod's face points north (northern hemisphere). The pod then "
            "leans away from the sun's path, the panel faces the sun with nothing between them, "
            "and the box sits in the panel's shade.",
            "Every cable runs down the mast's east or west slot to the box's bottom wall; the north "
            "and south slots carry the crossarm, bracket and box. Leave a drip loop below each plug; "
            "2020 slot covers hold a 4 to 5 mm cable in the slot.",
            "Use UV-stable black cable ties; white ones go brittle in sun."],
        nums=[("North", "sky pod at the top; the crossarm lower down, running east to west"),
              ("South", "wind arm at the top; solar bracket, box under it"),
              ("East", "rain gauge, on the crossarm's end"), ("West", "Stevenson screen, on the other end"),
              ("East and west faces", "the cables")]))
    # The last picture is the station as it stands: everything on, from the side the cover does not show.
    done = Scene("mast-06-finished", overview_scene(parts).items, view=(-0.85, 1, 0.38), size=(1100, 1400))
    done.text_labels = True
    steps.append(Step(
        "The finished station",
        done,
        do=["Walk round it once. Every screw snug, every plug seated with a drip loop under it, and "
            "nothing left on the bench that belongs on the mast.",
            "Flick the cups: they should coast, not stop dead. Turn the vane by hand: it should go "
            "all the way round with no tight spot.",
            "Write down which face points north and the date it went up.",
            "Then leave it be. The first rain will arrive when it is ready, and the bucket will "
            "count it without being asked."],
        nums=[("Mast", mm(Lm, 0)), ("Crossarm", "%s, its top %s below the mast top" %
                                     (mm(P.arm_len, 0), mm(P.arm_drop, 0)))]))
    steps[-1].finale = True                    # its own page in print, the picture full size
    return steps


def overview_scene(parts):
    Lm = P.mast_len
    za = Lm - P.arm_drop
    placed = frame_assembly(parts)
    items = [Item(profile_2020(Lm), "alu", "2020 mast"),
             Item(mv(profile_2020(P.arm_len, "y"), 20, -P.arm_len / 2, za - 10), "alu", "2020 crossarm")]
    seen = set()
    for name, s in placed:
        if name.startswith("frame_"):
            continue
        items.append(Item(s, _frame_color(name), _frame_group(name)))
    return Scene("overview", items, view=(-0.85, -1, 0.42), size=(1100, 1400))


# ==================================================================== HTML ===
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600'
         '&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap">')


def print_css():
    """The guide's CSS, light only, laid out for A4: a cover, sections that open on a new page,
    two steps to a page where they fit, page numbers in the margin."""
    import re
    css = re.sub(r"@media \(prefers-color-scheme: dark\) \{.*?\} \}", "", CSS, flags=re.S)
    css = re.sub(r':root\[data-theme="dark"\] \{.*?\}', "", css, flags=re.S)
    return css + """
@page { size: A4; margin: 14mm 13mm 16mm;
  @bottom-left { content: "Forsyth station \\00b7  assembly guide"; font: 7.5pt "IBM Plex Sans", Helvetica, sans-serif;
    color: #7a8596; }
  @bottom-right { content: counter(page) " / " counter(pages); font: 600 7.5pt "IBM Plex Mono", Menlo, monospace;
    color: #3d6a93; } }
@page :first { @bottom-left { content: none; } @bottom-right { content: none; } }
:root { --accent: #3d6a93; --accent-soft: #eaf1f7; --lamp: #fbf6ec; }
body { background: #fff; font: 9.4pt/1.42 var(--body); }
.wrap { max-width: 184mm; padding: 0; }
h2, h3, h4, .lbl { break-after: avoid; page-break-after: avoid; }
h2 { break-before: page; margin: 0 0 1mm; padding-top: 2mm; border-top: 0;
  border-bottom: 1.5px solid #1d2530; padding-bottom: 2mm; font-size: 17pt; }
h2 .secno { font-size: 30pt; }
.intro { font-size: 9.8pt; margin: 2mm 0 4mm; }
#parts, #start { break-before: page; }
.cover { min-height: 262mm; display: flex; flex-direction: column; break-after: page; }
.cover h1 { font-size: 34pt; margin: 6mm 0 3mm; letter-spacing: -0.01em; }
.cover .lead { font-size: 11pt; line-height: 1.5; max-width: 150mm; }
.cover figure.over { flex: 1; margin: 2mm 0; }
.cover figure.over svg { max-height: 150mm; }
.cover nav.toc { break-after: auto; background: var(--lamp); border-radius: 3mm; padding: 3mm 5mm; }
.cover nav.toc ol { columns: 3; font-size: 8.6pt; margin: 0; }
.mark-f { width: 11mm; height: 11mm; }
/* A step: picture on the left with its parts beside it, then the instructions and numbers
   full width, so most steps take half a page. */
.step { display: grid; grid-template-columns: minmax(0, 1fr) 54mm; column-gap: 6mm; align-items: start;
  border: 0; border-top: 1px solid #c5ccd6; border-radius: 0; padding: 2.5mm 0 0; margin: 0 0 3mm;
  break-inside: avoid; page-break-inside: avoid; }
.step > header, .step > dl.nums, .step > p.flag { grid-column: 1 / -1; }
.step > header { margin-bottom: 1.5mm; }
.step > figure { grid-column: 1; grid-row: 2; margin: 0 0 2mm; }
.step .cols { display: contents; }
.step .need { grid-column: 2; grid-row: 2; align-self: center; }
.step .do { grid-column: 1 / -1; grid-row: 3; }
.step h3 { font-size: 12pt; }
figure .pic { border: 0; text-align: center; }
figure svg { width: auto; max-width: 100%; max-height: 60mm; margin: 0 auto; }
figcaption { font-size: 7.8pt; margin-top: 1mm; gap: 1px 10px; }
.need ul, .do li { font-size: 8.6pt; }
.do li { margin-bottom: 0.2em; line-height: 1.36; }
dl.nums { grid-template-columns: 50mm minmax(0, 1fr); font-size: 8.2pt; padding: 1.5mm 3mm; margin-top: 1.5mm;
  gap: 0.6mm 4mm; }
.flag { font-size: 8.6pt; }
.flag.bench { background: var(--lamp); border-left-color: #c9a45c; }
.flag.bench::before { color: #8a6420; }
.gallery { grid-template-columns: repeat(5, 1fr); gap: 2.5mm; }
.gallery.hw { grid-template-columns: repeat(6, 1fr); }
.gallery.txt { grid-template-columns: repeat(4, 1fr); }
.gallery .card { font-size: 7.3pt; padding: 1.5mm; }
.gallery .card.txt { min-height: 13mm; }
.hwlist { break-before: page; }
.step.finale { display: block; break-before: page; border-top: 0; }
.step.finale figure svg { max-height: 165mm; }
.step.finale .need { display: none; }
.keep { break-inside: avoid; }
.hwlist h4 { margin-top: 4mm; }
table { font-size: 8.2pt; }
th, td { padding: 0.8mm 2mm; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
footer { break-before: avoid; break-inside: avoid; margin-top: 6mm; border-top: 1px solid #c5ccd6;
  padding-top: 2mm; font-size: 7.8pt; }
footer p { margin: 1mm 0; }
.status-chip { font-size: 7.5pt; }
"""


CSS = """
/* Layout: one reading column; each step is figure, then what you need, then what to do. */
:root {
  --bg: #f6f7f9; --paper: #ffffff; --fg: #1d2530; --muted: #5b6676; --rule: #d9dee6;
  --accent: #3d6a93; --accent-soft: #e4edf5; --warn: #8a4b08; --warn-bg: #fdf3e4; --warn-rule: #e9c48f;
  --bad: #9b1c1c; --bad-bg: #fdecec; --ok: #2f6b3a;
  --display: "Fraunces", Georgia, "Times New Roman", serif;
  --body: "IBM Plex Sans", -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12161c; --paper: #1a2029; --fg: #e3e8ef; --muted: #9aa6b6; --rule: #2e3846;
  --accent: #8fb4d6; --accent-soft: #223244; --warn: #f0c27a; --warn-bg: #2d2416; --warn-rule: #6b5124;
  --bad: #ff9b9b; --bad-bg: #351c1c; --ok: #8fd19e; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #12161c; --paper: #1a2029; --fg: #e3e8ef; --muted: #9aa6b6; --rule: #2e3846;
  --accent: #8fb4d6; --accent-soft: #223244; --warn: #f0c27a; --warn-bg: #2d2416; --warn-rule: #6b5124;
  --bad: #ff9b9b; --bad-bg: #351c1c; --ok: #8fd19e; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font: 16px/1.55 var(--body); margin: 0; }
.wrap { max-width: 920px; margin: 0 auto; padding-block: 32px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1, h2, h3 { font-family: var(--display); font-weight: 600; text-wrap: balance; line-height: 1.2; }
h1 { font-size: 2.3rem; margin: 0.2em 0 0.3em; }
h2 { font-size: 1.6rem; margin: 2.4em 0 0.4em; padding-top: 0.6em; border-top: 2px solid var(--fg); }
h3 { font-size: 1.2rem; margin: 0; }
h4 { font: 600 0.72rem/1.3 var(--body); letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 0.4em; }
p { max-width: 68ch; }
a { color: var(--accent); }
code { font: 0.88em var(--mono); background: var(--accent-soft); padding: 0.05em 0.3em; border-radius: 3px; }
.eyebrow { font: 600 0.78rem var(--body); letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); }
.lead { font-size: 1.08rem; color: var(--muted); }
nav.toc ol { columns: 2 220px; padding-left: 1.2em; margin: 0.5em 0; }
nav.toc li { break-inside: avoid; }
.step { background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; margin: 22px 0;
  padding: 18px; break-inside: avoid; }
.step header { display: flex; gap: 12px; align-items: baseline; margin-bottom: 12px; }
.step .no { font: 600 0.9rem var(--mono); color: var(--accent); min-width: 2.6em; }
figure { margin: 0 0 14px; }
figure .pic { background: #fff; border: 1px solid var(--rule); border-radius: 6px; overflow: hidden; }
figure svg { display: block; width: 100%; height: auto; }
figcaption { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 8px; font-size: 0.9rem; }
figcaption span { display: inline-flex; gap: 6px; align-items: center; }
.ball { display: inline-grid; place-items: center; width: 1.45em; height: 1.45em; border-radius: 50%;
  background: #2b4766; color: #fff; font: 600 0.78rem var(--body); flex: none; }
.cols { display: grid; grid-template-columns: minmax(0, 15rem) minmax(0, 1fr); gap: 18px; }
@media (max-width: 640px) { .cols { grid-template-columns: minmax(0, 1fr); } }
.need ul { list-style: none; padding: 0; margin: 0 0 12px; font-size: 0.92rem; }
.need li { padding: 3px 0; border-bottom: 1px dotted var(--rule); display: flex; justify-content: space-between; gap: 8px; }
.need li b { font: 600 0.85rem var(--mono); white-space: nowrap; }
.do ol { margin: 0; padding-left: 1.3em; }
.do li { margin-bottom: 0.45em; max-width: 68ch; }
dl.nums { display: grid; grid-template-columns: minmax(0, 14rem) minmax(0, 1fr); gap: 4px 14px;
  margin: 14px 0 0; padding: 10px 12px; background: var(--accent-soft); border-radius: 6px; font-size: 0.92rem;
  font-variant-numeric: tabular-nums; }
dl.nums dt { color: var(--muted); }
dl.nums dd { margin: 0; }
@media (max-width: 640px) { dl.nums { grid-template-columns: minmax(0, 1fr); } dl.nums dd { margin-bottom: 6px; } }
.flag { margin: 10px 0 0; padding: 8px 12px; border-left: 3px solid var(--warn-rule); background: var(--warn-bg);
  color: var(--fg); font-size: 0.92rem; border-radius: 0 6px 6px 0; max-width: none; }
.flag::before { content: "Open in the model: "; font-weight: 600; color: var(--warn); }
.flag.bench { border-left-color: var(--accent); background: var(--accent-soft); }
.flag.bench::before { content: "Check on the bench: "; color: var(--accent); }
.flag.bad { border-left-color: var(--bad); background: var(--bad-bg); }
.flag.bad::before { content: "Problem: "; color: var(--bad); }
.tbl { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { font: 600 0.75rem var(--body); letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
td.num { text-align: right; white-space: nowrap; }
.st-ok { color: var(--ok); } .st-no { color: var(--bad); font-weight: 600; }
.chips { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 0.88rem; }
.chips i { display: inline-block; width: 0.9em; height: 0.9em; border-radius: 2px; vertical-align: -0.1em;
  margin-right: 5px; border: 1px solid rgba(0,0,0,0.25); }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin: 8px 0 18px; }
.gallery .card { background: #fff; color: #1d2530; border: 1px solid var(--rule); border-radius: 6px; padding: 6px 8px 8px;
  font-size: 0.85rem; break-inside: avoid; }
.gallery .card img { display: block; width: 100%; height: auto; }
.gallery .card code { background: transparent; padding: 0; font-weight: 600; }
.gallery .card small { color: #5b6676; }
footer { margin-top: 48px; color: var(--muted); font-size: 0.85rem; }
/* Cover, section openers, labels */
.cover { padding-bottom: 8px; }
.cover .brandrow { flex-wrap: wrap; }
.status-chip { margin-left: auto; font: 600 0.74rem var(--mono); letter-spacing: 0.04em; color: var(--accent);
  border: 1px solid currentColor; border-radius: 999px; padding: 3px 10px; white-space: nowrap; }
.status-chip::before { content: ""; display: inline-block; width: 0.55em; height: 0.55em; border-radius: 50%;
  background: currentColor; margin-right: 0.5em; vertical-align: 0.05em; opacity: 0.8; }
h2 .secno { font: 600 2.6rem/1 var(--display); color: var(--accent); margin-right: 0.25em;
  font-variant-numeric: lining-nums; vertical-align: -0.12em; }
.intro { font-size: 1.05rem; color: var(--muted); font-style: italic; max-width: 64ch; margin-top: 0.2em; }
.lbl { font: 600 0.72rem/1.3 var(--body); letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted);
  margin: 0 0 0.4em; }
.step .no { display: inline-block; background: var(--accent); color: var(--paper); border-radius: 999px;
  padding: 1px 9px; min-width: 0; font: 600 0.8rem var(--mono); vertical-align: 0.15em; margin-right: 0.3em; }
.hwlist h4 { margin-top: 14px; text-transform: none; letter-spacing: 0; font: 600 0.95rem var(--display);
  color: var(--fg); }
.vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.gallery .card.txt { display: flex; flex-direction: column; justify-content: space-between; min-height: 64px;
  border-style: dashed; }
.gallery.txt { grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
p.small { font-size: 0.9rem; color: var(--muted); }
.coda { font-style: italic; margin: 10px 0 4px; }
@media print {
  body { background: #fff; color: #000; font-size: 11pt; }
  .wrap { max-width: none; padding: 0; }
  .step { border: none; padding: 0; margin: 0 0 18pt; break-inside: avoid; page-break-inside: avoid; }
  h2 { break-before: page; }
  nav.toc { break-after: page; }
}
"""


def _svg_figure(fig, img_href):
    W, H = fig["w"], fig["h"]
    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, html.escape(fig["name"])),
           '<image href="%s" x="0" y="0" width="%d" height="%d"/>' % (img_href, W, H)]
    for d in fig.get("dims", []):
        (ax, ay), (bx, by) = d["a"], d["b"]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L * d["off"], dx / L * d["off"]
        a2, b2 = (ax + nx, ay + ny), (bx + nx, by + ny)
        out.append('<g stroke="#9b1c1c" stroke-width="2" fill="none">'
                   '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/><line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"/>'
                   '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" marker-start="url(#ar)" marker-end="url(#ar)"/></g>'
                   % (ax, ay, a2[0] + nx * 0.15, a2[1] + ny * 0.15, bx, by, b2[0] + nx * 0.15, b2[1] + ny * 0.15,
                      a2[0], a2[1], b2[0], b2[1]))
        mx, my = (a2[0] + b2[0]) / 2, (a2[1] + b2[1]) / 2
        out.append('<text x="%.1f" y="%.1f" font-size="30" font-weight="700" fill="#9b1c1c" text-anchor="middle" '
                   'stroke="#fff" stroke-width="7" paint-order="stroke" font-family="Helvetica, Arial, sans-serif">'
                   '%s mm</text>' % (mx + (40 if nx >= 0 else -40) * (1 if abs(nx) > abs(ny) else 0),
                                     my + 10, html.escape(d["text"])))
    if fig.get("dims"):
        out.insert(1, '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" '
                      'markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#9b1c1c"/>'
                      '</marker></defs>')
    if fig.get("compass"):
        ux, uy = fig["compass"]
        cx, cy = 90, 100
        out.append('<g><circle cx="%d" cy="%d" r="52" fill="#fff" stroke="#2b4766" stroke-width="3"/>'
                   '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2b4766" stroke-width="6"/>'
                   '<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f z" fill="#2b4766"/>'
                   '<text x="%.1f" y="%.1f" font-size="30" font-weight="700" fill="#2b4766" text-anchor="middle" '
                   'font-family="Helvetica, Arial, sans-serif">N</text></g>'
                   % (cx, cy, cx - ux * 36, cy - uy * 36, cx + ux * 20, cy + uy * 20,
                      cx + ux * 42, cy + uy * 42, cx + ux * 14 - uy * 14, cy + uy * 14 + ux * 14,
                      cx + ux * 14 + uy * 14, cy + uy * 14 - ux * 14,
                      cx - ux * 32 - uy * 0, cy - uy * 32 + 10))
    if fig.get("text"):
        for b in layout_balloons(fig, r=22):
            ax, ay, x, y = b["ax"], b["ay"], b["bx"], b["by"]
            left = x < fig["w"] / 2
            tx = 14 if left else fig["w"] - 14
            ex = tx + (len(b["label"]) * 15.5 + 8) * (1 if left else -1)
            out.append('<g><line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2b4766" stroke-width="2.5"/>'
                       '<circle cx="%.1f" cy="%.1f" r="6" fill="#2b4766" stroke="#fff" stroke-width="2"/>'
                       '<text x="%.1f" y="%.1f" font-size="28" font-weight="700" fill="#1d2530" '
                       'text-anchor="%s" stroke="#fff" stroke-width="6" paint-order="stroke" '
                       'font-family="Helvetica, Arial, sans-serif">%s</text></g>'
                       % (ex, y, ax, ay, ax, ay, tx, y + 10, "start" if left else "end",
                          html.escape(b["label"])))
        out.append("</svg>")
        return "".join(out)
    for b in layout_balloons(fig):
        ax, ay, bxx, byy, r = b["ax"], b["ay"], b["bx"], b["by"], b["r"]
        dx, dy = ax - bxx, ay - byy
        L = math.hypot(dx, dy) or 1.0
        sx, sy = bxx + dx / L * r, byy + dy / L * r
        out.append('<g><line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#2b4766" stroke-width="2.5"/>'
                   '<circle cx="%.1f" cy="%.1f" r="6" fill="#2b4766" stroke="#fff" stroke-width="2"/>'
                   '<circle cx="%.1f" cy="%.1f" r="%d" fill="#2b4766" stroke="#fff" stroke-width="3"/>'
                   '<text x="%.1f" y="%.1f" font-size="%d" font-weight="700" fill="#fff" text-anchor="middle" '
                   'font-family="Helvetica, Arial, sans-serif">%d</text></g>'
                   % (sx, sy, ax, ay, ax, ay, bxx, byy, r, bxx, byy + r * 0.38, int(r * 1.1), b["n"]))
    out.append("</svg>")
    return "".join(out)


def _legend(fig):
    if fig.get("text"):
        return ""
    return "".join('<span><span class="ball">%d</span>%s</span>' % (i, html.escape(lab))
                   for i, lab in enumerate(fig["labels"], start=1) if lab in fig["anchors"])


def step_html(sec_no, k, st, fig, cat, href_prefix):
    sid = "s%d-%d" % (sec_no, k)
    h = ['<article class="step%s" id="%s"><header><h3><span class="no">%d.%d</span> %s</h3></header>'
         % (" finale" if getattr(st, "finale", False) else "", sid, sec_no, k, html.escape(st.title))]
    if fig:
        h.append('<figure><div class="pic">%s</div><figcaption>%s</figcaption></figure>'
                 % (_svg_figure(fig, href_prefix + fig["name"] + ".png"), _legend(fig)))
    need = []
    if st.printed:
        need.append('<p class="lbl">Printed</p><ul>' + "".join(
            "<li><span>%s</span><b>&times;%d</b></li>" % (c(nm), q) for nm, q in st.printed) + "</ul>")
    if st.hw:
        need.append('<p class="lbl">Hardware</p><ul>' + "".join(
            "<li><span>%s</span><b>&times;%d</b></li>" % (html.escape(cat[key][0]), q)
            for key, q in st.hw) + "</ul>")
    h.append('<div class="cols"><div class="need">%s</div><div class="do"><ol>%s</ol></div></div>'
             % ("".join(need) or '<p class="lbl">Nothing new</p>', "".join("<li>%s</li>" % d for d in st.do)))
    if st.nums:
        h.append('<dl class="nums">' + "".join("<dt>%s</dt><dd>%s</dd>" % (a, b) for a, b in st.nums)
                 + "</dl>")
    for f in st.flags:
        bad = f.startswith("<b>")
        h.append('<p class="flag%s">%s</p>' % (" bad" if bad else "", f))
    for f in st.bench:
        h.append('<p class="flag bench">%s</p>' % f)
    h.append("</article>")
    return "".join(h)


def totals_table(sections, cat):
    tot = {k: q for k, (q, _w) in hw_totals(sections).items()}
    bom = read_bom()
    used = set()
    rows = []
    for key in cat:
        if key not in tot:
            continue
        name, match = cat[key]
        need = order = ""
        status = ""
        if key in OWNED:
            status = '<span class="st-ok">already owned</span>'
        elif match is None:
            status = "&mdash;"
        else:
            hit = [r for r in bom if match.lower() in r[0].lower()]
            if not hit:
                status = '<span class="st-no">not in BOM tables</span>'
            else:
                used.add(hit[0][0])
                need, order = hit[0][1], hit[0][2]
                try:
                    ok = int(need) == tot[key]
                    status = ('<span class="st-ok">matches</span>' if ok else
                              '<span class="st-no">BOM says %s</span>' % html.escape(need))
                except ValueError:
                    status = html.escape(need)
        rows.append("<tr><td>%s</td><td class=num>%d</td><td class=num>%s</td><td class=num>%s</td><td>%s</td></tr>"
                    % (html.escape(name), tot[key], html.escape(need), html.escape(order), status))
    unused = [r for r in bom if r[0] not in used and any(ch.isdigit() for ch in r[1])]
    extra = ""
    if unused:
        extra = ("<p>Lines in <code>BOM.md</code> this guide never uses: " +
                 "; ".join("%s (need %s)" % (html.escape(r[0]), html.escape(r[1])) for r in unused) + ".</p>")
    return ('<div class="tbl"><table><thead><tr><th>Item</th><th>Guide</th><th>BOM need</th><th>BOM order</th>'
            '<th>Check</th></tr></thead><tbody>%s</tbody></table></div>%s' % ("".join(rows), extra))


def kit_table(sections):
    path = os.path.join(HERE, "out", "parts.json")
    with open(path, encoding="utf-8") as f:
        parts = json.load(f)["parts"]
    where = {}
    for no, (_sid, title, _i, steps) in enumerate(sections, start=1):
        for k, st in enumerate(steps, start=1):
            for nm, q in st.printed:
                where.setdefault(nm, []).append("%d.%d" % (no, k))
    names = {p["name"] for p in parts}
    missing = sorted(set(where) - names)
    if missing:
        raise SystemExit("guide names parts that are not in out/parts.json: %s" % ", ".join(missing))
    sw = {"white": ("#eeeeea", "white ASA"), "accent": ("#db6130", "accent ASA"), "tpu": ("#33849e", "TPU")}
    rows = "".join("<tr><td>%s</td><td class=num>%d</td><td><span class=chips><span><i style=\"background:%s\"></i>%s</span></span></td><td>%s</td></tr>"
                   % (c(p["name"]), p["qty"], sw[p["color"]][0], sw[p["color"]][1],
                      ", ".join(where.get(p["name"], ["<span class=st-no>not used</span>"])))
                   for p in parts)
    return ('<div class="tbl"><table><thead><tr><th>Part</th><th>Qty</th><th>Print in</th><th>Steps</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % rows)


def write_html(sections, figs, cat, n, path, href_prefix="assembly/", mode="screen"):
    toc = "".join('<li><a href="#%s">%s</a> <span style="color:var(--muted)">(%d)</span></li>'
                  % (sid, html.escape(t), len(st)) for sid, t, _i, st in sections)
    body = []
    for no, (sid, title, intro, steps) in enumerate(sections, start=1):
        # the space sits inside the title's span: with Fraunces, Chrome drops one between spans
        # from the PDF bookmark ("1Wind housing")
        body.append('<section id="%s"><h2><span class="secno">%d</span><span class="sect"> %s</span></h2>'
                    '<p class="intro">%s</p>' % (sid, no, html.escape(title), intro))
        for k, st in enumerate(steps, start=1):
            fig = figs.get(st.scene.name) if st.scene else None
            body.append(step_html(no, k, st, fig, cat, href_prefix))
        body.append("</section>")
    flags = []
    for no, (_sid, title, _i, steps) in enumerate(sections, start=1):
        for k, st in enumerate(steps, start=1):
            for f in st.flags:
                flags.append('<li><a href="#s%d-%d">%d.%d</a> %s</li>' % (no, k, no, k, f))
    bench = []
    for no, (_sid, title, _i, steps) in enumerate(sections, start=1):
        for k, st in enumerate(steps, start=1):
            for f in st.bench:
                bench.append('<li><a href="#s%d-%d">%d.%d</a> %s</li>' % (no, k, no, k, f))
    if flags:
        flags_html = ("<p>Things this guide could not take from <code>params.py</code>, <code>README.md</code> "
                      "or <code>BOM.md</code>. Each links to its step.</p><ul>%s</ul>" % "".join(flags))
    else:
        flags_html = ("<p>Nothing. Every step's parts, hardware and numbers come from the model, and "
                      "<code>build.py</code>'s fit checks pass. What remains is for the bench.</p>")
    if bench:
        flags_html += ("<h3>Checks only the real parts can answer</h3><p>A model can be argued with "
                       "forever. Plastic settles it in an afternoon.</p><ul>%s</ul>" % "".join(bench))
    flags = [flags_html]
    ov = figs.get("overview")
    chips = "".join('<span><i style="background:rgb(%d,%d,%d)"></i>%s</span>'
                    % (tuple(int(v * 255) for v in COL[k]) + (t,))
                    for k, t in (("white", "white ASA"), ("accent", "accent ASA (vane, cups)"),
                                 ("tpu", "TPU seals"), ("steel", "screws, nuts, bearings"),
                                 ("brass", "heat-set inserts"), ("magnet", "magnets"),
                                 ("pcb", "circuit boards"), ("alu", "2020 profile")))
    stamp = time.strftime("%Y-%m-%d %H:%M")
    doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Forsyth Station Assembly Guide</title>
<meta name="author" content="Starstuck Lab">
<meta name="description" content="Assembly guide for the Forsyth weather station's 3D-printed outdoor kit.">
<meta name="claude:viewport-fit-sides" content="cover">
%(fonts)s<style>%(css)s</style></head><body><div class="wrap">
<header class="cover">
<div class="brandrow">%(mark_f)s<p class="eyebrow">Forsyth weather station &middot; printed kit</p>
<span class="status-chip">Station 000 &middot; Expecting rain</span></div>
<h1>Assembly guide</h1>
<p class="lead">The printed kit for a Forsyth station, put together in order: wind kit, rain gauge, Stevenson
screen, core box, solar bracket and sky pod, and then all of it onto a 2020 mast. Every picture is drawn from the
parametric model and every number is read from <code>params.py</code>, so the guide is exactly as right as the
model. Lengths are in millimetres. The weather has waited this long; it can wait for the glue to set.</p>
%(overview)s
<nav class="toc"><p class="lbl">Contents</p><ol><li><a href="#parts">Parts at a glance</a></li><li><a href="#start">Before you start</a></li>%(toc)s<li><a href="#open">Left open by the model</a></li>
<li><a href="#hardware">Hardware against BOM.md</a></li><li><a href="#kit">Printed parts</a></li></ol></nav>
</header>
<h2 id="parts"><span class="sect">Parts at a glance</span></h2>
<p class="intro">Every printed part and every piece of hardware the steps use, drawn on its own and named. Lay
the kit out on the bench and tick it off before starting. A missing screw is cheaper to find now than at step 10.</p>
%(gallery)s
<h2 id="start"><span class="sect">Before you start</span></h2>
<p class="intro">Read each step's picture first. Parts added in that step are drawn in full colour with numbered
balloons; parts already fitted are drawn pale. Dashed lines show which way a part goes in.</p>
<div class="chips">%(chips)s</div>
<h3 style="margin-top:1.2em">Tools</h3>
<ul><li>Hex keys: 2.5 mm (M3 socket heads), 3 mm (M4 socket heads and M5 button heads), 4 mm (the M5 rotor shafts).</li>
<li>Spanners: 5.5 mm (M3 nyloc), 7 mm (M4), 8 mm (M5), and whatever fits your gland and GX socket nuts.</li>
<li>A soldering iron with a heat-set insert tip, or a plain tip you do not mind dedicating to it.</li>
<li>Epoxy or CA glue for the magnets, silicone, a spirit level, a multimeter for checking reed switches, and a measuring syringe or jug for the rain calibration.</li>
<li>99%% isopropyl alcohol, a small jar and a few drops of light oil, for the cup bearings (step 1.2).</li></ul>
<h3>Heat-set inserts</h3>
<p>There are %(n_ins)d of them (M3 x %(ins_l)s, 4.2 mm across). Each pilot hole is &Oslash;%(pilot)s, at least
%(ins_l)s mm deep. Set the insert on the hole, press it straight down with the hot iron until its top is flush,
lift the iron straight off and hold the part still for a few seconds. Print a test coupon first: a different insert
needs <code>m3_insert_d</code> and <code>m3_insert_l</code> changed.</p>
<h3>Self-tapping screws</h3>
<p>Screws that go into plain &Oslash;%(tap)s pilot holes (cup hub cap, rain stops and funnel, sky pod head) cut
their own thread. Drive them slowly, stop when the part is tight, and do not take them in and out more than you have to.
Plastic forgives once, sometimes twice.</p>
<h3>Bearings</h3>
<p>Four shielded ball bearings carry the two rotors. The pair under the cups is cleaned of its grease and lightly oiled
before it goes in (step 1.2): grease that suits a skateboard wheel is too much for a light breeze. The pair in the
lid stays as it came. Keep the shields on, and keep the cleaned pair oiled: bare steel outdoors starts to rust
within hours.</p>
<h3>Mounting screws</h3>
<p>Every foot and tab takes M5 button heads with a washer (about 1 mm) into M5 profile nuts in the 2020's slot.
Each foot has four holes in a cross: use the two that land on the slot.</p>
%(body)s
<h2 id="open"><span class="sect">Left open by the model</span></h2>
%(flags)s
<h2 id="hardware"><span class="sect">Hardware against BOM.md</span></h2>
<p class="intro">What the steps above use, added up, beside the &ldquo;Need&rdquo; column of <code>BOM.md</code>.
Items marked already owned are left out of the BOM on purpose.</p>
%(totals)s
<h2 id="kit"><span class="sect">Printed parts</span></h2>
<p class="intro">From <code>out/parts.json</code>, with the steps that use each one.</p>
%(kit)s
<footer><div class="made">%(mark_sl)s<span>Forsyth is a <a href="https://starstucklab.com">starstucklab</a> project.</span></div>
<p class="coda">Somewhere above the mast the weather carries on, unaware it is about to be written down.</p>
<p>Generated %(stamp)s by <code>assembly.py</code> from <code>params.py</code>. Rebuild with <code>./build.sh</code>;
do not edit this file by hand.</p></footer>
</div></body></html>
""" % {"css": (CSS if mode == "screen" else print_css()) + LOGO_CSS, "toc": toc,
       "mark_f": logos()[0], "mark_sl": logos()[1], "body": "".join(body), "flags": "".join(flags),
       "gallery": gallery_html(figs, href_prefix, json.load(open(os.path.join(HERE, "out", "parts.json"), encoding="utf-8"))["parts"],
                               sections, cat),
       "fonts": FONTS,
       "totals": totals_table(sections, cat), "kit": kit_table(sections), "stamp": stamp, "chips": chips,
       "n_ins": sum(q for _s, _t, _i, st in sections for s_ in st for key, q in s_.hw if key == "insert"),
       "ins_l": fmt(P.m3_insert_l), "pilot": fmt(P.m3_insert_d), "tap": fmt(P.m3_tap_d),
       "overview": ('<figure class="over"><div class="pic">%s</div><figcaption>%s</figcaption></figure>'
                    % (_svg_figure(ov, href_prefix + "overview.png"), _legend(ov))) if ov else ""}
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


# =========================================================== parts gallery ===
CONSUMABLE = ("epoxy", "silicone", "ipa", "oil")   # one tube or bottle however many steps use it


def hw_totals(sections):
    """catalogue key -> (total quantity, ["1.2", "3.1", ...]) over every step, in step order.
    Consumables count once (the most any step asks for), not once per step."""
    tot = {}
    for no, (_sid, _t, _i, steps) in enumerate(sections, start=1):
        for k, st in enumerate(steps, start=1):
            for key, q in st.hw:
                qq, where = tot.get(key, (0, []))
                ref = "%d.%d" % (no, k)
                qq = max(qq, q) if key in CONSUMABLE else qq + q
                tot[key] = (qq, where + ([ref] if ref not in where else []))
    return tot


def hw_model(key, n):
    """(shape, colour) for a catalogue item's gallery picture, lying down; None if it has no model."""
    screw = lambda s: ry(s, 90)                               # along X: long screws fill the card
    m = {
        "brg": (hw_bearing(P.brg_id, P.brg_od, P.brg_w), "steel"),
        "shaft": (screw(hw_shcs(5, P.shaft_len, P.shaft_head_d, P.shaft_head_h)), "steel"),
        "m5x25": (screw(hw_shcs(5, 25)), "steel"),
        "m5x12": (screw(hw_button(5, 12)), "steel"),
        "m5x10": (screw(hw_button(5, 10)), "steel"),
        "m5x8": (screw(hw_button(5, 8)), "steel"),
        "m5nut": (hw_nut(P.m5_nut_af, P.m5_nut_h, 5.0), "steel"),
        "washer": (hw_washer(5.3, 10.0, 1.0), "steel"),
        "tnut": (hw_tnut(), "steel"),
        "m3x8": (screw(hw_shcs(3, 8)), "steel"),
        "m3x10": (screw(hw_shcs(3, 10)), "steel"),
        "m3x6": (screw(hw_shcs(3, 6)), "steel"),
        "m3x16": (screw(hw_shcs(3, n.get("stop_len", 16))), "steel"),
        "axle": (screw(hw_shcs(3, n["axle"])), "steel"),
        "nyloc": (hw_nut(5.5, 4.0, 3.0), "steel"),
        "insert": (hw_insert(4.2, P.m3_insert_l), "brass"),
        "mag6": (hw_magnet(P.mag_d, P.mag_t), "magnet"),
        "mag4": (hw_magnet(P.rain_mag_d, P.rain_mag_t), "magnet"),
        "m4": (screw(hw_shcs(4, n["scr_screw"])), "steel"),
        "m4nut": (hw_nut(7.0, 3.2, 4.0), "steel"),
        "gland": (hw_gland(), "white"),
        "bracket": (fuse([box(-10, 10, 0, 20, 0, 3), box(-10, 10, 0, 3, 0, 20)]), "steel"),
        "reed": (fuse(list(hw_reed(P.reed_l - 0.5, 2.0, 9.0))), "glass"),
    }
    for k in ("gx16_8", "gx16_5"):
        m[k] = (hw_gx(P.gx16_d, P.gx16_flange), "steel")
    for k in ("gx12_2", "gx12_3", "gx12_4"):
        m[k] = (hw_gx(P.gx12_d, P.gx12_flange), "steel")
    return m.get(key)


def gallery_scenes(parts, sections=(), n=None):
    """One small picture per printed part (as used, where that reads better than
    the print orientation) and per bought-in hardware item the steps use."""
    use = {"vane_rotor": wind.vane_rotor_use(), "rain_funnel": rain.funnel_use(),
           "screen_cap": screen.cap_use(), "sky_head": sky.head_local(), "sky_mount": sky.mount_use(),
           "enclosure_lid": enclosure.lid_use(), "cup_hub": flip(parts["cup_hub"]),
           "solar_bracket": rz(rx(parts["solar_bracket"], 90), 180)}
    with open(os.path.join(HERE, "out", "parts.json"), encoding="utf-8") as f:
        names = [p["name"] for p in json.load(f)["parts"]]
    out = []
    for nm in names:
        sh = use.get(nm, parts[nm])
        sc = Scene("part-" + nm, [Item(sh, printed_color(nm))], view=(0.9, -1.2, 1.0),
                   size=(480, 360), margin=0.04)
        out.append(sc)
    seen = set()
    for key in hw_totals(sections):
        mdl = hw_model(key, n)
        if not mdl:
            continue
        sh, col = mdl
        name = "hw-gx16" if key.startswith("gx16") else "hw-gx12" if key.startswith("gx12") else "hw-" + key
        if name in seen:
            continue
        seen.add(name)
        out.append(Scene(name, [Item(sh, col)], view=(0.9, -1.2, 0.9), size=(360, 300), margin=0.08))
    return out


HW_GROUPS = (("Screws, nuts and washers", ("shaft", "m5x25", "m5x12", "m5x10", "m5x8", "m4", "axle", "m3x16",
                                             "m3x10", "m3x8", "m3x6", "m5nut", "m4nut", "nyloc", "washer", "tnut",
                                             "insert")),
             ("Bearings, magnets and switches", ("brg", "mag6", "mag4", "reed")),
             ("Connectors and frame", ("gland", "gx16_8", "gx16_5", "gx12_2", "gx12_3", "gx12_4", "bracket")),
             ("Cables", ("cable5", "cable8", "cable4", "cable3", "cable2")))


def _steps_ref(where):
    return "step%s %s" % ("s" if len(where) > 1 else "", ", ".join(where))


def gallery_html(figs, href_prefix, parts_json, sections=(), cat=None):
    """Printed parts, then every bought-in item the steps use, grouped, with totals and steps.
    Generated from the steps, so nothing a step uses can be missing here."""
    used = {}
    for no, (_sid, _t, _i, steps) in enumerate(sections, start=1):
        for k, st in enumerate(steps, start=1):
            for nm, _q in st.printed:
                used.setdefault(nm, [])
                if "%d.%d" % (no, k) not in used[nm]:
                    used[nm].append("%d.%d" % (no, k))
    cards = []
    for p in parts_json:
        f = figs.get("part-" + p["name"])
        if not f:
            continue
        cards.append('<div class="card"><img src="%s%s.png" alt="%s" loading="lazy">'
                     '<div><code>%s</code> <b>&times;%d</b></div><small>%s &middot; %s</small></div>'
                     % (href_prefix, f["name"], p["name"], p["name"], p["qty"],
                        {"white": "white ASA", "accent": "accent ASA", "tpu": "TPU"}[p["color"]],
                        _steps_ref(used.get(p["name"], ["not used"]))))
    tot = hw_totals(sections)
    blocks, done = [], set()

    def card(key, img=True):
        name = cat[key][0]
        q, where = tot[key]
        sc = "hw-gx16" if key.startswith("gx16") else "hw-gx12" if key.startswith("gx12") else "hw-" + key
        pic = ('<img src="%s%s.png" alt="" loading="lazy">' % (href_prefix, sc)) if img and sc in figs else ""
        done.add(key)
        return ('<div class="card%s">%s<div>%s <b>&times;%d</b></div><small>%s</small></div>'
                % ("" if pic else " txt", pic, html.escape(name), q, _steps_ref(where)))
    for title, keys in HW_GROUPS:
        row = "".join(card(k) for k in keys if k in tot)
        if row:
            blocks.append('<div class="keep"><h4>%s</h4><div class="gallery hw">%s</div></div>' % (title, row))
    owned = [k for k in tot if k in OWNED]
    rest = [k for k in tot if k not in done and k not in OWNED]
    if rest:
        blocks.append('<div class="keep"><h4>Glue, foam and the rest</h4><div class="gallery hw txt">%s</div></div>'
                      % "".join(card(k, img=False) for k in rest))
    if owned:
        blocks.append('<div class="keep"><h4>Electronics and parts already on the bench</h4>'
                      '<div class="gallery hw txt">%s</div></div>' % "".join(card(k, img=False) for k in owned))
    return ('<h3>Printed parts</h3><div class="gallery">%s</div>'
            '<section class="hwlist"><h3>Bought-in hardware</h3><p class="small">Every item the steps use, '
            'added up. The same totals sit against <code>BOM.md</code> at the back.</p>%s</section>'
            % ("".join(cards), "".join(blocks)))


# =================================================================== logos ===
def logos():
    """(Forsyth mark, starstucklab mark) as inline SVG. The Forsyth mark is read from the
    project site, the starstucklab one from a cleaned copy kept beside the app template."""
    root = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
    out = []
    for path, cls in ((os.path.join(root, "site", "assets", "mark.svg"), "mark-f"),
                      (os.path.join(HERE, "templates", "starstucklab-mark.svg"), "mark-sl")):
        try:
            with open(path, encoding="utf-8") as f:
                svg = f.read()
        except OSError:
            out.append("")
            continue
        svg = svg[svg.index("<svg"):]
        out.append(svg.replace("<svg ", '<svg class="%s" aria-hidden="true" focusable="false" ' % cls, 1))
    return out


LOGO_CSS = """
.brandrow { display: flex; align-items: center; gap: 10px; }
.mark-f { width: 2.4rem; height: 2.4rem; flex: none; }
.mark-sl { width: 1.35rem; height: 1.35rem; flex: none; color: var(--fg); }
.mark-sl .sl-sprout { fill: var(--bg); }
.made { display: flex; align-items: center; gap: 8px; margin-top: 10px; color: var(--muted); }
.made a { color: inherit; }
"""


# ================================================= records, app and print ===
# What a builder writes down at a step: (key, label, unit). The app stores these
# per build, and the tracking sheet prints a blank for each.
RECORDS = {
    "wind-02-bearings": [("fit", "Bearing fit in the housing (snug / loose / tight)", "")],
    "vane-01-lid": [("fit", "Bearing fit in the lid (snug / loose / tight)", "")],
    "cups-03-shaft": [("spin", "Cups coast after a flick", "s")],
    "vane-04-balance": [("nuts", "Ballast nuts used", "pcs"), ("mass", "Ballast mass", "g")],
    "close-01-pcb": [("north", "PCB reed marked as north", "")],
    "close-02-lid": [("anemo", "Anemometer closures per turn", ""),
                     ("vane", "Vane reeds that close", "of 8")],
    "rain-05-section": [("ml", "Water poured", "ml"), ("tips", "Tips counted", "")],
    "sky-01-exploded": [("can", "Letters on the sensor can", "")],
    "box-03-board": [("ant", "Antenna measured: elbow / diameter / length", "mm")],
    "mast-06-finished": [("up", "Date the station went up", ""), ("north", "Face pointing north", "")],
}


def export_steps(sections, figs, cat, href_prefix="assembly/"):
    """Everything the app and the tracking sheet need, as plain data."""
    out = []
    for no, (sid, title, intro, steps) in enumerate(sections, start=1):
        sec = {"id": sid, "no": no, "title": title, "intro": intro, "steps": []}
        for k, st in enumerate(steps, start=1):
            fig = figs.get(st.scene.name) if st.scene else None
            sec["steps"].append({
                "id": st.scene.name if st.scene else "%s-%d" % (sid, k),
                "no": "%d.%d" % (no, k), "title": st.title,
                "svg": _svg_figure(fig, href_prefix + fig["name"] + ".png") if fig else "",
                "legend": [lab for lab in fig["labels"] if lab in fig["anchors"]] if fig else [],
                "printed": [[nm, q] for nm, q in st.printed],
                "hw": [[cat[key][0], q] for key, q in st.hw],
                "do": list(st.do), "nums": [list(x) for x in st.nums],
                "flags": [{"html": f, "bad": f.startswith("<b>")} for f in st.flags]
                + [{"html": f, "bench": True} for f in st.bench],
                "record": [list(r) for r in RECORDS.get(st.scene.name if st.scene else "", [])],
            })
        out.append(sec)
    with open(os.path.join(HERE, "out", "parts.json"), encoding="utf-8") as f:
        parts = json.load(f)["parts"]
    where = hw_totals(sections)
    tot = {k: q for k, (q, _w) in where.items()}
    hw = [{"name": cat[k][0], "qty": q, "owned": k in OWNED, "where": where[k][1]} for k, q in tot.items()]
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "rain_ml_per_mm": round(P.rain_area_cm2 / 10, 3),
            "sections": out, "parts": [{"name": p["name"], "qty": p["qty"], "color": p["color"],
                                        "material": p["material"]} for p in parts],
            "hardware": sorted(hw, key=lambda h: (h["owned"], h["name"])),
            "overview": _svg_figure(figs["overview"], href_prefix + "overview.png") if "overview" in figs else ""}


def write_app(data, path):
    tpl = os.path.join(HERE, "templates", "assembly-app.html")
    with open(tpl, encoding="utf-8") as f:
        page = f.read()
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*STEPS_JSON*/null", blob)
    mark_f, mark_sl = logos()
    page = page.replace("<!--FORSYTH_MARK-->", mark_f).replace("<!--SL_MARK-->", mark_sl)
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


SHEET_CSS = """
/* Layout: A4 form, ruled tables to fill in by hand. */
:root { --fg: #111; --muted: #555; --rule: #888; --light: #c9ced6; --head: #e9edf2; --accent: #2b4766; }
@page { size: A4; margin: 12mm 12mm 14mm; }
* { box-sizing: border-box; }
body { background: #fff; color: var(--fg); font: 9pt/1.35 "Helvetica Neue", Helvetica, Arial, sans-serif; margin: 0; }
.wrap { max-width: 186mm; margin: 0 auto; padding-block: 16px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1 { font: 600 18pt Georgia, serif; margin: 0 0 1mm; }
h2 { font: 600 12pt Georgia, serif; margin: 6mm 0 2mm; padding-top: 1mm; border-top: 1.5px solid var(--fg); }
h2.page { break-before: page; }
p.note { color: var(--muted); margin: 0 0 2mm; max-width: none; }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 3mm 8mm; margin: 4mm 0; }
.fields div { border-bottom: 1px solid var(--rule); padding-top: 6mm; font-size: 8pt; color: var(--muted); }
.tbl { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th { background: var(--head); text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 1.5mm 1.5mm; border: 1px solid var(--rule); }
td { border: 1px solid var(--rule); padding: 1.2mm 1.5mm; vertical-align: top; height: 7.5mm; }
tr { break-inside: avoid; page-break-inside: avoid; }
tr.sec td { background: var(--head); font-weight: 600; height: auto; }
td.no { width: 9mm; font-family: Menlo, monospace; font-size: 8pt; }
td.box, th.box { width: 9mm; text-align: center; }
td.date { width: 18mm; } td.who { width: 13mm; }
.b { display: inline-block; width: 3.6mm; height: 3.6mm; border: 1.2px solid var(--fg); border-radius: 0.6mm;
  vertical-align: -0.6mm; margin-right: 0.8mm; }
.rec { display: block; font-size: 7.5pt; color: var(--muted); margin-top: 1mm; }
.rec i { display: inline-block; min-width: 22mm; border-bottom: 1px solid var(--light); margin: 0 1mm; }
td.thumb { width: 15mm; padding: 0.3mm; } td.thumb img { width: 14.5mm; height: auto; display: block; }
tr.part td { height: auto; }
code { font: 8pt Menlo, monospace; }
.warn td { background: #fdecec; }
.calc { font-size: 8pt; color: var(--muted); }
footer { margin-top: 6mm; color: var(--muted); font-size: 7.5pt; }
"""


def write_sheet(data, path, href_prefix="assembly/"):
    """A paper record to fill in by hand: parts, hardware, every step, the bench results."""
    b = '<span class="b"></span>'
    e = html.escape
    rows = []
    for p in data["parts"]:
        rows.append('<tr class="part"><td class="thumb"><img src="%spart-%s.png" alt=""></td><td><code>%s</code></td><td>%s</td>'
                    '<td class="box">%d</td><td>%s</td><td class="box">%s</td><td></td></tr>'
                    % (href_prefix, p["name"], e(p["name"]),
                       {"white": "white ASA", "accent": "accent ASA", "tpu": "TPU"}[p["color"]], p["qty"],
                       b * p["qty"], b))
    parts = "".join(rows)
    hw = "".join('<tr><td>%s</td><td class="box">%d</td><td class="box">%s</td><td>%s</td></tr>'
                 % (e(h["name"]), h["qty"], b, "already owned" if h["owned"] else "")
                 for h in data["hardware"])
    steps = []
    for sec in data["sections"]:
        steps.append('<tr class="sec"><td colspan="6">%d. %s</td></tr>' % (sec["no"], e(sec["title"])))
        for st in sec["steps"]:
            rec = "".join('<span class="rec">%s<i></i>%s</span>' % (e(lab), e(unit)) for _k, lab, unit in st["record"])
            warn = any(f.get("bad") for f in st["flags"])
            steps.append('<tr%s><td class="no">%s</td><td>%s%s%s</td><td class="box">%s</td><td class="date"></td>'
                         '<td class="who"></td><td></td></tr>'
                         % (' class="warn"' if warn else "", st["no"], e(st["title"]),
                            ' <b>(see the problem in the guide first)</b>' if warn else "", rec, b))
    bad = [(st["no"], st["title"], f["html"]) for sec in data["sections"] for st in sec["steps"]
           for f in st["flags"] if f.get("bad")]
    issues = "".join('<tr><td class="no">%s</td><td>%s</td><td class="box">%s</td><td></td></tr>'
                     % (no, f, b) for no, _t, f in bad)
    mlmm = data["rain_ml_per_mm"]
    doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Forsyth Assembly Record</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>%(css)s</style></head><body><div class="wrap">
<div class="brandrow">%(mark_f)s<h1>Forsyth station: assembly record</h1></div>
<p class="note">Fill this in as you build. Step numbers match the assembly guide. Pencil is fine; the weather
will not check the handwriting. Generated %(gen)s from <code>params.py</code>.</p>
<div class="fields"><div>Station / build name</div><div>Builder</div><div>Started</div><div>Finished</div></div>
<h2>Before you start: blocking problems in the model</h2>
<div class="tbl"><table><thead><tr><th>Step</th><th>Problem</th><th class="box">Fixed</th><th>How</th></tr></thead>
<tbody>%(issues)s</tbody></table></div>
<h2>Printed parts</h2>
<p class="note">Tick one box per copy printed, then one when its fit has been checked.</p>
<div class="tbl"><table><thead><tr><th></th><th>Part</th><th>Print in</th><th class="box">Qty</th><th>Printed</th>
<th class="box">Fit</th><th>Notes</th></tr></thead><tbody>%(parts)s</tbody></table></div>
<h2 class="page">Hardware on hand</h2>
<div class="tbl"><table><thead><tr><th>Item</th><th class="box">Qty</th><th class="box">Have</th><th>Notes</th></tr></thead>
<tbody>%(hw)s</tbody></table></div>
<h2 class="page">Assembly steps</h2>
<p class="note">Write down what each step asks you to measure; the app keeps the same fields.</p>
<div class="tbl"><table><thead><tr><th>Step</th><th>What</th><th class="box">Done</th><th>Date</th><th>Initials</th>
<th>Notes</th></tr></thead><tbody>%(steps)s</tbody></table></div>
<h2 class="page">Bench results</h2>
<div class="tbl"><table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>
<tr><td>Rain: water poured (ml) and tips counted</td><td></td></tr>
<tr><td>Rain: ml per tip = poured / tips<br><span class="calc">mm per tip = ml per tip / %(mlmm)s</span></td><td></td></tr>
<tr><td>Anemometer: drill test, closures per second against wind speed (for <code>ANEMO_MS_PER_HZ_X1000</code>)</td><td></td></tr>
<tr><td>Vane: magnet closes one reed (or two between sectors), never three</td><td></td></tr>
<tr><td>Box lid: bows between screws? (lower <code>gasket_squeeze</code> if so)</td><td></td></tr>
<tr><td>Antenna: RSSI with the lid on and off, same distance</td><td></td></tr>
<tr><td>Sky sensor: reading against the screen's air temperature</td><td></td></tr>
<tr><td>Mast: which face points north; box antenna end toward the coordinator</td><td></td></tr>
</tbody></table></div>
<footer><div class="made">%(mark_sl)s<span>Forsyth is a starstucklab project &middot; starstucklab.com</span></div>
Forsyth station mechanicals. Regenerated with <code>./build.sh</code>; do not edit by hand.</footer>
</div></body></html>
""" % {"css": SHEET_CSS + LOGO_CSS.replace("var(--bg)", "#fff"), "gen": data["generated"],
       "mark_f": logos()[0], "mark_sl": logos()[1], "issues": issues or "<tr><td colspan=4>None</td></tr>",
       "parts": parts, "hw": hw, "steps": "".join(steps), "mlmm": fmt(mlmm, 2)}
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


LANDING_CSS = """
/* Layout: one centred column; the tracker is the one primary action, the guide and PDFs sit beside it. */
:root { --bg: #f4f6f8; --paper: #ffffff; --fg: #1b2430; --muted: #5a6575; --rule: #d7dde5;
  --accent: #33597f; --accent-fg: #ffffff; --accent-soft: #e3ecf5;
  --display: "Fraunces", Georgia, serif; --body: "IBM Plex Sans", -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11151b; --paper: #1a2029; --fg: #e3e8ef; --muted: #9aa6b6; --rule: #2d3745;
  --accent: #8fb4d6; --accent-fg: #0f1823; --accent-soft: #213246; color-scheme: dark; } }
:root[data-theme="dark"] { --bg: #11151b; --paper: #1a2029; --fg: #e3e8ef; --muted: #9aa6b6; --rule: #2d3745;
  --accent: #8fb4d6; --accent-fg: #0f1823; --accent-soft: #213246; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.55 var(--body); }
.wrap { max-width: 860px; margin: 0 auto; padding-block: 40px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.brandrow { display: flex; align-items: center; gap: 12px; }
.mark-f { width: 2.8rem; height: 2.8rem; flex: none; }
.mark-sl { width: 1.35rem; height: 1.35rem; flex: none; color: var(--fg); }
.mark-sl .sl-sprout { fill: var(--bg); }
.eyebrow { font: 600 0.78rem var(--body); letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); margin: 0; }
h1 { font: 600 2.4rem/1.1 var(--display); margin: 18px 0 10px; text-wrap: balance; }
.lead { color: var(--muted); font-size: 1.08rem; max-width: 62ch; margin: 0 0 22px; }
.cta { display: inline-block; background: var(--accent); color: var(--accent-fg); text-decoration: none; font-weight: 600;
  padding: 11px 18px; border-radius: 8px; }
.cta:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.note { color: var(--muted); font-size: 0.9rem; margin: 10px 0 0; }
figure { margin: 28px 0; background: #fff; border: 1px solid var(--rule); border-radius: 10px; overflow: hidden; }
figure img { display: block; width: 100%; height: auto; }
.docs { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.docs a { display: grid; gap: 4px; padding: 14px 16px; background: var(--paper); border: 1px solid var(--rule); border-radius: 8px;
  color: var(--fg); text-decoration: none; }
.docs a b { font-weight: 600; color: var(--accent); }
.docs a span { color: var(--muted); font-size: 0.9rem; }
.facts { display: flex; flex-wrap: wrap; gap: 6px 22px; color: var(--muted); font-size: 0.9rem; margin: 22px 0 0;
  font-variant-numeric: tabular-nums; }
footer { display: flex; align-items: center; gap: 8px; margin-top: 40px; color: var(--muted); font-size: 0.88rem; }
footer a { color: inherit; }
"""


def write_landing(data, path):
    """The public front page of build.forsyth.starstucklab.com."""
    mark_f, mark_sl = logos()
    n_steps = sum(len(s["steps"]) for s in data["sections"])
    n_parts = sum(p["qty"] for p in data["parts"])
    doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Forsyth Station Builds</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Assembly guide and build tracker for the Forsyth weather station's printed kit.">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
%(fonts)s<style>%(css)s</style></head><body><div class="wrap">
<div class="brandrow">%(mark_f)s<p class="eyebrow">Forsyth weather station</p></div>
<h1>Build a station</h1>
<p class="lead">The printed kit for a Forsyth station: wind vane and cups, rain gauge, Stevenson screen,
core box, solar bracket and sky pod, on a 2020 mast. The guide walks every step with pictures drawn from the
model. The tracker keeps a build's progress, step by step, and shares it with whoever is holding the other end
of the mast. The sky will be measured eventually. There is no rush.</p>
<a class="cta" href="/app/">Open the build tracker</a>
<p class="note">The tracker asks you to sign in with your email, so your builds stay yours. The guide and PDFs need no account.</p>
<figure><img src="assembly/overview.png" alt="The whole station on its mast: wind kit and sky pod at the top, Stevenson screen and rain gauge on the crossarm, solar panel and core box below." width="1100" height="1400"></figure>
<div class="docs">
  <a href="assembly.html"><b>Assembly guide</b><span>Every step, part and number, for a phone or a desk.</span></a>
  <a href="forsyth-assembly-guide.pdf"><b>Guide, A4 PDF</b><span>The same guide, to print.</span></a>
  <a href="forsyth-assembly-record.pdf"><b>Record sheet, A4 PDF</b><span>Tick boxes and blanks to fill in by hand.</span></a>
</div>
<p class="facts"><span>%(steps)d steps in %(secs)d sections</span><span>%(parts)d printed parts</span><span>Updated %(gen)s</span></p>
<footer>%(mark_sl)s<span>Forsyth is a <a href="https://starstucklab.com">starstucklab</a> project &middot;
<a href="https://forsyth.starstucklab.com">forsyth.starstucklab.com</a> &middot;
<a href="https://live.forsyth.starstucklab.com">live data</a></span></footer>
</div></body></html>
""" % {"fonts": FONTS, "css": LANDING_CSS, "mark_f": mark_f, "mark_sl": mark_sl, "steps": n_steps,
       "secs": len(data["sections"]), "parts": n_parts, "gen": data["generated"][:10]}
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


# ==================================================================== main ===
def sections_for(parts, n):
    w = wind_steps(parts, n)
    return [
        ("wind-housing", "Wind housing",
         "The housing carries both wind sensors: the cups hang from bearings in its floor and the vane "
         "turns on its lid. Build the bottom half here. The README says to print %s first and check that a "
         "bearing fits its pocket before printing the body. The housing has no opinion about the wind; "
         "it only has to stay dry while finding out." % c("wind_lid"), w["housing"]),
        ("anemometer", "Anemometer",
         "Three cups on a hub, clamped to an M5 x %g screw that turns in the floor tower's bearings. "
         "It will count every gust, including the ones nobody asked about." %
         P.shaft_len, w["cups"]),
        ("vane", "Wind vane",
         "The vane turns on two more bearings in the lid, on a second M5 x %g put in from under the lid. "
         "The lid and vane come off the housing together: the screw head is the one fastener that "
         "passes the vane PCB's centre hole. The vane points at where the wind comes from, which is "
         "more than most things in the lab can say." % P.shaft_len, w["vane"]),
        ("wind-close", "Closing the wind kit",
         "The vane PCB, its ring, the gasket and the lid with the vane on it. Once it is shut, the reeds "
         "do their work in the dark.", w["close"]),
        ("rain", "Rain gauge",
         "A tipping bucket under a %s funnel. Each tip is a small, exact receipt from the sky." %
         mm(P.rain_collector_d, 0), rain_steps(parts, n)),
        ("screen", "Stevenson screen",
         "%d louvres and a cap on a spoked base, clamped by three M4 x %d screws. Board B slides into rails "
         "on the base; the lightning module hangs under the cap. It keeps the sun off the sensors, a "
         "courtesy the sun does not return." % (P.scr_plates, n["scr_screw"]),
         screen_steps(parts, n)),
        ("box", "Core box",
         "Board A and a loose cell in a sealed box; every cable comes in through the bottom wall. Work with "
         "the box lying on its back. Most of the station's thinking happens in here, out of the rain.",
         box_steps(parts, n)),
        ("solar", "Solar bracket",
         "A tilted tray for a panel up to %s x %s, mounted on the mast above the box. It faces the "
         "sun and asks for very little." %
         (fmt(P.panel_l), mm(P.panel_w)), solar_steps(parts, n)),
        ("sky", "Sky pod",
         "An MLX90614 looking at the sky from above the mast top. On a clear night the sky reads "
         "colder than seems reasonable; that is the point.", sky_steps(parts, n)),
        ("mast", "Onto the mast",
         "Everything onto a vertical 2020 mast and a crossarm. The last step, and the one the "
         "neighbours notice.", frame_steps(parts, n)),
    ]


def main():
    t0 = time.time()
    problems = P.validate()
    if problems:
        print("params.validate() failed; fix params.py first:")
        for p in problems:
            print("  - " + p)
        return 2
    parts = {}
    for mod in (wind, rain, screen, enclosure, sky):
        parts.update(mod.parts())
    n = numbers(parts)
    cat, _gx = catalogue(n)
    sections = sections_for(parts, n)
    for _a, _b, _c, steps in sections:
        steps[0].scene.text_labels = True          # first picture of each section names its parts
    ov = overview_scene(parts)
    ov.text_labels = True
    scenes = [ov] + [st.scene for _a, _b, _c, steps in sections for st in steps if st.scene]
    scenes += gallery_scenes(parts, sections, n)
    meta_path = os.path.join(FIG_DIR, "figures.json")
    figs = {}
    if ONLY and os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            figs = json.load(f)
    os.makedirs(FIG_DIR, exist_ok=True)
    keep = {s.name for s in scenes}
    for s in scenes:
        if ONLY and s.name not in ONLY:
            continue
        t = time.time()
        figs[s.name] = render(s)
        print("  %-22s %4.1f s" % (s.name, time.time() - t))
        sys.stdout.flush()
    figs = {k: v for k, v in figs.items() if k in keep}
    if not ONLY:
        for fn in os.listdir(FIG_DIR):
            if fn.endswith(".png") and fn[:-4] not in keep:
                os.remove(os.path.join(FIG_DIR, fn))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(figs, f, indent=1)
    write_html(sections, figs, cat, n, os.path.join(DOCS, "assembly.html"))
    write_html(sections, figs, cat, n, os.path.join(DOCS, "assembly-print.html"), mode="print")
    data = export_steps(sections, figs, cat)
    write_sheet(data, os.path.join(DOCS, "assembly-sheet.html"))
    write_app(data, os.path.join(DOCS, "assembly-app.html"))
    write_landing(data, os.path.join(DOCS, "build-landing.html"))
    print("assembly guide: %d figures, docs/assembly.html, %.0f s" % (len(figs), time.time() - t0))
    return 0


main()
