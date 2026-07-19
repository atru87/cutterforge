"""Bramka hasła dla całej aplikacji.

Hasło przychodzi ze zmiennej środowiskowej PLATFORM_PASSWORD (na Renderze
z environment group "grp"). Gdy zmienna NIE jest ustawiona — np. przy
uruchomieniu lokalnym — bramka jest nieaktywna; to jedyny "wyłącznik"
i jest jawny. Poza tym zero backdoorów: jedyna droga do środka to
poprawne hasło, porównywane stałoczasowo (hmac.compare_digest).

Sesja trzymana w podpisanym cookie Flaska; klucz podpisu wyprowadzany
z hasła — zmiana hasła unieważnia wszystkie sesje.
"""

import hashlib
import hmac
import os
from datetime import timedelta

from flask import redirect, render_template_string, request, session

PASSWORD = os.environ.get("PLATFORM_PASSWORD", "")

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Logowanie</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;
    background:#12141a;color:#e8eaf0;font-family:'Segoe UI',system-ui,sans-serif}
  form{background:#1a1d26;border:1px solid #2c3140;border-radius:14px;
    padding:34px 38px;display:flex;flex-direction:column;gap:14px;min-width:280px}
  h1{margin:0 0 4px;font-size:18px}
  p{margin:0;color:#8b93a7;font-size:13px}
  input{background:#20242f;border:1px solid #2c3140;color:#e8eaf0;
    border-radius:8px;padding:11px 12px;font-size:15px}
  button{background:#f0a35e;border:0;color:#1a120a;font-weight:700;
    border-radius:8px;padding:11px;font-size:15px;cursor:pointer}
  .err{color:#e06c6c;font-size:13px;min-height:16px}
</style></head><body>
<form method="post" action="/login">
  <h1>🔒 Dostęp chroniony</h1>
  <p>Podaj hasło platformy, aby kontynuować.</p>
  <input type="password" name="password" placeholder="hasło" autofocus autocomplete="current-password">
  <div class="err">{{ error }}</div>
  <button type="submit">Wejdź</button>
</form></body></html>"""


def init_auth(app, salt: str):
    """Podpina bramkę do aplikacji Flask. salt różnicuje klucz sesji
    między aplikacjami (cookie z jednej nie otwiera drugiej)."""
    if not PASSWORD:
        return
    app.secret_key = hashlib.sha256(f"{salt}::{PASSWORD}".encode()).digest()
    app.permanent_session_lifetime = timedelta(days=30)

    @app.before_request
    def _gate():
        if request.path == "/login":
            return None
        if session.get("auth_ok"):
            return None
        if request.path.startswith("/api/") or request.method != "GET":
            return {"error": "wymagane hasło — otwórz stronę i zaloguj się"}, 401
        return redirect("/login")

    @app.route("/login", methods=["GET", "POST"])
    def _login():
        error = ""
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("password", ""), PASSWORD):
                session.permanent = True
                session["auth_ok"] = True
                return redirect("/")
            error = "Błędne hasło."
        return render_template_string(_LOGIN_HTML, error=error), \
            401 if error else 200
