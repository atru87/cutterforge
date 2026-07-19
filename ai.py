"""Groq (darmowy tier) — prompt użytkownika -> lista konturów SVG.

Model tekstowy nie rysuje obrazków, ale model ROZUMUJĄCY (gpt-oss-120b)
całkiem nieźle komponuje sylwetki z prostych figur, jeśli dostanie few-shot
i wskazówkę "buduj przez sumowanie prymitywów". Wyniki llama-3.3 były
kleksami — dlatego domyślnie gpt-oss-120b, llama tylko jako fallback.

Nie używamy response_format=json_object: walidator Groqa ucina odpowiedź
modeli rozumujących (myślenie zjada tokeny -> pusty content -> 400).
Zamiast tego duży max_completion_tokens i parsowanie JSON-a regexem.
Każdą ścieżkę i tak waliduje geometry.path_to_polygon.
"""

import json
import os
import re
import time

import requests

from config import GROQ_MODEL, GROQ_FALLBACK_MODEL, GROQ_URL, \
    SHAPES_PER_REQUEST, MAX_RETRIES, RETRY_DELAY_S

SYSTEM_PROMPT = f"""You are a silhouette designer for 3D-printed cookie/clay cutters.
Given a theme, design {SHAPES_PER_REQUEST} DISTINCT, instantly recognizable flat silhouettes.

You do NOT draw curves by hand. You COMPOSE each silhouette from primitives on a 0..100 x 0..100 canvas. Standard math orientation: y=0 is the BOTTOM edge, y=100 is the TOP edge (a tree's trunk sits at LOW y, its tip at HIGH y). Available primitives (all numbers are canvas units):

- {{"shape":"circle","cx":..,"cy":..,"r":..}}
- {{"shape":"ellipse","cx":..,"cy":..,"rx":..,"ry":..,"rot":deg}}
- {{"shape":"rect","cx":..,"cy":..,"w":..,"h":..,"rot":deg,"round":radius}}
- {{"shape":"polygon","pts":[[x,y],..],"round":radius}}  (any custom outline)
- {{"shape":"star","cx":..,"cy":..,"r":outer,"ri":inner,"n":points,"rot":deg}}
- {{"shape":"stroke","pts":[[x,y],..],"w":thickness}}  (thick polyline, round ends — sticks, hooks, arcs; approximate a curve with 4-8 points)

Each part has "op":"add" (default, union) or "op":"sub" (cut away). Parts are applied in order.

Design rules:
- Build like paper cutouts: snowman = 3 stacked circles; gift = rect + stroke ribbon + 2 circles bow; candy cane = stroke with hooked points; cat head = circle + 2 triangle ears.
- ALL parts must overlap into ONE connected piece (it's a physical cutter).
- Chunky and bold: no limb, gap or detail narrower than 8 units. 3-8 parts per silhouette is the sweet spot — do not overdetail.
- Exaggerate the most characteristic feature (cat's ears, whale's tail, mug's handle).
- Span at least 70 units in one direction.
- "sub" cuts are great for: moon crescent, mug handle hole, donut hole, window in a house.

Example (lollipop — candy circle on TOP, stick going DOWN):
{{"name":"lizak","parts":[{{"shape":"circle","cx":50,"cy":68,"r":24}},{{"shape":"stroke","pts":[[50,45],[50,8]],"w":9}}]}}

Respond with JSON only (no prose before or after):
{{"items":[{{"name":"short polish name","parts":[...]}}, ...]}}"""


class GroqError(RuntimeError):
    pass


class RetryableError(RuntimeError):
    """Błąd przejściowy (rate limit) — warto ponowić."""


def _api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise GroqError("brak GROQ_API_KEY w .env")
    return key


