"""Uruchamia dołączony do APK program Drogowskazy w prywatnej pamięci aplikacji.

Program instaluje się automatycznie z zasobów APK. Baza użytkownika pozostaje
w prywatnym katalogu data i jest zachowywana przy aktualizacji programu.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import threading
import traceback
from typing import Optional

from werkzeug.serving import make_server

_LOCK = threading.RLock()
_SERVER = None
_THREAD: Optional[threading.Thread] = None
_MODULE = None
_PROJECT_DIR: Optional[str] = None
_LAST_ERROR = ""
_REQUESTS = None


class _TrackedRequests:
    """Nie pozwala podmienić programu/bazy podczas trwającego żądania HTTP."""

    def __init__(self, app):
        self.app = app
        self.condition = threading.Condition()
        self.active = 0
        self.closing = False

    def __call__(self, environ, start_response):
        with self.condition:
            if self.closing:
                start_response("503 Service Unavailable", [("Content-Type", "application/json")])
                return [b'{"ok":false,"blad":"serwer_jest_zatrzymywany"}']
            self.active += 1
        try:
            response = self.app(environ, start_response)
        except BaseException:
            self.finished()
            raise

        def stream():
            try:
                yield from response
            finally:
                try:
                    if hasattr(response, "close"):
                        response.close()
                finally:
                    self.finished()
        return stream()

    def finished(self):
        with self.condition:
            self.active -= 1
            self.condition.notify_all()

    def begin_stop(self):
        with self.condition:
            self.closing = True

    def wait_idle(self, timeout):
        with self.condition:
            return self.condition.wait_for(lambda: self.active == 0, timeout=timeout)


def _purge_runtime_modules() -> None:
    for name in list(sys.modules):
        if name == "drogowskazy_runtime_app" or name.startswith("clean_core"):
            sys.modules.pop(name, None)


def _load_app(project_dir: str):
    global _MODULE
    root = Path(project_dir).resolve()
    app_path = root / "app.py"
    if not app_path.is_file():
        raise FileNotFoundError(f"Brak app.py: {app_path}")

    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DROGOWSKAZY_DB_PATH"] = str(data_dir / "drogowskazy.sqlite3")
    os.environ["DROGOWSKAZY_BACKGROUND_SERVICE"] = "1"
    os.environ["DROGOWSKAZY_PORT"] = os.environ.get("DROGOWSKAZY_PORT", "5433")

    root_str = str(root)
    if root_str in sys.path:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)
    os.chdir(root_str)
    _purge_runtime_modules()

    spec = importlib.util.spec_from_file_location("drogowskazy_runtime_app", app_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Nie można utworzyć loadera app.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["drogowskazy_runtime_app"] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "app"):
        raise RuntimeError("app.py nie udostępnia obiektu Flask 'app'")
    _MODULE = module
    return module.app


def start(project_dir: str, port: int = 5433) -> str:
    """Uruchom serwer, jeśli jeszcze nie działa. Wywołanie jest idempotentne."""
    global _SERVER, _THREAD, _PROJECT_DIR, _LAST_ERROR, _REQUESTS
    project_dir = str(Path(project_dir).resolve())
    port = int(port)
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive() and _PROJECT_DIR == project_dir:
            return f"already_running:{port}"
        try:
            if _MODULE is not None or _SERVER is not None:
                stop()
            flask_app = _load_app(project_dir)
            _REQUESTS = _TrackedRequests(flask_app)
            _SERVER = make_server("127.0.0.1", port, _REQUESTS, threaded=True)
            _THREAD = threading.Thread(
                target=_SERVER.serve_forever,
                name="DrogowskazyFlask",
                daemon=True,
            )
            _THREAD.start()
            _PROJECT_DIR = project_dir
            _LAST_ERROR = ""
            return f"started:{port}"
        except Exception:
            _LAST_ERROR = traceback.format_exc()
            raise


def stop() -> str:
    global _SERVER, _THREAD, _PROJECT_DIR, _MODULE, _LAST_ERROR, _REQUESTS
    with _LOCK:
        if _REQUESTS is not None:
            _REQUESTS.begin_stop()
        if _SERVER is not None:
            try:
                _SERVER.shutdown()
            finally:
                _SERVER.server_close()
                _SERVER = None
        if _THREAD is not None:
            _THREAD.join(timeout=5.0)
            _THREAD = None

        if _REQUESTS is not None and not _REQUESTS.wait_idle(45.0):
            _LAST_ERROR = "Żądanie HTTP jeszcze zapisuje wynik. Podmiana programu lub bazy została zatrzymana."
            raise RuntimeError(_LAST_ERROR)

        # Nowsze runtime'y udostępniają hook zatrzymujący worker kolejki SQLite.
        # Najpierw przestajemy przyjmować HTTP, potem czekamy na aktywny zapis.
        module = _MODULE
        if module is not None and hasattr(module, "shutdown_background_worker"):
            try:
                stopped = module.shutdown_background_worker(45.0)
                if stopped is False:
                    raise RuntimeError("Worker kolejki nie zatrzymał się w wymaganym czasie")
            except Exception:
                _LAST_ERROR = traceback.format_exc()
                raise

        _MODULE = None
        _REQUESTS = None
        _PROJECT_DIR = None
    return "stopped"


def is_running() -> bool:
    with _LOCK:
        return bool(_THREAD is not None and _THREAD.is_alive())


def last_error() -> str:
    return _LAST_ERROR
