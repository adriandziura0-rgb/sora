"""One-time import of the exact, tested 1.2.13 program into tracked sources."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
ROOT=Path(__file__).resolve().parents[1]
ZIP=ROOT/"app/src/main/assets/drogowskazy-runtime.zip"
DEST=ROOT/"runtime_source"
RUNTIME_SHA="bee4fd3c9f67131e8d49cbf2789bce46fdfcde25610aeeb4e3566529e44cffd8"
ENGINE_SHA="acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e"
def sha(data):return hashlib.sha256(data).hexdigest()
if DEST.exists():raise SystemExit("Migracja tylko raz: kanoniczne źródła już istnieją.")
assert sha(ZIP.read_bytes())==RUNTIME_SHA,"Odmienna wersja runtime — niczego nie kopiuję"
files=[]
with ZipFile(ZIP) as z:
    assert z.testzip() is None
    for info in z.infolist():
        name=info.filename
        path=Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or name.startswith("data/"):
            raise ValueError("Niebezpieczny plik: "+name)
        if not name.endswith((".py",".json",".md",".txt",".js",".css",".html")):
            raise ValueError("Nieznany format źródeł: "+name)
        data=z.read(name)
        data.decode("utf-8")
        target=DEST/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        entry={"path":name,"sha256":sha(data),"date_time":list(info.date_time),
               "extra_hex":info.extra.hex(),"comment_hex":info.comment.hex()}
        for attr in ("compress_type","create_system","create_version","extract_version",
                     "flag_bits","volume","internal_attr","external_attr"):
            entry[attr]=getattr(info,attr)
        files.append(entry)
assert len(files)==66
metadata={"schema":"sora-runtime-source-v1","runtime_sha256":RUNTIME_SHA,"engine_sha256":ENGINE_SHA,"files":files}
(DEST/"zip_manifest.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("PASS: migrated exactly 66 audited runtime files into canonical tracked sources")
