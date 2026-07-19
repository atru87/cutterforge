"""Rastrowy obraz sylwetki -> shapely Polygon (kontur + duże dziury).

Zakładany materiał wejściowy: clipart/sylwetka o wysokim kontraście
(czarny kształt na jasnym tle) z wyszukiwarki obrazów. Pipeline:
skala -> szarość (alfa na białym) -> próg -> morfologia (domknięcie +
otwarcie usuwa znaki wodne i włoski) -> kontury z hierarchią (dziury)
-> największy spójny kształt -> uproszczenie.

Zwraca też score jakości — orkiestrator próbuje kilku obrazów i bierze
najlepszy, zamiast wierzyć pierwszemu.
"""

import io

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon

MAX_SIDE = 640


def _to_gray(img_bytes: bytes) -> np.ndarray:
    im = Image.open(io.BytesIO(img_bytes))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    im = im.convert("L")
    w, h = im.size
    s = MAX_SIDE / max(w, h)
    if s < 1:
        im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
    return np.asarray(im)


def _mask(gray: np.ndarray) -> np.ndarray | None:
    """Binarna maska sylwetki. Najpierw twardy próg (czarny tusz, ignoruje
    szare znaki wodne), gdy pusto — Otsu."""
    for th in (90, None):
        if th is None:
            _, m = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            _, m = cv2.threshold(gray, th, 255, cv2.THRESH_BINARY_INV)
        frac = (m > 0).mean()
        if 0.02 <= frac <= 0.72:
            return m
    return None


def image_to_polygon(img_bytes: bytes):
    """-> (Polygon, score 0..1) albo (None, 0)."""
    try:
        gray = _to_gray(img_bytes)
    except Exception:
        return None, 0.0
    m = _mask(gray)
    if m is None:
        return None, 0.0

    size = max(m.shape)
    k1 = max(3, int(size * 0.012)) | 1
    k2 = max(3, int(size * 0.008)) | 1
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k1, k1)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2)))

    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
    if not cnts or hier is None:
        return None, 0.0
    hier = hier[0]

    # największy kontur zewnętrzny
    outer = [(i, cv2.contourArea(c)) for i, (c, h) in enumerate(zip(cnts, hier))
             if h[3] == -1]
    if not outer:
        return None, 0.0
    best_i, best_a = max(outer, key=lambda t: t[1])
    img_area = m.shape[0] * m.shape[1]
    if best_a < 0.04 * img_area:
        return None, 0.0

    def ring(c):
        pts = c.reshape(-1, 2).astype(float)
        pts[:, 1] = -pts[:, 1]          # oś Y do góry
        return pts

    exterior = ring(cnts[best_i])
    if len(exterior) < 3:
        return None, 0.0
    holes = []
    child = hier[best_i][2]
    while child != -1:
        a = cv2.contourArea(cnts[child])
        if a > 0.02 * best_a and len(cnts[child]) >= 3:
            holes.append(ring(cnts[child]))
        child = hier[child][0]

    poly = Polygon(exterior, holes).buffer(0)
    if poly.is_empty:
        return None, 0.0
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    span = max(poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
    poly = poly.simplify(span * 0.004)
    if poly.is_empty or poly.area <= 0:
        return None, 0.0

    # score: zwarta bryła (nie strzępy), rozsądne proporcje, nie ramka
    hull = poly.convex_hull.area or 1.0
    solidity = poly.area / hull
    w = poly.bounds[2] - poly.bounds[0]
    h = poly.bounds[3] - poly.bounds[1]
    aspect = max(w, h) / max(1e-6, min(w, h))
    if aspect > 4.0 or solidity < 0.25:
        return None, 0.0
    hole_frac = sum(Polygon(r).area for r in poly.interiors) / max(poly.area, 1e-6)
    if hole_frac > 1.2:
        return None, 0.0
    score = solidity * (1.0 - min(aspect - 1, 2.0) * 0.15)
    return poly, float(max(0.0, min(1.0, score)))
