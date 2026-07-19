"""Orkiestracja źródeł kształtów — od najwierniejszych do awaryjnych:

1. Iconify (api.iconify.design, darmowe, bez klucza) — profesjonalne ikony
   wektorowe; świetne dla typowych obiektów, słownik: pojedyncze rzeczowniki.
2. Wyszukiwarka obrazów DuckDuckGo (ddgs, bez klucza) — "X silhouette
   clipart", pobieramy kilka kandydatów, wektoryzujemy (vectorize.py)
   i bierzemy najlepszy wynik. Pokrywa dowolny motyw.
3. DSL prymitywów przez Groq (ai.generate_shapes) — ostatnia deska ratunku.

Groq służy głównie do tłumaczenia motywu na konkretne obiekty
(ai.theme_keywords) — to małe zapytanie, mieści się w limicie tokenów.
"""

import concurrent.futures as futures
import re

import requests
from shapely.geometry import Polygon

import ai
import geometry
import vectorize

ICONIFY_SEARCH = "https://api.iconify.design/search"
ICONIFY_SVG = "https://api.iconify.design/{prefix}/{name}.svg"
# zestawy z wypełnionymi sylwetkami (nie outline)
ICON_SETS = "game-icons,fa6-solid,mdi,material-symbols,fluent-emoji-high-contrast"

HEADERS = {"User-Agent": "Mozilla/5.0 (cutterForge; hobby 3D printing)"}


# ---------------------------------------------------------------- iconify

def _clean_icon_poly(poly: Polygon) -> Polygon | None:
    """Chunkifikacja ikony pod fizyczny wycinak: domknięcie mikroprzerw,
    usunięcie włosków, tylko duże dziury. Zwraca None dla ikon, które po
    obróbce nie są sensowną sylwetką (obwódki, pierścienie, strzępy)."""
    b = poly.bounds
    s = max(b[2] - b[0], b[3] - b[1])
    p = poly.buffer(s * 0.012).buffer(-s * 0.022).buffer(s * 0.010)
    if p.is_empty:
        return None
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    holes = [r for r in p.interiors if Polygon(r).area >= 0.02 * p.area]
    p = Polygon(p.exterior, holes).simplify(s * 0.004)
    if p.is_empty or p.area <= 0:
        return None
    solidity = p.area / (p.convex_hull.area or 1.0)
    if solidity < 0.36:            # outline/ramka, nie sylwetka
        return None
    # pierścień ("czapka czarownicy" = okrąg w okręgu): dziury zjadają
    # większość wypełnienia -> to obrys, nie sylwetka
    filled = Polygon(p.exterior).area
    if filled > 0 and (filled - p.area) / filled > 0.45:
        return None
    return p


def _name_matches(icon_id: str, query: str) -> bool:
    """Dopasowanie całych słów: query "lamb" NIE pasuje do "mdi:lambda"
    (wyszukiwarka Iconify dopasowuje podciągi i wracały absurdy)."""
    words = {w for w in re.split(r"[^a-z0-9]+", query.lower()) if len(w) > 2}
    name = icon_id.split(":", 1)[1]
    tokens = {t for t in name.lower().split("-") if t}
    for w in words:
        if w in tokens or (w + "s") in tokens or (w + "es") in tokens:
            return True
        if w.endswith("s") and w[:-1] in tokens:
            return True
    return False


def icon_candidates(query: str, k: int = 2) -> list[Polygon]:
    """Do k RÓŻNYCH sensownych ikon dla zapytania — użytkownik wybiera."""
    try:
        r = requests.get(ICONIFY_SEARCH, timeout=15, headers=HEADERS,
                         params={"query": query, "limit": 24,
                                 "prefixes": ICON_SETS})
        icons = [i for i in r.json().get("icons", [])
                 if _name_matches(i, query)]
    except Exception:
        return []
    out = []
    for icon_id in icons[:8]:
        if len(out) >= k:
            break
        try:
            prefix, name = icon_id.split(":", 1)
            svg = requests.get(ICONIFY_SVG.format(prefix=prefix, name=name),
                               timeout=15, headers=HEADERS).text
            ds = re.findall(r'\sd="([^"]+)"', svg)
            if not ds:
                continue
            poly = geometry.path_to_polygon(" ".join(ds))
            poly = _clean_icon_poly(poly)
            if poly is not None:
                out.append(poly)
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- web (ddg)

def web_candidates(query_en: str, k: int = 1) -> list[Polygon]:
    """Najlepiej ocenione wektoryzacje z wyszukiwarki obrazów (do k)."""
    try:
        from ddgs import DDGS
        results = list(DDGS().images(f"{query_en} silhouette clipart black",
                                     max_results=8))
    except Exception:
        return []
    scored, tried = [], 0
    for res in results:
        url = res.get("image") or ""
        if not url:
            continue
        try:
            img = requests.get(url, timeout=12, headers=HEADERS).content
        except Exception:
            continue
        poly, score = vectorize.image_to_polygon(img)
        tried += 1
        if poly is not None and score >= 0.40:
            scored.append((score, poly))
            if score > 0.80 and len(scored) >= k:
                break
        if tried >= 5:
            break
    scored.sort(key=lambda t: -t[0])
    return [p for _, p in scored[:k]]


# ---------------------------------------------------------------- kaskada

def _one_item(item: dict) -> list[dict]:
    """item: {"pl","en","icon"} -> lista kandydatów {"name","path","source"}.

    Celowo ZAWSZE próbujemy i ikon, i wyszukiwarki — pojedyncze źródło
    potrafi trafić absurd (różdżka=patyk), a użytkownik woli wybierać
    z kilku wariantów tego samego obiektu."""
    # pełna fraza najpierw ("christmas tree"), potem sam rzeczownik ("tree") —
    # inaczej motywowane warianty spłaszczają się do generycznych ikon
    polys = icon_candidates(item["en"], k=2)
    if not polys and item.get("icon") and item["icon"] != item["en"]:
        polys = icon_candidates(item["icon"], k=2)
    cands = [{"name": item["pl"], "path": geometry.poly_to_d(p),
              "source": "icon"} for p in polys]
    for p in web_candidates(item["en"], k=1):
        cands.append({"name": item["pl"], "path": geometry.poly_to_d(p),
                      "source": "web"})
    return cands


def gather(theme: str) -> list[dict]:
    """Główne wejście: motyw -> lista kształtów z kaskady źródeł."""
    try:
        items = ai.theme_keywords(theme)
    except Exception:
        items = [{"pl": theme, "en": theme, "icon": theme}]

    out, seen = [], set()
    with futures.ThreadPoolExecutor(max_workers=4) as ex:
        for cands in ex.map(_one_item, items):
            for res in cands:
                # dedup: różne hasła trafiają czasem w tę samą ikonę
                # ("królik" i "królik w koszyku" -> identyczny kształt)
                if res["path"] not in seen:
                    seen.add(res["path"])
                    out.append(res)

    if len(out) < 5:               # kaskada zawiodła — dorzuć DSL z Groq
        try:
            for it in ai.generate_shapes(theme, count=5):
                it["source"] = "ai"
                out.append(it)
        except Exception:
            pass
    return out[:32]
