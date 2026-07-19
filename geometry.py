"""Silnik geometrii: ścieżka SVG -> bryła wycinaka / stempla (trimesh).

Wejście to zawsze zamknięty kontur 2D (shapely Polygon, może mieć dziury).
Wycinak = wstęga wzdłuż konturu: kołnierz (dół, na stole druku) + korpus +
cienkie ostrze (góra). Stempel = płytka bazowa + wytłoczony wzór + uchwyt.

Lekcja z ipadMount/vaseGen: is_watertight NIE wystarcza — sprawdzamy też
is_winding_consistent i w razie czego fix_normals().
"""

import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString, MultiPolygon, Point
from shapely.ops import unary_union, nearest_points
from svgpathtools import parse_path

from config import DEFAULTS


# ---------------------------------------------------------------- SVG -> 2D

def path_to_polygon(d: str, samples_per_seg: int = 32) -> Polygon:
    """Parsuje atrybut d ścieżki SVG do shapely Polygon (even-odd dla dziur).

    Oś Y jest odbijana (SVG rośnie w dół), więc kształt na wydruku wygląda
    tak samo jak podgląd — istotne przy napisach/asymetrii.
    """
    path = parse_path(d)
    subpolys = []
    for sp in path.continuous_subpaths():
        pts = []
        for seg in sp:
            for t in np.linspace(0.0, 1.0, samples_per_seg, endpoint=False):
                z = seg.point(t)
                pts.append((z.real, -z.imag))
        if len(pts) >= 3:
            p = Polygon(pts).buffer(0)  # buffer(0) naprawia samoprzecięcia
            if not p.is_empty:
                subpolys.append(p)
    if not subpolys:
        raise ValueError("ścieżka SVG nie zawiera zamkniętego konturu")

    # even-odd: największy kontur to baza; kolejne zawarte w niej to dziury,
    # rozłączne — dokładamy sumą (np. bałwan z osobnych kół)
    subpolys.sort(key=lambda p: p.area, reverse=True)
    result = subpolys[0]
    for p in subpolys[1:]:
        if result.contains(p.representative_point()) and p.area < result.area:
            result = result.difference(p)
        else:
            result = unary_union([result, p])
    if isinstance(result, MultiPolygon):
        result = max(result.geoms, key=lambda g: g.area)
    result = result.simplify(0.15)
    if result.is_empty or result.area <= 0:
        raise ValueError("kontur zdegenerowany po naprawie")
    return result


def poly_to_d(poly: Polygon) -> str:
    """Polygon -> SVG path d (z dziurami), znormalizowany do viewBox 0..100.
    Odbija oś Y (SVG rośnie w dół) — path_to_polygon odbija ją z powrotem."""
    minx, miny, maxx, maxy = poly.bounds
    span = max(maxx - minx, maxy - miny) or 1.0
    s = 92.0 / span
    ox = (100 - (maxx - minx) * s) / 2 - minx * s
    oy = (100 - (maxy - miny) * s) / 2 - miny * s

    def ring_d(coords):
        pts = [(x * s + ox, 100 - (y * s + oy)) for x, y in coords]
        return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"

    d = ring_d(poly.exterior.coords)
    for r in poly.interiors:
        d += " " + ring_d(r.coords)
    return d


def scale_to_size(poly: Polygon, size_mm: float) -> Polygon:
    """Skaluje kształt tak, by najdłuższy wymiar = size_mm, środek w (0,0)."""
    minx, miny, maxx, maxy = poly.bounds
    span = max(maxx - minx, maxy - miny)
    if span <= 0:
        raise ValueError("kształt o zerowych wymiarach")
    s = size_mm / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    from shapely.affinity import scale, translate
    return scale(translate(poly, -cx, -cy), s, s, origin=(0, 0))


# ---------------------------------------------------------------- pomocnicze

def _contour_lines(poly: Polygon):
    lines = [LineString(poly.exterior.coords)]
    lines += [LineString(r.coords) for r in poly.interiors]
    return lines


def _ribbon(poly: Polygon, width: float):
    """Zamknięta wstęga o zadanej szerokości wzdłuż WSZYSTKICH konturów
    (zewnętrznego i dziur) — to przekrój ścianki wycinaka.

    join_style=1 (okrągłe): mitre robiło kilkunastomilimetrowe kolce na
    ostrych wierzchołkach (gwiazda!); zaokrąglenie ~width/2 jest pomijalne.
    """
    return unary_union([ln.buffer(width / 2.0, join_style=1)
                        for ln in _contour_lines(poly)])


def _extrude(section, height: float, z0: float) -> trimesh.Trimesh:
    if isinstance(section, MultiPolygon):
        parts = [trimesh.creation.extrude_polygon(g, height) for g in section.geoms]
        m = trimesh.util.concatenate(parts)
    else:
        m = trimesh.creation.extrude_polygon(section, height)
    m.apply_translation([0, 0, z0])
    return m