def _call(model: str, theme: str, count: int) -> list[dict]:
    # darmowy tier: 8000 tokenów/min — max_completion_tokens + prompt musi
    # się zmieścić, inaczej Groq odrzuca zapytanie z góry (413/429)
    payload = {
        "model": model,
        "temperature": 0.8,
        "max_completion_tokens": 6000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"Theme: {theme}\nDesign {count} silhouettes."},
        ],
    }
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "medium"
    r = requests.post(GROQ_URL, json=payload,
                      headers={"Authorization": f"Bearer {_api_key()}"},
                      timeout=180)
    if r.status_code == 429:
        wait = float(r.headers.get("retry-after", 5)) + 1.0
        time.sleep(min(wait, 30.0))
        raise RetryableError(f"limit tokenów Groq, czekałem {wait:.0f}s")
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError("brak JSON w odpowiedzi modelu")
    items = json.loads(m.group(0)).get("items", [])

    # DSL -> Polygon -> ścieżka SVG (ten sam format co builtin/UI);
    # zepsute definicje odpadają tu, nie w serwerze
    import geometry
    import shapes_dsl
    out = []
    for it in items:
        try:
            poly = shapes_dsl.build(it["parts"])
            out.append({"name": str(it.get("name", "?")).strip(),
                        "path": geometry.poly_to_d(poly)})
        except Exception:
            pass
    if not out:
        raise ValueError("model nie zwrócił żadnych składalnych kształtów")
    return out


KEYWORDS_PROMPT = """You turn a theme for cookie/clay cutter designs into a list of concrete,
drawable OBJECTS. For each object give:
- "pl": short polish display name
- "en": english phrase for an image search (2-4 words, what the object IS)
- "icon": ONE simple english noun for an icon-library search (e.g. "sweater", "tree", "bat")

Pick objects with iconic, instantly recognizable silhouettes. Avoid scenes,
patterns and abstract concepts. ONE single object per item — never combine
("bunny with carrot" -> just "bunny"; the carrot can be its OWN item).
Respond with JSON only:
{"items":[{"pl":"...","en":"...","icon":"..."}, ...]}"""


def theme_keywords(theme: str, count: int = SHAPES_PER_REQUEST) -> list[dict]:
    """Motyw -> konkretne obiekty [{pl,en,icon}]. Małe zapytanie (~1k tok)."""
    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.7,
        "max_completion_tokens": 3500,
        "messages": [
            {"role": "system", "content": KEYWORDS_PROMPT},
            {"role": "user", "content": f"Theme: {theme}\nList {count} objects."},
        ],
    }
    if "gpt-oss" in GROQ_MODEL:
        payload["reasoning_effort"] = "low"
    r = requests.post(GROQ_URL, json=payload,
                      headers={"Authorization": f"Bearer {_api_key()}"},
                      timeout=90)
    if r.status_code == 429:
        wait = float(r.headers.get("retry-after", 5)) + 1.0
        time.sleep(min(wait, 30.0))
        r = requests.post(GROQ_URL, json=payload,
                          headers={"Authorization": f"Bearer {_api_key()}"},
                          timeout=90)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    items = json.loads(m.group(0))["items"]
    out = []
    for it in items:
        if it.get("pl") and it.get("en"):
            out.append({"pl": str(it["pl"]).strip(),
                        "en": str(it["en"]).strip(),
                        "icon": str(it.get("icon", "")).strip()})
    if not out:
        raise ValueError("brak obiektów w odpowiedzi")
    return out[:count]


def generate_shapes(theme: str, count: int = SHAPES_PER_REQUEST) -> list[dict]:
    """Zwraca listę {name, path}; rzuca GroqError gdy API niedostępne."""
    last_err = None
    for model in (GROQ_MODEL, GROQ_FALLBACK_MODEL):
        for attempt in range(MAX_RETRIES):
            try:
                return _call(model, theme, count)
            except GroqError:
                raise
            except Exception as e:  # sieć, 4xx/5xx, zepsuty JSON
                last_err = e
                time.sleep(RETRY_DELAY_S * (attempt + 1))
    raise GroqError(f"Groq nie odpowiedział poprawnie: {last_err}")
