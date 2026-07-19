"""Wbudowana biblioteka kształtów — działa bez klucza API i służy jako demo.

Kształty generowane parametrycznie (numpy/shapely), zwracane jako ścieżki
SVG "d" w viewBox 0..100 — dokładnie ten sam format co odpowiedzi Groq,
więc dalszy pipeline jest wspólny.
"""

import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union


from geometry import poly_to_d as _to_d


def _polar(fn, n=240):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = fn(th)
    return Polygon(np.column_stack([r * np.cos(th), r * np.sin(th)])).buffer(0)


def _heart():
    t = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    return Polygon(np.column_stack([x, y])).buffer(0)


def _star(points=5, inner=0.45):
    th = np.linspace(0, 2 * np.pi, points * 2, endpoint=False) + np.pi / 2
    r = np.where(np.arange(points * 2) % 2 == 0, 1.0, inner)
    p = Polygon(np.column_stack([r * np.cos(th), r * np.sin(th)]))
    return p.buffer(0.06, join_style=1).buffer(-0.03)  # lekko zaokrąglone rogi


def _tree():
    tiers = []
    y = 0.0
    for w, h in [(30, 26), (24, 22), (17, 18)]:
        tiers.append(Polygon([(-w / 2, y), (w / 2, y), (0, y + h)]))
        y += h * 0.62
    trunk = box(-4, -9, 4, 2)
    return unary_union(tiers + [trunk]).buffer(1.2, join_style=1)


def _snowman():
    return unary_union([Point(0, 0).buffer(14),
                        Point(0, 19).buffer(10.5),
                        Point(0, 34).buffer(7.5)])


def _moon():
    return Point(0, 0).buffer(20).difference(Point(9, 4).buffer(16)).buffer(0)


def _flower(petals=6):
    core = Point(0, 0).buffer(7)
    ps = [Point(13 * np.cos(a), 13 * np.sin(a)).buffer(8.2)
          for a in np.linspace(0, 2 * np.pi, petals, endpoint=False)]
    return unary_union([core] + ps)


def _leaf():
    t = np.linspace(0, np.pi, 120)
    top = np.column_stack([np.cos(t) * 12, np.sin(t) * 26])
    bot = np.column_stack([np.cos(t)[::-1] * 12, -np.sin(t)[::-1] * 7])
    return Polygon(np.vstack([top, bot])).buffer(0)


def _cloud():
    return unary_union([Point(-14, 0).buffer(10), Point(0, 6).buffer(13),
                        Point(14, 0).buffer(10), box(-16, -9, 16, 1)])


def _gingerbread():
    head = Point(0, 26).buffer(10)
    body = Polygon([(-9, 18), (9, 18), (12, -6), (-12, -6)]).buffer(3)
    arms = box(-24, 8, 24, 17)
    legs = unary_union([box(-13, -26, -3, -2), box(3, -26, 13, -2)])
    return unary_union([head, body, arms, legs]).buffer(2.5, join_style=1)


def _hexagon():
    return _polar(lambda th: np.full_like(th, 1.0), n=6).buffer(0.05, join_style=1)


def _egg():
    t = np.linspace(0, 2 * np.pi, 240, endpoint=False)
    return Polygon(np.column_stack(
        [14 * np.cos(t), 19 * np.sin(t) * (1 + 0.18 * np.sin(t))])).buffer(0)


def _butterfly():
    wing = unary_union([Point(10, 9).buffer(10), Point(9, -7).buffer(7.5)])
    from shapely.affinity import scale
    body = box(-2.5, -14, 2.5, 14)
    return unary_union([wing, scale(wing, -1, 1, origin=(0, 0)), body])


BUILTIN = [
    ("Serce", _heart), ("Gwiazda", _star), ("Choinka", _tree),
    ("Bałwan", _snowman), ("Księżyc", _moon), ("Kwiat", _flower),
    ("Liść", _leaf), ("Chmurka", _cloud), ("Piernikowy ludzik", _gingerbread),
    ("Heks", _hexagon), ("Jajko", _egg), ("Motyl", _butterfly),
]


def builtin_shapes() -> list[dict]:
    out = []
    for name, fn in BUILTIN:
        try:
            out.append({"name": name, "path": _to_d(fn())})
        except Exception:
            pass
    return out