def _finalize(meshes) -> trimesh.Trimesh:
    """Łączy bryły (boolean union jeśli dostępny manifold3d, inaczej
    konkatenacja — nakładające się zamknięte bryły slicer i tak scali)."""
    try:
        mesh = trimesh.boolean.union(meshes, engine="manifold")
    except BaseException:
        mesh = trimesh.util.concatenate(meshes)
    if not mesh.is_winding_consistent:
        mesh.fix_normals()
    return mesh


def _connector_bars(poly: Polygon, bar_w: float = 3.0):
    """Mostki łączące pierścienie tnące dziur (oczy dyni itp.) z obwodem —
    bez nich wewnętrzne ostrza byłyby luźnymi, osobnymi elementami.

    Mostki leżą przy kołnierzu (z=0), czyli ~14 mm NAD krawędzią tnącą —
    nie dotykają ciasta/gliny, więc nie zostawiają dodatkowych linii.
    Po 2 mostki na dziurę (najkrótsze połączenie + przeciwległe)."""
    if not poly.interiors:
        return None
    ext = LineString(poly.exterior.coords)
    filled = Polygon(poly.exterior.coords)
    bars = []
    for hole in poly.interiors:
        hl = LineString(hole.coords)
        c = Polygon(hole).centroid
        p1h, p1e = nearest_points(hl, ext)
        bars.append(LineString([p1h, p1e]).buffer(bar_w / 2, cap_style=2))
        d = np.array([p1h.x - c.x, p1h.y - c.y])
        n = float(np.linalg.norm(d))
        if n > 1e-6:
            d /= n
            coords = np.asarray(hole.coords)
            dots = (coords - [c.x, c.y]) @ (-d)
            p2h = Point(*coords[int(np.argmax(dots))])
            p2e = nearest_points(p2h, ext)[1]
            bars.append(LineString([p2h, p2e]).buffer(bar_w / 2, cap_style=2))
    u = unary_union(bars).intersection(filled)
    return None if u.is_empty else u


# ---------------------------------------------------------------- wycinak

def build_cutter(poly: Polygon, **over) -> trimesh.Trimesh:
    p = {**DEFAULTS, **over}
    poly = scale_to_size(poly, p["size"])
    # lekkie pogrubienie (+0.5mm) ratuje patykowate detale sylwetek z grafik
    # (ręce bałwana itp.) przed łamliwością ostrza; kształtu nie zmienia
    fat = poly.buffer(0.5, join_style=1).simplify(0.1)
    if not fat.is_empty and fat.geom_type == "Polygon":
        poly = fat

    blade = _ribbon(poly, p["blade_t"])
    body = _ribbon(poly, p["body_t"])
    flange = _ribbon(poly, p["body_t"] + 2 * p["flange_w"])

    meshes = [
        _extrude(flange, p["flange_t"], 0.0),               # kołnierz na stole
        _extrude(body, p["body_h"], 0.0),                   # korpus
        _extrude(blade, p["blade_h"], p["body_h"]),         # ostrze na górze
    ]
    bars = _connector_bars(poly)
    if bars is not None:
        meshes.append(_extrude(bars, max(p["flange_t"], 2.0), 0.0))
    return _finalize(meshes)


# ---------------------------------------------------------------- stempel

def build_stamp(poly: Polygon, **over) -> trimesh.Trimesh:
    p = {**DEFAULTS, **over}
    poly = scale_to_size(poly, p["size"])

    base = poly.buffer(p["stamp_margin"], join_style=1).simplify(0.2)
    if isinstance(base, MultiPolygon):
        base = max(base.geoms, key=lambda g: g.area)
    # relief drukowany na płytce; wzór LUSTRZANY, żeby odcisk był poprawny
    from shapely.affinity import scale as _scale
    relief = _scale(poly, -1, 1, origin=(0, 0))
    base = _scale(base, -1, 1, origin=(0, 0))

    # relief na górze (najlepsza jakość druku), dociskamy płaskim grzbietem —
    # uchwyt po stronie reliefu dotykałby gliny przed wzorem, a po drugiej
    # stronie wymagałby podpór, więc w v1 go nie ma
    meshes = [
        _extrude(base, p["stamp_base_t"], 0.0),
        _extrude(relief, p["stamp_relief"], p["stamp_base_t"]),
    ]
    return _finalize(meshes)


# ---------------------------------------------------------------- kontrola

def sanity(mesh: trimesh.Trimesh) -> dict:
    return dict(
        watertight=bool(mesh.is_watertight),
        winding=bool(mesh.is_winding_consistent),
        tris=int(len(mesh.faces)),
        bbox=[round(float(v), 1) for v in (mesh.bounds[1] - mesh.bounds[0])],
    )
