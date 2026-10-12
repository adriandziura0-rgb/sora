"""Test PC: prawdziwy panel PHONE i most Windows, bez uruchamiania GUI.

Pełny test EXE z oknem WebView2 wykonuje drugi etap workflow.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
from engine import Engine
from sora_pc_webview import NativeFiles, _native_script, LOCAL_PORT


def check():
    with TemporaryDirectory(prefix="sora-phone-pc-") as tmp:
        home = Path(tmp)
        engine = Engine(home)
        try:
            with engine.module.app.test_client() as client:
                page = client.get("/")
                assert page.status_code == 200
                html = page.get_data(as_text=True)
                markers = (
                    'id="databasePanel"', 'id="databaseComparePanel"',
                    'id="sameStoryComparePanel"', 'id="sharedContentPanel"',
                    'id="findSharedContentBtn"', 'id="openFullOverviewBtn"',
                    'id="reanalyzeDatabaseBtn"', 'id="databaseFilesInput"',
                    'id="downloadDatabaseBtn"',
                )
                for marker in markers:
                    assert marker in html, f"Brak przycisku/sekcji: {marker}"
                for path in ("static/app.js", "static/full-database.js",
                             "static/shared-content.js"):
                    assert client.get("/" + path).status_code == 200, path
                status = client.get("/api/baza/status").get_json()
                assert status.get("stats") is not None

            adapter = _native_script()
            for feature in ("showDirectoryPicker", "read_file", "list_directory",
                            "export_transfer", "import_transfer", "restore_database",
                            "backup_database"):
                assert feature in adapter, feature

            files = NativeFiles(engine, home)
            root = home / "testowy_folder"
            root.mkdir()
            (root / "plik.txt").write_text("Materiał testowy", encoding="utf-8")
            (root / "pomoc.exe").write_bytes(b"Nie importuj")
            (root / "podfolder").mkdir()
            (root / "podfolder"/"fragment.md").write_text("Próbny tekst",encoding="utf-8")
            token = uuid.uuid4().hex
            files.roots[token] = root.resolve()
            items = files.list_directory(token,"")
            names = {item["name"] for item in items}
            assert names == {"plik.txt", "podfolder"}, names
            sub = files.list_directory(token, "podfolder")
            assert len(sub)==1 and sub[0]["name"]=="fragment.md"
            import base64
            assert base64.b64decode(files.read_file(token,"plik.txt")["base64"]).decode("utf-8")=="Materiał testowy"
            for attack in ("../plik.txt", str(home / "application.lock")):
                try:
                    files.read_file(token, attack)
                    raise AssertionError("Odczyt spoza folderu: " + attack)
                except ValueError:
                    pass

            assert isinstance(LOCAL_PORT,int) and LOCAL_PORT>1024
            print("PASS: PHONE HTML/CSS/JS on PC, shared content, comparison, database, "
                  "scoped native folder API, transfer controls, stable persistent origin")
        finally:
            engine.stop()


if __name__ == "__main__":
    check()
