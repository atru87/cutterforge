"""cutterForge — serwer www (Flask, port 5100).

Endpointy:
  GET  /                 UI
  GET  /api/categories   lista kategorii bazowych
  POST /api/shapes       {"prompt": "..."} lub {"category": "id"} -> kształty
  POST /api/model        {"path": "...", "name", "mode": "cutter"|"stamp",
                          "size", ...} -> generuje STL, zwraca URL + statystyki
  GET  /out/<plik>       pobieranie STL
"""

import hashlib
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

BASE = Path(__file__).parent
# override=True: w systemie potrafi wisieć stary GROQ_API_KEY — .env ma wygrywać
load_dotenv(BASE / ".env", override=True)

if sys.platform == "win32":  # stara konsola cp1250 vs polskie znaki
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import ai
import geometry
import sources
from builtin_shapes import builtin_shapes
from config import PORT, DEFAULTS

from auth import init_auth

app = Flask(__name__, static_folder=None)
init_auth(app, "cutterforge")
OUT = BASE / "out"
CACHE = BASE / "cache"
CATEGORIES = json.loads((BASE / "categories.json").read_text(encoding="utf-8"))
CAT_BY_ID = {c["id"]: c for c in CATEGORIES}


def _validated(items):
    """Odrzuca ścieżki, których nie da się zamienić na poprawny kontur."""
    ok = []
    for it in items:
        try:
            geometry.path_to_polygon(it["path"])
            ok.append(it)
        except Exception:
            pass
    return ok


@app.get("/")
def index():
    return send_from_directory(BASE / "web", "index.html")


@app.get("/api/categories")
def categories():
    return jsonify(CATEGORIES)


@app.post("/api/shapes")
def shapes():
    data = request.get_json(force=True)
    cat_id = data.get("category")
    prompt = (data.get("prompt") or "").strip()

    if cat_id:
        cat = CAT_BY_ID.get(cat_id)
        if not cat:
            return jsonify(error="nieznana kategoria"), 400
        theme, cache_key = cat["seed"], f"cat_{cat_id}"
    elif prompt:
        theme = prompt
        cache_key = "p_" + hashlib.md5(prompt.lower().encode()).hexdigest()[:12]
    else:
        return jsonify(error="podaj prompt albo kategorię"), 400

    cache_file = CACHE / f"{cache_key}.json"
    if cache_file.exists() and not data.get("fresh"):
        return jsonify(json.loads(cache_file.read_text(encoding="utf-8")))

    items = _validated(sources.gather(theme))
    if not items:
        return jsonify(items=builtin_shapes(), source="builtin",
                       warning="żadne źródło nie zwróciło kształtów — "
                               "pokazuję wbudowane")
    result = {"items": items, "source": "mixed"}
    cache_file.write_text(json.dumps(result, ensure_ascii=False),
                          encoding="utf-8")
    return jsonify(result)


@app.get("/api/builtin")
def builtin():
    return jsonify(items=builtin_shapes(), source="builtin")


@app.post("/api/model")
def model():
    data = request.get_json(force=True)
    path_d = data.get("path", "")
    mode = data.get("mode", "cutter")
    name = re.sub(r"[^a-z0-9ąćęłńóśźż]+", "_",
                  str(data.get("name", "ksztalt")).lower()).strip("_") or "ksztalt"
    if mode not in ("cutter", "stamp"):
        return jsonify(error="mode: cutter|stamp"), 400

    over = {}
    for k in DEFAULTS:
        if k in data:
            try:
                over[k] = float(data[k])
            except (TypeError, ValueError):
                return jsonify(error=f"zły parametr {k}"), 400

    try:
        poly = geometry.path_to_polygon(path_d)
        mesh = (geometry.build_cutter if mode == "cutter"
                else geometry.build_stamp)(poly, **over)
    except Exception as e:
        return jsonify(error=f"nie udało się zbudować bryły: {e}"), 422

    check = geometry.sanity(mesh)
    h = hashlib.md5((path_d + mode + json.dumps(over, sort_keys=True))
                    .encode()).hexdigest()[:10]
    fname = f"{name}_{mode}_{h}.stl"
    mesh.export(OUT / fname)
    return jsonify(url=f"/out/{fname}", file=fname, **check)


@app.get("/out/<path:fname>")
def out_file(fname):
    return send_from_directory(OUT, fname)


OUT.mkdir(exist_ok=True)
CACHE.mkdir(exist_ok=True)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", PORT))       # Render ustawia $PORT
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    print(f"cutterForge -> http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
