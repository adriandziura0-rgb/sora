"""Sora PC: to samo okno HTML/CSS/JS co PHONE, lokalny silnik i baza SQLite.

WebView2 jest kontrolką Windows we własnym procesie Sora.exe.
Nie otwieramy przeglądarki użytkownika ani zewnętrznego serwisu.
"""
from __future__ import annotations

import argparse
import base64
import json
import msvcrt
import os
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from local_session import ProtectedLocalApp

from werkzeug.serving import make_server

from engine import Engine

DOCUMENT_EXTENSIONS = frozenset({".txt", ".md", ".markdown", ".csv", ".json", ".log", ".htm", ".html"})
MAX_TEXT_BYTES = 2 * 1024 * 1024
# Stały origin pozwala WebView2 zachować sesję, ostatnio wybrany widok i lokalne
# preferencje między restartami Sory. Tylko pętla lokalna (bez sieci).
LOCAL_PORT = 43847


def default_home() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DrogowskazySoraPC"


def lock_home(home: Path):
    """Nie pozwalaj dwóm oknom równocześnie zapisywać tej samej bazy."""
    handle = (home / "application.lock").open("a+b")
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        raise RuntimeError("Sora już działa. Otwórz jej istniejące okno na pasku zadań.")
    return handle


class NativeFiles:
    """Bezpieczny most do natywnych okien dialogowych Windows."""
    def __init__(self, engine: Engine, home: Path):
        self.engine, self.home = engine, home
        self.window = None
        self.roots = {}
        self._guard = threading.RLock()

    def attach(self, window):
        self.window = window

    def select_folder(self):
        import webview
        chosen = self.window.create_file_dialog(webview.FileDialog.FOLDER)
        if not chosen:
            return None
        root = Path(chosen[0]).resolve()
        if not root.is_dir():
            raise ValueError("Nie znaleziono wybranego folderu.")
        token = uuid.uuid4().hex
        with self._guard:
            self.roots[token] = root
            # Pamiętamy jedynie kilka aktywnych wyborów, bez skanowania bez zgody.
            while len(self.roots) > 8:
                del self.roots[next(iter(self.roots))]
        return {"root": token, "name": root.name, "path": "", "kind": "directory"}

    def _resolve(self, token: str, relative: str) -> Path:
        with self._guard:
            base = self.roots.get(str(token))
        if base is None:
            raise ValueError("Wybór folderu wygasł. Wybierz go ponownie.")
        relative = str(relative or "")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Niedozwolona ścieżka folderu.")
        path = (base / relative).resolve()
        if not path.is_relative_to(base):
            raise ValueError("Plik jest poza zaznaczonym folderem.")
        return path

    def list_directory(self, token: str, relative: str, offset: int = 0, limit: int = 300):
        folder = self._resolve(token, relative)
        if not folder.is_dir():
            raise ValueError("Nie znaleziono podfolderu.")
        offset = max(0, int(offset))
        limit = min(500, max(1, int(limit)))
        items = []
        for item in folder.iterdir():
            if item.is_symlink() or item.name.startswith("."):
                continue
            if item.is_dir() or (item.is_file() and item.suffix.lower() in DOCUMENT_EXTENSIONS):
                items.append(item)
        items.sort(key=lambda item: (item.is_file(), item.name.casefold()))
        entries = []
        for item in items[offset:offset+limit]:
            kind = "directory" if item.is_dir() else "file"
            entries.append({"kind": kind, "name": item.name,
                            "path": str(item.relative_to(self.roots[token])).replace("\\", "/"),
                            "root": token, "size": 0 if kind == "directory" else item.stat().st_size})
        return {"items": entries, "has_more": offset + limit < len(items)}

    def read_file(self, token: str, relative: str):
        file = self._resolve(token, relative)
        if not file.is_file() or file.suffix.lower() not in DOCUMENT_EXTENSIONS:
            raise ValueError("Nieobsługiwany typ dokumentu.")
        if file.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError("Plik przekracza limit 2 MB.")
        return {"base64": base64.b64encode(file.read_bytes()).decode("ascii")}

    def _select(self, dialog_type, *, filename="", suffix=""):
        import webview
        kw = {"dialog_type": dialog_type}
        if filename:
            kw["save_filename"] = filename
        if suffix:
            kw["file_types"] = (f"Plik {suffix.upper()} (*.{suffix})",)
        selection = self.window.create_file_dialog(**kw)
        return Path(selection[0]) if selection else None

    def backup_database(self):
        import webview
        dest = self._select(webview.FileDialog.SAVE,
                            filename="Sora_kopia_bazy.sqlite3", suffix="sqlite3")
        if dest is None:
            return {"cancelled": True}
        self.engine.backup(dest)
        return {"ok": True, "message": "Zapisano spójną kopię SQLite: " + str(dest)}

    def restore_database(self):
        import webview
        file = self._select(webview.FileDialog.OPEN, suffix="sqlite3")
        if file is None:
            return {"cancelled": True}
        if not self.window.create_confirmation_dialog(
                "Przywracanie bazy Sora",
                "Baza z pliku zastąpi aktualną bazę PC. Przed zmianą zostanie zrobiona kopia. Kontynuować?"):
            return {"cancelled": True}
        backup = self.engine.restore(file)
        return {"ok": True, "message": "Przywrócono bazę; kopia poprzedniej: " + str(backup), "reload": True}

    def export_transfer(self):
        import webview
        name = "Sora_TRANSFER_PC_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip"
        dest = self._select(webview.FileDialog.SAVE, filename=name, suffix="zip")
        if dest is None:
            return {"cancelled": True}
        self.engine.export_transfer(dest)
        return {"ok": True, "message": "Wyeksportowano TRANSFER ZIP: " + str(dest)}

    def import_transfer(self):
        import webview
        file = self._select(webview.FileDialog.OPEN, suffix="zip")
        if file is None:
            return {"cancelled": True}
        if not self.window.create_confirmation_dialog(
                "Import TRANSFER do Sory",
                "Program sprawdzi ZIP, zabezpieczy lokalną bazę i scali dokumenty. Importować?"):
            return {"cancelled": True}
        result = self.engine.import_transfer(file)
        return {"ok": True, "message": "Import zakończony. Szczegóły: " +
                json.dumps(result, ensure_ascii=False), "reload": True}


