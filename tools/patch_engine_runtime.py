"""Prepare the optimized *analysis engine* for APK and Windows builds.

This script touches only clean_core/topic_matcher.py INSIDE the embedded runtime ZIP.
It never modifies the file picker, article downloader, user SQLite databases or UI.
The expected original ZIP hash makes unexpected upstream changes fail safely.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"
EXPECTED_ORIGINAL_SHA256 = "68cd3dff8f8e65a53759b8fc42522619129cac04a596c2234c95099b82ccfc05"
MODULE = "clean_core/topic_matcher.py"

# dict.get(key, default_expression) EVALUATES the fallback before looking up
# the cached value; in large cross-publisher clusters this re-ran costly
# similarity scoring thousands of times, even for cached pairs.
BEFORE_LOOKUP = "return pair_scores.get(key, _pair_score(docs[i], docs[j]))"
AFTER_LOOKUP = "cached = pair_scores.get(key)\n        return cached if cached is not None else _pair_score(docs[i], docs[j])"
BEFORE_CROSS = "cross.append(pair_scores.get((min(i,j), max(i,j)), _pair_score(docs[i], docs[j])))"
AFTER_CROSS = "cross.append(score_for(i, j))"


def optimize(asset: Path = ASSET) -> str:
    asset = Path(asset)
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    with ZipFile(asset) as source:
        if source.testzip() is not None:
            raise ValueError("Silnik ZIP ma uszkodzone CRC.")
        entries = [(info, source.read(info)) for info in source.infolist()]

    modules = [(info, data) for info, data in entries if info.filename == MODULE]
    if len(modules) != 1:
        raise ValueError("Nie znaleziono dokładnie jednego modułu dopasowania tematów.")
    original = modules[0][1].decode("utf-8")
    if BEFORE_LOOKUP not in original and BEFORE_CROSS not in original:
        if AFTER_LOOKUP in original and AFTER_CROSS in original:
            return digest  # CI preparation is safe to repeat.
        raise ValueError("Nieznana implementacja matchera — nie wykonuję zmian.")

    if digest != EXPECTED_ORIGINAL_SHA256:
        raise ValueError("Nieznany SHA-256 silnika. Wymagany przegląd ręczny przed modyfikacją.")
    if original.count(BEFORE_LOOKUP) != 1 or original.count(BEFORE_CROSS) != 1:
        raise ValueError("Niezgodny kod matchera — poprawka nie zostanie zastosowana.")

    modified = original.replace(BEFORE_LOOKUP, AFTER_LOOKUP).replace(BEFORE_CROSS, AFTER_CROSS).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix="sora-engine-", suffix=".zip", dir=asset.parent)
    os.close(fd)
    try:
        with ZipFile(temp_name, "w") as dest:
            for info, data in entries:
                dest.writestr(info, modified if info.filename == MODULE else data)
        with ZipFile(temp_name) as result:
            if result.testzip() is not None:
                raise ValueError("Nowy silnik nie przeszedł kontroli CRC.")
            if set(result.namelist()) != {info.filename for info, _ in entries}:
                raise ValueError("Niezgodna zawartość paczki silnika.")
            for info, data in entries:
                if info.filename != MODULE and result.read(info.filename) != data:
                    raise ValueError("Zmiana pliku poza silnikiem: " + info.filename)
        os.replace(temp_name, asset)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return hashlib.sha256(asset.read_bytes()).hexdigest()


if __name__ == "__main__":
    print("Silnik Sora zoptymalizowany; SHA-256:", optimize())
