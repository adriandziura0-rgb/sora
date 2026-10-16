"""Regresja zabezpieczenia lokalnego HTTP: żaden obcy proces ani strona
nie może odczytać API Sora PC bez sekretnej sesji natywnego okna."""
from flask import Flask, jsonify
from werkzeug.test import Client
from werkzeug.wrappers import Response
from local_session import ProtectedLocalApp

app = Flask(__name__)
@app.get("/")
def index():
    return "<h1>Sora</h1>"
@app.get("/api/baza/status")
def status():
    return jsonify(stats={"total": 554})
@app.post("/api/baza/zmiana")
def mutate():
    return jsonify(ok=True)

guard = ProtectedLocalApp(app)
http = Client(guard, Response)
host = "127.0.0.1:43847"

assert http.get("/", headers={"Host":host}).status_code == 403
assert http.get("/api/baza/status", headers={"Host":host}).status_code == 403
assert http.post("/api/baza/zmiana", headers={"Host":host}).status_code == 403
assert http.get(guard.bootstrap_url(43847), headers={"Host":"nieznany"}).status_code == 403
assert http.get("/?sora_launch=błędny", headers={"Host":host}).status_code == 403

result = http.get("/?sora_launch=" + guard.secret, headers={"Host":host})
assert result.status_code == 302
assert result.headers["Location"] == "/"
assert "HttpOnly" in result.headers["Set-Cookie"]
assert "SameSite=Strict" in result.headers["Set-Cookie"]
assert http.get("/", headers={"Host":host}).status_code == 200
assert http.get("/api/baza/status", headers={"Host":host}).get_json()["stats"]["total"] == 554
assert http.post("/api/baza/zmiana", headers={
    "Host":host,"Origin":"https://zlosliwa-strona.invalid"
}).status_code == 403
assert http.post("/api/baza/zmiana", headers={
    "Host":host,"Origin":"http://"+host
}).status_code == 200

print("PASS: private localhost UI; session bootstrap, cookie, origin, and blocked unauthorized DB access")