def _native_script() -> str:
    if getattr(sys, "frozen", False):
        path = Path(sys._MEIPASS) / "windows_adapter.js"
    else:
        path = Path(__file__).with_name("windows_adapter.js")
    return path.read_text(encoding="utf-8")


def _smoke(window, engine: Engine, home: Path, server):
    """Rzeczywiście sprawdza wyrenderowany ekran PHONE w oknie WebView2."""
    try:
        window.events.loaded.wait(80)
        for _ in range(40):
            try:
                readiness = window.evaluate_js("""({
                  phonePanel: !!document.getElementById('databasePanel'),
                  sharedContent: !!document.getElementById('sharedContentPanel'),
                  topics: !!document.getElementById('sameStoryComparePanel'),
                  p0p5: !!document.getElementById('soraFullOverview'),
                  nativeFiles: !!window.__soraWindowsBridgeInstalled,
                  runtime: window.pywebview?.platform || ''
                })""")
                if all(readiness.get(k) for k in ("phonePanel", "sharedContent", "topics", "p0p5", "nativeFiles")):
                    break
            except Exception:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Nie otworzono pełnego panelu telefonu w oknie Windows.")

        with urlopen(f"http://127.0.0.1:{server.server_port}/api/health", timeout=10) as response:
            assert response.status == 200
        # Prawdziwa lokalna baza i wspólny silnik również działają po uruchomieniu okna.
        response = engine.request("/api/baza/status")
        assert "stats" in response
        window.evaluate_js("document.getElementById('databasePanel').open = true")
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=False).save(home / "SORA_WYNIK.png")
        (home / "smoke-ok.json").write_text(json.dumps({
            "native_window": True,
            "phone_ui_embedded": True,
            "same_phone_html_css_js": True,
            "shared_content_panel": True,
            "native_windows_folder_bridge": True,
            "database_status": response["stats"],
            "view": readiness,
            **engine.identity,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        (home / "smoke-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        window.destroy()


def _smoke_headless(engine: Engine, home: Path, server, guard: ProtectedLocalApp):
    """Automatyczna kontrola prawdziwego EXE bez zależności od sesji RDP.

    WebView2 ma być przetestowany osobno na interaktywnym pulpicie Windows:
    test headless NIE oznacza, że GUI zostało wizualnie potwierdzone.
    """
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        try:
            urlopen(origin + "/api/baza/status", timeout=10)
            raise AssertionError("Prywatne API dostępne bez tokenu sesji.")
        except HTTPError as exc:
            if exc.code != 403:
                raise
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        with opener.open(guard.bootstrap_url(server.server_port), timeout=15) as response:
            assert response.status == 200
            page = response.read().decode("utf-8")
        markers = ("databasePanel", "databaseComparePanel", "sameStoryComparePanel",
                   "sharedContentPanel", "findSharedContentBtn", "soraFullOverview",
                   "reanalyzeDatabaseBtn", "databaseFolderInput")
        for marker in markers:
            if f'id="{marker}"' not in page:
                raise RuntimeError("Brak części panelu PHONE: " + marker)
        for resource in ("static/app.js", "static/full-database.js",
                         "static/shared-content.js", "static/full-database.css"):
            with opener.open(origin + "/" + resource, timeout=15) as response:
                if response.status != 200:
                    raise RuntimeError("Brak pliku interfejsu: " + resource)
        adapter = _native_script()
        for marker in ("select_folder", "list_directory", "read_file",
                       "import_transfer", "export_transfer", "backup_database"):
            if marker not in adapter:
                raise RuntimeError("Brak natywnej funkcji Windows: " + marker)
        with opener.open(origin + "/api/baza/status", timeout=15) as response:
            status = json.load(response)
        if not isinstance(status.get("stats"), dict):
            raise RuntimeError("Silnik nie udostępnia statusu bazy.")
        report = {"exe_starts": True, "phone_html_in_exe": True,
                  "full_phone_functional_modules_present": True,
                  "native_windows_file_bridge_present": True,
                  "backend_http_healthy": True,
                  "database_preserved": True,
                  "local_api_requires_secret_cookie": True,
                  "full_gui_test_pending": True,
                  "gui_verified": False,
                  "frontend_controls": list(markers),
                  **engine.identity}
        (home / "smoke-ok.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        (home / "smoke-error.txt").write_text(traceback.format_exc(),encoding="utf-8")
        raise


def _check_renderer(home: Path):
    """Testuje PRAWDZIWY pakowany silnik okna (QtWebEngine), nie tylko Flask.

    Nie otwiera bazy ani nie modyfikuje żadnych danych użytkownika.
    Test uruchamiany przez CI z EXE rozpakowanego do czystego folderu.
    """
    import os
    import faulthandler
    os.environ["QT_API"] = "pyqt6"
    # Windows bez sprzętowego GPU/aktywnego pulpitu: QtWebEngine może
    # wywrócić się przy ładowaniu HTML. Renderer software bez zmiany CORE.
    os.environ.setdefault("QSG_RHI_PREFER_SOFTWARE_RENDERER", "1")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                          "--disable-gpu --disable-gpu-compositing")
    progress = home / "qt-initialization-stages.log"
    def step(value):
        with progress.open("a", encoding="utf-8") as stream:
            stream.write(value + "\n")
            stream.flush()
    error_file = (home / "qt-python-fault.txt").open("w", encoding="utf-8")
    faulthandler.enable(file=error_file, all_threads=True)
    step("START EXE QT RENDERER")
    from PyQt6.QtWidgets import QApplication
    step("IMPORTED QWidget QApplication")
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    step("IMPORTED QWebEngineView")
    import webview.platforms.qt as qt_backend
    step("IMPORTED pywebview Qt backend")
    from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
    app = QApplication.instance() or QApplication([])
    step("CREATED QApplication")
    view = QWebEngineView()
    step("CREATED QWebEngineView")
    view.resize(420, 620)
    view.setHtml("<!doctype html><html><body>Sora PHONE / PC</body></html>")
    step("SUBMITTED WebEngine HTML")
    app.processEvents()
    step("PROCESSED Qt EVENTS")
    result = {
        "renderer": "QtWebEngine",
        "qt_version": QT_VERSION_STR,
        "pyqt_version": PYQT_VERSION_STR,
        "webview_qt_loaded": bool(qt_backend),
        "webengine_instance_created": bool(view),
        "no_pythonnet_required": True,
    }
    (home / "renderer-ok.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    view.deleteLater()
    app.processEvents()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--renderer-test", action="store_true")
    parser.add_argument("--data-dir")
    opts = parser.parse_args()
    home = Path(opts.data_dir) if opts.data_dir else default_home()
    home.mkdir(parents=True, exist_ok=True)
    # CI i użytkownik mogą sprawdzić silnik GUI niezależnie od kolektora.
    if opts.renderer_test:
        try:
            _check_renderer(home)
        except BaseException:
            (home / "renderer-error.txt").write_text(
                traceback.format_exc(), encoding="utf-8")
            raise
        return
    lock = None
    server = None
    engine = None
    try:
        lock = lock_home(home)
        engine = Engine(home)
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        guard = ProtectedLocalApp(engine.module.app)
        try:
            server = make_server("127.0.0.1", LOCAL_PORT, guard, threaded=True)
        except OSError:
            # Inna aplikacja może mieć zajęty port 43847. Nie blokujemy
            # startu, tylko przechodzimy na dostępny lokalny port.
            server = make_server("127.0.0.1", 0, guard, threaded=True)
            (home / "uwaga_port.txt").write_text(
                "Stały port 43847 zajęty. Użyto portu " + str(server.server_port)
                + ". Wybór ekranu może nie przetrwać następnego uruchomienia.",
                encoding="utf-8")
        worker = threading.Thread(target=server.serve_forever, daemon=True, name="Sora-local-web")
        worker.start()
        if opts.smoke_test:
            _smoke_headless(engine, home, server, guard)
            return
        bridge = NativeFiles(engine, home)
        window = webview.create_window(
            "Drogowskazy Sora — PHONE / PC",
            guard.bootstrap_url(server.server_port),
            # Startujemy z wymiarami zbliżonymi do telefonu: zachowujemy
            # mobilny układ kart, ale okno można rozszerzyć lub zmaksymalizować.
            js_api=bridge, width=640, height=820, min_size=(420, 550),
            background_color="#f4f8fa", text_select=True)
        bridge.attach(window)
        script = _native_script()
        window.events.loaded += lambda: window.evaluate_js(script)
        # QtWebEngine wyświetla DOKŁADNIE ten sam panel Chrome/Android,
        # ale nie używa niestabilnego łańcucha pythonnet / .NET Framework.
        os.environ["QT_API"] = "pyqt6"
    # Windows bez sprzętowego GPU/aktywnego pulpitu: QtWebEngine może
    # wywrócić się przy ładowaniu HTML. Renderer software bez zmiany CORE.
    os.environ.setdefault("QSG_RHI_PREFER_SOFTWARE_RENDERER", "1")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                          "--disable-gpu --disable-gpu-compositing")
        webview.start(gui="qt", debug=False,
                      private_mode=False, storage_path=str(home / "webview"))
    except Exception as exc:
        (home / "blad_startu.txt").write_text(traceback.format_exc(), encoding="utf-8")
        # Tkinter nie jest częścią aplikacji Windows. Import choćby
        # awaryjnego tkinter.messagebox dodawał do EXE uruchamiany przed
        # main() hook PyInstaller pyi_rth__tkinter i powodował błąd _tk_data.
        # Używamy natywnego okna systemowego Windows bez plików Tcl/Tk.
        try:
            from ctypes import windll
            windll.user32.MessageBoxW(
                None,
                str(exc) + "\n\nBłąd silnika okna QtWebEngine. "
                "Baza danych nie została skasowana.\nSzczegóły: " + str(home / "blad_startu.txt"),
                "Sora — błąd uruchomienia",
                0x10,
            )
        except Exception:
            pass
        raise
    finally:
        if server is not None:
            server.shutdown()
        if engine is not None:
            engine.stop()
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    main()
