"""Integration checks for the packaged runtime and its persistent restart state."""
from pathlib import Path
import importlib.util
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
asset = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"
original_cwd = Path.cwd()
with tempfile.TemporaryDirectory(prefix="sora-runtime-test-") as tmp:
    runtime = Path(tmp) / "runtime"
    with zipfile.ZipFile(asset) as z:
        assert z.testzip() is None
        assert not any(n.startswith("data/") for n in z.namelist()), "User database must stay private"
        for name in z.namelist():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
        z.extractall(runtime)
    sys.path.insert(0, str(runtime))
    from clean_core.document_database import DocumentDatabase
    database = runtime / "data/drogowskazy.sqlite3"
    store = DocumentDatabase(database)
    def add(text, name):
        return store.begin_import(text=text, filename=name, relative_path="Test/" + name,
            extension=".txt", encoding="utf-8", source_bytes=len(text.encode()), app_version="test")
    done = add("Rada miasta przyjęła uchwałę. Burmistrz poinformował o decyzji.", "done.txt")
    done_id = done["document"]["id"]
    store.mark_success(done_id, {"analysis_run_id": "completed-before-restart", "podsumowanie": {}},
        expected_content_sha256=done["document"]["content_sha256"])
    pending = add("Premier powiedział, że rząd przedstawi projekt ustawy. Sejm omówi nowe przepisy.", "pending.txt")
    with sqlite3.connect(database) as db:
        done_before = db.execute("SELECT updated_at,analysis_gzip,attempts FROM documents WHERE id=?", (done_id,)).fetchone()
    spec = importlib.util.spec_from_file_location("sora_test_bootstrap", ROOT / "app/src/main/python/android_bootstrap.py")
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    def get(path):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=30) as response:
            return response.read()
    try:
        assert bootstrap.start(str(runtime), port).startswith("started:")
        assert bootstrap.start(str(runtime), port).startswith("already_running:")
        slow_started, release_slow = threading.Event(), threading.Event()
        def slow_request():
            slow_started.set()
            assert release_slow.wait(10), "Test request was never released"
            return "finished"
        bootstrap._MODULE.app.add_url_rule("/test/slow", view_func=slow_request)
        health = json.loads(get("/api/health"))
        assert health["ok"] and health["background_service"]
        assert health["wersja"].startswith("4.5.12")
        assert b"Drogowskazy" in get("/")
        assert b"DrogowskazyAndroid.saveText" in get("/static/app.js")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            status = json.loads(get("/api/baza/status"))
            if status["stats"]["processing"] == 0:
                break
            time.sleep(0.2)
        assert status["stats"]["done"] == 2 and status["stats"]["error"] == 0, status
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT updated_at,analysis_gzip,attempts FROM documents WHERE id=?", (done_id,)).fetchone() == done_before
        backup = Path(tmp) / "backup.sqlite3"
        backup.write_bytes(get("/api/baza/pobierz"))
        with sqlite3.connect(backup) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert db.execute("SELECT count(*) FROM documents WHERE status='done'").fetchone()[0] == 2
        response, stop_result = [], []
        request_thread = threading.Thread(target=lambda: response.append(get("/test/slow")))
        request_thread.start()
        assert slow_started.wait(5)
        stop_thread = threading.Thread(target=lambda: stop_result.append(bootstrap.stop()))
        stop_thread.start()
        time.sleep(0.7)
        assert stop_thread.is_alive(), "Shutdown must wait for the running HTTP request"
        release_slow.set()
        request_thread.join(10)
        stop_thread.join(10)
        assert response == [b"finished"] and stop_result == ["stopped"]
        assert not bootstrap.is_running()
        assert bootstrap.start(str(runtime), port).startswith("started:")
        status = json.loads(get("/api/baza/status"))
        assert status["stats"]["done"] == 2 and status["stats"]["processing"] == 0
        assert status["background_import"]["recovered_after_restart"] == 0
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT updated_at,analysis_gzip,attempts FROM documents WHERE id=?", (done_id,)).fetchone() == done_before
        print("PASS: packaged runtime, server start, resumed pending queue, done records unchanged, SQLite export, safe HTTP drain, restart")
    finally:
        bootstrap.stop()
        os.chdir(original_cwd)
