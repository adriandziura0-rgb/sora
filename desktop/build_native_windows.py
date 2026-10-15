"""Zbuduj dwa pliki natywne: WebView2 Sora.exe + silnik PHONE SoraSilnik.exe."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
asset = root / "app/src/main/assets/drogowskazy-runtime.zip"
runtime = root / "build/phone-runtime"
runtime.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(asset) as archive:
    if archive.testzip() is not None:
        raise RuntimeError("Uszkodzona paczka silnika PHONE.")
    archive.extractall(runtime)
sys.path.insert(0, str(root / "desktop"))
from engine import runtime_identity
identity = runtime_identity(asset)

subprocess.run([
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--console", "--name", "SoraSilnik",
    "--exclude-module", "tkinter", "--exclude-module", "_tkinter",
    "--exclude-module", "webview", "--exclude-module", "pythonnet",
    "--exclude-module", "clr", "--exclude-module", "clr_loader",
    "--exclude-module", "PyQt6", "--exclude-module", "PySide6",
    "--paths", str(root / "app/src/main/python"),
    "--paths", str(root / "desktop"),
    "--paths", str(runtime),
    "--collect-submodules", "clean_core",
    "--collect-all", "flask",
    "--collect-all", "reportlab",
    "--collect-all", "PIL",
    "--add-data", str(asset) + ";.",
    str(root / "desktop/sora_backend.py")
], cwd=root, check=True)

publish = root / "dist/Sora"
publish.mkdir(parents=True, exist_ok=True)
subprocess.run([
    "dotnet", "publish", str(root / "desktop/native/Sora.Native.csproj"),
    "-c", "Release", "-r", "win-x64", "--self-contained", "true",
    "-p:PublishSingleFile=true",
    "-p:IncludeNativeLibrariesForSelfExtract=true",
    "-o", str(publish)
], cwd=root, check=True)
backend = publish / "_engine/SoraSilnik"
if backend.exists():
    shutil.rmtree(backend)
shutil.copytree(root / "dist/SoraSilnik", backend)

# Debug/symbol/XML documentation is preserved in a SEPARATE diagnostics
# artifact, never shipped with the installer. Do not remove runtime DLL/JSON.
diagnostics = root / "dist/SoraDiagnostics"
diagnostics.mkdir(parents=True, exist_ok=True)
moved_diagnostics = []
for candidate in list(publish.rglob("*")):
    if not candidate.is_file():
        continue
    debug_pdb = candidate.suffix.lower() == ".pdb"
    webview_docs = candidate.name.startswith("Microsoft.Web.WebView2.") and candidate.suffix.lower() == ".xml"
    if debug_pdb or webview_docs:
        target = diagnostics / candidate.relative_to(publish)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(candidate), str(target))
        moved_diagnostics.append(candidate.relative_to(publish).as_posix())
(diagnostics / "PRZENIESIONE_PLIKI.json").write_text(
    json.dumps(moved_diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")

shutil.copyfile(root / "desktop/windows_adapter.js", publish / "windows_adapter.js")
shutil.copyfile(root / "desktop/README.md", publish / "INSTRUKCJA.txt")
(publish / "SILNIK_PHONE_PC.json").write_text(
    json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8")
(publish / "RAPORT_BUDOWANIA.json").write_text(json.dumps({
    "desktop_host": "C# WinForms Microsoft Edge WebView2",
    "engine": "unmodified Sora PHONE Flask, SQLite, classifier",
    "pythonnet": False, "qt": False, "tkinter": False,
    "engine_sha256": identity["engine_sha256"],
    "runtime_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
}, ensure_ascii=False, indent=2), encoding="utf-8")

if not (publish / "Sora.exe").is_file() or not (backend / "SoraSilnik.exe").is_file():
    raise RuntimeError("Niekompletna paczka: brak EXE lub silnika.")
for suspect in publish.rglob("*"):
    if suspect.is_file() and suspect.name.lower() in (
        "python.runtime.dll", "clrloader.dll", "_tkinter.pyd", "qtwebengineprocess.exe"):
        raise RuntimeError("W paczce pozostała niepotrzebna biblioteka: " + str(suspect))
assert not any(path.suffix.lower() == ".pdb" or
               (path.name.startswith("Microsoft.Web.WebView2.") and path.suffix.lower() == ".xml")
               for path in publish.rglob("*") if path.is_file()), "Diagnostyka w paczce instalacyjnej"
print("PASS: natywny Sora.exe CLEAN (C# WebView2), osobny PHONE backend, bez Qt/pythonnet/Tk ani debug PDB/XML.")
