"""DSL prymitywów — model AI komponuje kształt z prostych figur zamiast
rysować surowe krzywe Béziera (te wychodziły połamane). Każda część to
JSON: {"shape": "...", "op": "add"|"sub", ...parametry}, składane po kolei.

Figury: circle, ellipse, rect, polygon, star, stroke (gruba linia łamana
z zaokrąglonymi końcami — patyki, laski, łuki).
Canvas 0..100, oś Y DO GÓRY (naturalna dla modelu — próba narzucenia
Y-w-dół jak w SVG kończyła się kształtami do góry nogami). Na SVG do
podglądu odbija to geometry.poly_to_d.
"""

import numpy as np
from shapely.geometry import Polygon, Point, LineString
from shapely import affinity


def _rot(g, deg, origin):
    return affinity.rotate(g, deg, origin=origin) if deg else g


def _round_corners(p, r):
    if not r or r <= 0:
        return p
    return p.buffer(r, join_style=1).buffer(-r, join_style=1)


def _make(part):
    s = part.get("shape")
    if s == "circle":
        return Point(part["cx"], part["cy"]).buffer(abs(part["r"]), 64)
    if s == "ellipse":
        e = Point(part["cx"], part["cy"]).buffer(1.0, 64)
        e = affinity.scale(e, abs(part["rx"]), abs(part["ry"]))
        return _rot(e, part.get("rot", 0), (part["cx"], part["cy"]))
    if s == "rect":
        cx, cy, w, h = part["cx"], part["cy"], abs(part["w"]), abs(part["h"])
        p = Polygon([(cx - w/2, cy - h/2), (cx + w/2, cy - h/2),
                     (cx + w/2, cy + h/2), (cx - w/2, cy + h/2)])
        p = _round_corners(p, part.get("round", 0))
        return _rot(p, part.get("rot", 0), (cx, cy))
    if s == "polygon":
        pts = part["pts"]
        if len(pts) < 3:
            raise ValueError("polygon: min 3 punkty")
        p = Polygon(pts).buffer(0)
        return _round_corners(p, part.get("round", 0))
    if s == "star":
        cx, cy = part["cx"], part["cy"]
        n = max(3, int(part.get("n", 5)))
        r, ri = abs(part["r"]), abs(part.get("ri", part["r"] * 0.45))
        th = np.linspace(0, 2*np.pi, n*2, endpoint=False) + np.pi/2  # ramię w górę
        rr = np.where(np.arange(n*2) % 2 == 0, r, ri)
        p = Polygon(np.column_stack([cx + rr*np.cos(th), cy + rr*np.sin(th)]))
        p = _round_corners(p.buffer(0), part.get("round", 0))
        return _rot(p, part.get("rot", 0), (cx, cy))
    if s == "stroke":
        pts = part["pts"]
        if len(pts) < 2:
            raise ValueError("stroke: min 2 punkty")
        return LineString(pts).buffer(abs(part["w"]) / 2.0, 32)
    raise ValueError(f"nieznana figura: {s}")


def build(parts) -> Polygon:
    """Składa listę części w jeden Polygon (add = suma, sub = różnica)."""
    result = None
    for part in parts:
        g = _make(part)
        if g.is_empty:
            continue
        if part.get("op", "add") == "sub":
            if result is not None:
                result = result.difference(g)
        else:
            result = g if result is None else result.union(g)
    if result is None or result.is_empty:
        raise ValueError("pusty kształt")
    if result.geom_type == "MultiPolygon":
        result = max(result.geoms, key=lambda g: g.area)
    return result.simplify(0.1)
