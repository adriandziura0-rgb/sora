"""Stage 4 CLEAN: final release guard for shared export and frozen engine.

Pure assertions over tracked sources and generated runtime; no DB writes.
"""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from build_runtime_from_sources import SOURCE, TARGET, RUNTIME_SHA, ENGINE_SHA

def sha(data):return hashlib.sha256(data).hexdigest()

with ZipFile(TARGET) as z:
    assert z.testzip() is None
    assert sha(TARGET.read_bytes()) == RUNTIME_SHA, "Runtime differs from approved manifest"
    assert len(z.namelist()) == 66
    assert "clean_core/classifier.py" in z.namelist()
    assert "static/app.js" in z.namelist()
    assert "static/full-database.js" in z.namelist()
    assert z.read("static/full-database.js") == (SOURCE/"static/full-database.js").read_bytes()
    core = z.read("static/app.js").decode("utf-8")
    overview = z.read("static/full-database.js").decode("utf-8")
    quoted = z.read("static/shared-content.js").decode("utf-8")
    story = z.read("static/same-story-mobile.js").decode("utf-8")
    assert "function pobierzPlik(" in core, "No shared export in Android/PC core UI"
    assert "window.pobierzPlik(name, contents, mime)" in overview
    assert "window.pobierzPlik(" in quoted
    assert "pobierzPlik(name,text,mime)" in story
    assert "URL.createObjectURL" not in overview, "Duplicate browser export returned"
    assert "soraStoryDownloadHtml" in story and "soraStoryDownloadJson" in story
    assert "soraDownloadSelectedReport" in overview and "soraDownloadSelectedData" in overview

version=(ROOT/"app/build.gradle").read_text(encoding="utf-8")
assert "versionCode 18" in version and "versionName '1.2.15'" in version
assert (ROOT/"VERSION.txt").read_text(encoding="utf-8").startswith("1.2.15")
desktop=(ROOT/"desktop/build_native_windows.py").read_text(encoding="utf-8")
windows=(ROOT/".github/workflows/build-windows.yml").read_text(encoding="utf-8")
assert "SoraDiagnostics" in desktop and "SoraDiagnostics" in windows
assert "Sora-WINDOWS-DIAGNOSTYKA" in windows
assert 'shutil.move(str(candidate), str(target))' in desktop
assert ENGINE_SHA == "acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e"
print("PASS: CLEAN 1.2.15; shared export HTML/JSON, frozen engine, 66 assets, Windows diagnostics split")
