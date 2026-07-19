"""Konfiguracja cutterForge — wszystko podmienialne w jednym miejscu."""

# Model Groq (darmowy tier). Gdy Groq wycofa model — podmień tu.
# gpt-oss-120b (rozumujący) daje DUŻO lepsze sylwetki niż llama.
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Ile kształtów na jedno zapytanie (kategoria / prompt)
SHAPES_PER_REQUEST = 15

# Retry przy błędach API
MAX_RETRIES = 3
RETRY_DELAY_S = 2.0

# Port serwera www
PORT = 5100

# ---- domyślne parametry geometrii (mm) ----
DEFAULTS = dict(
    size=70.0,        # docelowy najdłuższy wymiar kształtu
    blade_h=10.0,     # wysokość części tnącej (cienkie ostrze)
    body_h=6.0,       # wysokość korpusu (grubsza ścianka, usztywnienie)
    blade_t=0.8,      # grubość ostrza — 2 ścieżki dyszy 0.4
    body_t=1.6,       # grubość korpusu
    flange_w=3.0,     # szerokość kołnierza do naciskania palcami
    flange_t=1.5,     # grubość (wysokość) kołnierza
    # ---- stempel ----
    stamp_relief=1.5,   # wysokość reliefu wzoru
    stamp_base_t=3.0,   # grubość płytki bazowej
    stamp_margin=4.0,   # margines płytki wokół wzoru
)
