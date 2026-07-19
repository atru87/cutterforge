# cutterForge — wycinaki i stemple z promptu AI

Wpisujesz motyw („zestaw świąteczny", „dinozaury", „postacie z bajki…") albo
klikasz jedną z ~60 kategorii — AI (Groq, darmowy tier) projektuje 5
sylwetek, a silnik geometrii zamienia wybraną w gotowy do druku STL:

- **wycinak (cutter)** — kołnierz do naciskania + korpus + cienkie ostrze
  (0,8 mm), drukowany kołnierzem do stołu, bez podpór;
- **stempel (stamp)** — płytka z wytłoczonym wzorem (lustrzanym, żeby odcisk
  był poprawny), dociskany płaskim grzbietem.

## Szybki start

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env    # i wpisz klucz z console.groq.com (darmowy)
start.bat                 # albo: .\.venv\Scripts\python.exe app.py
```

Strona: <http://127.0.0.1:5100>. Bez klucza API działa biblioteka
wbudowanych kształtów (serce, gwiazda, choinka…).

## Skąd biorą się kształty (kaskada źródeł)

Groq nie generuje obrazków — to modele tekstowe, a proszone o rysowanie
konturów dawały kleksy. Dlatego AI robi tylko to, w czym jest dobre:
**tłumaczy motyw na listę konkretnych obiektów** („święta" → choinka,
bałwan, sweter…), a same kształty przychodzą z prawdziwych grafik:

1. **🧩 Iconify** (api.iconify.design, darmowe, bez klucza) — ~200 tys.
   profesjonalnych ikon wektorowych (game-icons, Font Awesome, Material…);
   SVG jest parsowany do konturu i „chunkifikowany" pod fizyczny wycinak.
2. **🌐 Wyszukiwarka obrazów** (DuckDuckGo, bez klucza) — szukamy
   „X silhouette clipart", pobieramy kilku kandydatów, wektoryzujemy
   (OpenCV: próg + morfologia + kontury z dziurami) i bierzemy najlepszy.
   Pokrywa motywy, których nie ma w ikonach.
3. **🤖 DSL prymitywów** (Groq komponuje kształt z figur) — tylko gdy
   1 i 2 zawiodą; jakość wyraźnie niższa.
4. **📦 Wbudowane** kształty parametryczne — gdy wszystko inne padnie
   (np. brak internetu).

Emotka przy nazwie kształtu w UI mówi, skąd przyszedł. Wyniki są
cachowane w `cache/` (klik w tę samą kategorię = zero sieci); przycisk
„🔄 inne warianty" wymusza świeżą generację.

- modele w `config.py`: `openai/gpt-oss-120b`, fallback
  `llama-3.3-70b-versatile`; darmowy tier Groq = 8000 tokenów/min,
  ale zapytanie o słowa kluczowe jest małe (~1–2 tys.), więc limit
  praktycznie nie przeszkadza

## Parametry (UI, sekcja „Ustawienia modelu")

| parametr | domyślnie | uwagi |
|---|---|---|
| rozmiar | 70 mm | najdłuższy wymiar kształtu |
| wys. ostrza / korpusu | 10 / 6 mm | łącznie 16 mm wysokości |
| grubość ostrza | 0,8 mm | = 2 ścieżki dyszy 0,4 |
| grubość korpusu | 1,6 mm | usztywnienie |
| kołnierz | 4 mm | półka do naciskania palcami |
| relief stempla | 1,5 mm | + płytka 3 mm |

## Druk

PLA/PETG, warstwa 0,2 mm, bez podpór. Wycinak drukuje się kołnierzem do
stołu (ostrze na górze). Do kontaktu z żywnością: PETG + świadomość, że
druk FDM ma mikroszczeliny (do ciastek okazjonalnie OK, do gliny bez
ograniczeń).

## Struktura

```
cutterForge/
├── app.py            # Flask :5100 — API + statyczne UI
├── ai.py             # Groq: prompt -> DSL prymitywów -> kontur
├── shapes_dsl.py     # składanie prymitywów (shapely)
├── geometry.py       # kontur -> bryła wycinaka/stempla (trimesh)
├── builtin_shapes.py # kształty parametryczne (fallback bez API)
├── categories.json   # ~60 kategorii bazowych (motyw -> seed dla AI)
├── web/index.html    # UI: prompt, kategorie, podgląd three.js, STL
├── cache/            # zcachowane odpowiedzi AI (JSON)
└── out/              # wygenerowane STL
```
