"""SORA CLEAN etap 2: fail CI if retired desktop entrypoints return.

Pure read-only source inspection. No DB access and no build side effects.
Does not forbid Qt/Tk exclusions within the active PyInstaller build script.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
RETIRED = (
    "sora_pc.py",           # old Tkinter desktop application
    "operations.py",        # its Tk widget operations
    "gui_test.py",          # test of Tk window
    "build_windows.py",     # old PyInstaller pywebview/Qt release path
    "sora_pc_webview.py",   # former pywebview host
    "test_qt_unfrozen.py",  # standalone Qt diagnostic
    "test_phone_ui.py",     # test of the retired host
    "presentation.py",      # moved unchanged to test-only report_projection.py
)
ACTIVE = (
    "build_native_windows.py", "engine.py", "sora_backend.py",
    "local_session.py", "windows_adapter.js", "report_projection.py",
    "native/Program.cs", "native/Sora.Native.csproj",
    "test_engine.py", "test_local_session.py", "test_windows_adapter.mjs",
)
for name in RETIRED:
    assert not (DESKTOP / name).exists(), f"Nieusunięty historyczny moduł Windows: {name}"
for name in ACTIVE:
    assert (DESKTOP / name).is_file(), f"Brak aktywnego pliku Windows: {name}"

retired_modules = {Path(n).stem for n in RETIRED}
for path in DESKTOP.rglob("*.py"):
    source = path.read_text(encoding="utf-8")
    syntax = ast.parse(source, filename=str(path))
    imports = []
    for node in ast.walk(syntax):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    old = retired_modules.intersection(imports)
    assert not old, f"Martwy import w {path.relative_to(ROOT)}: {sorted(old)}"

windows = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
android = (ROOT / ".github/workflows/build-apk.yml").read_text(encoding="utf-8")
assert "python desktop/build_native_windows.py" in windows
assert "python desktop/test_engine.py" in windows
assert "python desktop/test_local_session.py" in windows
assert "python tools/test_native_clean.py" in windows
assert "python tools/test_native_clean.py" in android
assert "python desktop/build_windows.py" not in windows
assert "app/src/main/assets/drogowskazy-runtime.zip" in windows

print("PASS: CLEAN etap 2; bez martwych plików/importów Tk/Qt; aktywny natywny WebView2, test raportów i prywatnej sesji")
