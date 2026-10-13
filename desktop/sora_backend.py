"""Sora PC — wyłącznie lokalny silnik PHONE, bez bibliotek GUI, pythonnet i Qt."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import threading
import traceback

from werkzeug.serving import make_server
from engine import Engine
from local_session import ProtectedLocalApp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--test-output-drain", action="store_true")
    args = parser.parse_args()
    home = Path(args.data_dir)
    home.mkdir(parents=True, exist_ok=True)
    engine = None
    server = None
    try:
        engine = Engine(home)
        if args.self_test:
            with engine.module.app.test_client() as client:
                page = client.get("/")
                assert page.status_code == 200
                assert b"databasePanel" in page.data
                assert client.get("/api/baza/status").status_code == 200
            print("SORA_BACKEND_TEST_OK", flush=True)
            return
        from flask import jsonify, request
        # Endpointy Windows są chronione tą samą sesją co cały panel.
        # Nie przyjmujemy danych ani ścieżek pochodzących z Internetu.
        app = engine.module.app

        @app.get("/api/sora-pc/health")
        def windows_native_health():
            """Tanie sprawdzenie połączenia, nie dotyka SQLite ani obliczeń."""
            return jsonify(ok=True, backend="SoraSilnik", version=engine.version)

        @app.post("/api/sora-pc/<operation>")
        def windows_native_operation(operation):
            payload = request.get_json(silent=True) or {}
            path = Path(str(payload.get("path") or "")).resolve()
            if not path.is_absolute() or not str(path):
                return jsonify(ok=False, szczegoly="Nieprawidłowa ścieżka."), 400
            try:
                if operation == "backup":
                    engine.backup(path)
                    message = "Zapisano bezpieczną kopię SQLite."
                    result = {}
                elif operation == "restore":
                    previous = engine.restore(path)
                    message = "Przywrócono bazę po wykonaniu kopii."
                    result = {"previous": str(previous)}
                elif operation == "export":
                    engine.export_transfer(path)
                    message = "Zapisano pakiet TRANSFER ZIP."
                    result = {}
                elif operation == "import":
                    result = engine.import_transfer(path)
                    message = "Zaimportowano i scalono dane z TRANSFER."
                else:
                    return jsonify(ok=False, szczegoly="Nieznana operacja."), 404
                return jsonify(ok=True, message=message, result=result,
                               reload=operation in ("restore", "import"))
            except (ValueError, OSError) as exc:
                return jsonify(ok=False, szczegoly=str(exc)), 400

        guard = ProtectedLocalApp(app)
        server = make_server("127.0.0.1", 0, guard, threaded=True)
        print("SORA_READY:" + json.dumps({
            "url": guard.bootstrap_url(server.server_port),
            "port": server.server_port,
            "session": guard.secret,
            "engine_sha256": engine.identity["engine_sha256"]
        }, ensure_ascii=False, separators=(",", ":")), flush=True)

        if args.test_output_drain:
            # Test regresji: >128 KB stdout przed wejściem serwera HTTP.
            # Bez ciągłego odczytu strumienia host zatrzymałby backend.
            for i in range(900):
                print("CI_STDOUT_" + str(i) + "_" + ("A" * 220), flush=True)

        def shutdown_watcher():
            try:
                # Wyraźne "Zakończ Sorę" zatrzymuje backend.
                # Zamknięcie okna do zasobnika NIE zamyka stdin, więc analiza trwa.
                # Po awarii procesu hosta EOF bezpiecznie kończy ten proces.
                sys.stdin.readline()
            except Exception:
                pass
            server.shutdown()

        threading.Thread(target=shutdown_watcher, daemon=True).start()
        server.serve_forever()
    except Exception:
        (home / "blad_silnika_pc.txt").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        if server is not None:
            server.server_close()
        if engine is not None:
            engine.stop()


if __name__ == "__main__":
    main()
