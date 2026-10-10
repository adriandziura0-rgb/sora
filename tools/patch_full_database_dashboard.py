"""Assemble a read-only, full-database dashboard into the SAME engine ZIP for PC/PHONE.

Run after tools/patch_engine_runtime.py in both workflows. Existing collector,
picker, download, database schema, and analysis classifier files remain untouched.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"
ASSETS = ROOT / "tools/overview_assets"
EXPECTED_OPTIMIZED_SHA256 = "80dbabee2320d7084c2b95856df31be531d92a22ef168b698a67b363095a37b9"

SOURCES = {
    "clean_core/database_overview.py": ASSETS / "database_overview.py",
    "static/full-database.js": ASSETS / "full-database.js",
    "static/full-database.css": ASSETS / "full-database.css",
}

def insert_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError("Nieznana wersja panelu — brak unikatowego znacznika: " + before[:75])
    return text.replace(before, after, 1)


def update_html(html: str) -> str:
    html = insert_once(
        html,
        '<link href="/static/style.css?v={{ app_version }}" rel="stylesheet"/>',
        '<link href="/static/style.css?v={{ app_version }}" rel="stylesheet"/>\n'
        '<link href="/static/full-database.css?v={{ app_version }}" rel="stylesheet"/>',
    )
    html = insert_once(
        html,
        '</nav>\n<div class="active-result-status no-result"',
        '</nav>\n<button type="button" id="openFullOverviewBtn" class="sora-overview-nav-btn"'
        ' aria-controls="soraFullOverview">Cała baza — wyniki i porównania</button>\n'
        '<div class="active-result-status no-result"',
    )
    html = insert_once(
        html, '<main class="split-layout" id="splitLayout">',
        '<section id="soraFullOverview" class="sora-full-overview" hidden aria-label="Całościowe wyniki i porównania bazy">'
        '<div class="sora-overview-header"><h2>Cała baza — raport i porównania</h2>'
        '<p>Wszystkie zapisane analizy artykułów. Zestawienia redakcji, relacji, aktorów,'
        ' tematów i warstw P0–P5. Nie otwiera pojedynczego wyniku ani nie przelicza dokumentów.</p>'
        '<div class="sora-overview-actions">'
        '<button type="button" id="soraFullOverviewRefresh">Odśwież całą bazę</button>'
        '<button type="button" id="soraFullOverviewBack">Wróć do aplikacji</button>'
        '</div></div><p class="sora-overview-status" id="soraFullOverviewStatus" role="status"'
        ' aria-live="polite">Wybierz „Odśwież całą bazę”, aby odczytać aktualny stan.</p>'
        '<div id="soraFullOverviewContent" aria-live="off"></div></section>\n'
        '<main class="split-layout" id="splitLayout">',
    )
    html = insert_once(
        html, '<script src="/static/app.js?v={{ app_version }}"></script>',
        '<script src="/static/app.js?v={{ app_version }}"></script>\n'
        '<script src="/static/full-database.js?v={{ app_version }}"></script>',
    )
    return html


def update_backend(app: str) -> str:
    app = insert_once(
        app,
        'from clean_core.database_aggregate import build_database_aggregate',
        'from clean_core.database_aggregate import build_database_aggregate\n'
        'from clean_core.database_overview import build_full_database_overview',
    )
    app = insert_once(
        app,
        '@app.get("/api/baza/porownanie/grupy")',
        '@app.get("/api/baza/raport_calosciowy")\n'
        'def api_database_full_overview():\n'
        '    """Wszystkie gotowe artykuły, wszystkie redakcje; nie zmienia bazy."""\n'
        '    try:\n'
        '        report = build_full_database_overview(\n'
        '            DOCUMENT_DATABASE.iter_completed_results(include_text=True, article_only=True),\n'
        '            database_stats=DOCUMENT_DATABASE.stats(),\n'
        '        )\n'
        '        return jsonify(report)\n'
        '    except Exception as exc:\n'
        '        return jsonify({"ok": False, "blad": "nie_udalo_sie_zbudowac_raportu",\n'
        '                        "szczegoly": f"{type(exc).__name__}: {exc}"}), 500\n\n\n'
        '@app.get("/api/baza/porownanie/grupy")',
    )
    return app


def apply_patch(asset: Path = ASSET) -> str:
    asset = Path(asset)
    before_sha = hashlib.sha256(asset.read_bytes()).hexdigest()
    with ZipFile(asset) as original:
        if original.testzip() is not None:
            raise ValueError("Uszkodzony ZIP silnika.")
        entries = [(info, original.read(info)) for info in original.infolist()]
    original_names = {info.filename for info, _ in entries}
    if all(name in original_names for name in SOURCES):
        if "soraFullOverview" in dict((i.filename, b) for i,b in entries)["templates/index.html"].decode():
            return before_sha
        raise ValueError("Niepełne wdrożenie panelu — wymagany przegląd.")
    if before_sha != EXPECTED_OPTIMIZED_SHA256:
        raise ValueError("Nieoczekiwana wersja silnika (SHA-256). Nie zmieniam aplikacji.")
    if any(name in original_names for name in SOURCES):
        raise ValueError("Częściowo wdrożony raport; zatrzymuję budowę.")
    updates = {
        "app.py": update_backend(next(data for info, data in entries if info.filename == "app.py").decode("utf-8")).encode("utf-8"),
        "templates/index.html": update_html(next(data for info, data in entries if info.filename == "templates/index.html").decode("utf-8")).encode("utf-8"),
    }
    fd, temp_name = tempfile.mkstemp(dir=asset.parent, suffix=".zip", prefix="sora-overview-")
    os.close(fd)
    try:
        with ZipFile(temp_name,"w") as patched:
            for info,data in entries:
                patched.writestr(info,updates.get(info.filename,data))
            for name,path in SOURCES.items():
                patched.writestr(name,path.read_bytes(),compress_type=ZIP_DEFLATED)
        with ZipFile(temp_name) as verify:
            if verify.testzip() is not None:
                raise ValueError("Kontrola CRC raportu nie powiodła się.")
            if set(verify.namelist()) != original_names | set(SOURCES):
                raise ValueError("Nieprawidłowa lista plików w silniku.")
            for info,data in entries:
                if info.filename not in updates and verify.read(info.filename) != data:
                    raise ValueError("Naruszono niepowiązany plik: " + info.filename)
        os.replace(temp_name,asset)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)
    return hashlib.sha256(asset.read_bytes()).hexdigest()


if __name__ == "__main__":
    print("Full database overview: packaged engine SHA-256 " + apply_patch())
