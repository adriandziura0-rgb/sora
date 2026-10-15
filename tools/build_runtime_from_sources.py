"""Build the exact audited runtime ZIP from tracked CLEAN canonical sources.

No string patches, classifier changes or SQL writes. The audited 1.2.15 runtime
is reproducible byte-for-byte; ANY code drift fails closed before packaging.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import ZipFile, ZipInfo

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"runtime_source"
MANIFEST=SOURCE/"zip_manifest.json"
TARGET=ROOT/"app/src/main/assets/drogowskazy-runtime.zip"
RUNTIME_SHA="aa8b08ce766359f439afcc4e5db3d9b45d9f50a29b48f685a4b0d475532b5638"
ENGINE_SHA="acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e"

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def read_manifest():
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema")!="sora-runtime-source-v1":
        raise ValueError("Niezgodny format manifestu CLEAN.")
    if manifest.get("runtime_sha256")!=RUNTIME_SHA or manifest.get("engine_sha256")!=ENGINE_SHA:
        raise ValueError("Niezgodna tożsamość zamrożonego programu.")
    rows=manifest["files"]
    paths=[row["path"] for row in rows]
    if len(paths)!=66 or len(set(paths))!=66:
        raise ValueError("Niepoprawny zestaw kanonicznych plików.")
    found={p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*")
           if p.is_file() and p!=MANIFEST}
    if found!=set(paths):
        raise ValueError("Brakujący/dodatkowy kod w runtime_source: "+
                         repr(sorted(found.symmetric_difference(paths))))
    return rows

def build(output:Path=TARGET)->str:
    output=Path(output)
    records=read_manifest()
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix="sora-clean-",suffix=".zip",dir=output.parent)
    os.close(fd)
    try:
        with ZipFile(temp,"w") as dest:
            for row in records:
                name=row["path"]
                path=PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name or name.startswith("data/"):
                    raise ValueError("Niebezpieczna ścieżka: "+name)
                raw=(SOURCE/name).read_bytes()
                if sha(raw)!=row["sha256"]:
                    raise ValueError("Niezatwierdzona zmiana źródeł: "+name)
                zi=ZipInfo(name,tuple(row["date_time"]))
                for attr in ("compress_type","create_system","create_version","extract_version",
                             "flag_bits","volume","internal_attr","external_attr"):
                    setattr(zi,attr,row[attr])
                zi.extra=bytes.fromhex(row["extra_hex"])
                zi.comment=bytes.fromhex(row["comment_hex"])
                dest.writestr(zi,raw)
        with ZipFile(temp) as z:
            assert z.testzip() is None
            if z.namelist()!=[row["path"] for row in records]:
                raise ValueError("Nieprawidłowa kolejność lub zawartość ZIP.")
        digest=sha(Path(temp).read_bytes())
        if digest!=RUNTIME_SHA:
            raise ValueError("ZIP nie jest identyczny z TESTOWANĄ wersją: "+digest)
        os.replace(temp,output)
        return digest
    finally:
        if os.path.exists(temp):os.unlink(temp)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=TARGET)
    args=parser.parse_args()
    print("PASS: CLEAN runtime, bit-identical SHA-256:",build(args.output))
