"""Uruchamia projekt Drogowskazy wybrany przez użytkownika jako lokalny serwer Flask.

Ten moduł jest częścią APK. Sam projekt (app.py, clean_core, templates, static i baza)
jest importowany z ZIP-a do prywatnego katalogu aplikacji, dzięki czemu repozytorium nie
musi przechowywać bazy użytkownika ani kolejnych wersji analizatora.
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
    global _SERVER, _THREAD, _PROJECT_DIR, _LAST_ERROR
    project_dir = str(Path(project_dir).resolve())
    port = int(port)
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive() and _PROJECT_DIR == project_dir:
            return f"already_running:{port}"
        try:
            if _SERVER is not None:
                try:
                    _SERVER.shutdown()
                except Exception:
                    pass
            flask_app = _load_app(project_dir)
            _SERVER = make_server("127.0.0.1", port, flask_app, threaded=True)
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
    global _SERVER, _THREAD, _PROJECT_DIR
    with _LOCK:
        if _SERVER is not None:
            try:
                _SERVER.shutdown()
            finally:
                _SERVER = None
        if _THREAD is not None:
            _THREAD.join(timeout=3.0)
            _THREAD = None
        _PROJECT_DIR = None
    return "stopped"


def is_running() -> bool:
    with _LOCK:
        return bool(_THREAD is not None and _THREAD.is_alive())


def last_error() -> str:
    return _LAST_ERROR
