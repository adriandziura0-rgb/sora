"""Strict regression for CLEAN source packaging with no runtime patches."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from build_runtime_from_sources import (
    build, read_manifest, RUNTIME_SHA, ENGINE_SHA, SOURCE, TARGET
)
ROOT=Path(__file__).resolve().parents[1]
rows=read_manifest()
assert len(rows)==66
with TemporaryDirectory(prefix="sora-clean-proof-") as work:
    candidate=Path(work)/"candidate.zip"
    assert build(candidate)==RUNTIME_SHA
    assert hashlib.sha256(candidate.read_bytes()).hexdigest()==RUNTIME_SHA
    assert candidate.read_bytes()==TARGET.read_bytes(),"APK/PC runtime must equal canonical ZIP"
    with ZipFile(candidate) as z:
        assert z.testzip() is None
        assert len(z.namelist())==66
        assert not any(n.startswith("data/") for n in z.namelist())
        for row in rows:
            assert hashlib.sha256(z.read(row["path"])).hexdigest()==row["sha256"]
        # Explicitly retain all selected-group and same-story UI modules.
        for filename in ("app.py","clean_core/topic_matcher.py",
                         "static/app.js","templates/index.html",
                         "static/full-database.js","static/shared-content.js",
                         "static/same-story-mobile.js","clean_core/quote_database.py"):
            assert filename in z.namelist(),filename
# The transfer/GOLD test workflows independently validate the locked engine hash.
assert ENGINE_SHA=="acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e"
print("PASS: 66 canonical sources, byte-identical APK/PC runtime, all reports, no user DB")
