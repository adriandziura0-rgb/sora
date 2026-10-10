"""Regression tests for the embedded Sora analysis engine ONLY.

File downloads, folder pickers, SQLite schema and HTTP handlers are untouched.
Verify that the optimized matcher preserves the exact deterministic results,
keeps publisher attribution, and avoids evaluating expensive cached fallbacks.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"
with tempfile.TemporaryDirectory(prefix="sora-topic-test-") as temporary:
    with ZipFile(ASSET) as archive:
        assert archive.testzip() is None
        archive.extractall(temporary)
    sys.path.insert(0, temporary)

    from clean_core import topic_matcher as matcher
    from clean_core.gold_benchmark import run_gold_benchmark

    cases = []
    publishers = ["TVN24", "Onet", "Interia", "PAP", "Polsat News", "RMF24", "Gazeta.pl"]
    for index in range(60):
        publisher = publishers[index % len(publishers)]
        text = (
            "TYTUŁ: Komisja Jana Kowalskiego bada doniesienia o sprawie Pegasusa\n"
            f"ŹRÓDŁO: {publisher}\n"
            f"URL: https://{index%7}.example.invalid/news/{index}\n"
            "LEAD: Jan Kowalski poinformował o nowych dowodach i analizie działania Pegasusa w Warszawie.\n"
            "DATA PUBLIKACJI: 2026-10-08\n"
            "TREŚĆ: Komisja Jana Kowalskiego przeprowadziła kolejne badanie w sprawie Pegasusa."
        )
        document = {
            "id": index + 1,
            "relative_path": f"{publisher}/{index}.txt",
            "filename": f"{index}.txt",
            "extension": ".txt",
            "content_sha256": f"{index:064x}",
            "_text_content": text,
        }
        cases.append((document, {}))

    original = matcher._pair_score
    counter = [0]
    def counted(left, right):
        counter[0] += 1
        return original(left, right)
    matcher._pair_score = counted
    started = perf_counter()
    response = matcher.discover_same_story_topics(cases)
    duration = perf_counter() - started
    calls = counter[0]
    matcher._pair_score = original

    assert calls <= 6500, f"Utracono cache par: {calls} obliczeń (maks. 6500)."
    assert len(response["topics"]) == 1, response["topics"]
    topic = response["topics"][0]
    assert topic["documents"] == 60
    assert topic["publisher_count"] == 7
    assert len(topic["items"]) == 60
    assert len({item["document_id"] for item in topic["items"]}) == 60

    # Snapshot recorded from the original analysis engine: no semantic drift.
    response.pop("generated_at", None)
    canonical = json.dumps(response, sort_keys=True, ensure_ascii=False, default=str)
    checksum = hashlib.sha256(canonical.encode()).hexdigest()
    assert checksum == "ffe4ab19254e0d6421f5a091136a8178f092b0c60a2db8eab290dd0e9cb506a4", checksum

    gold = run_gold_benchmark()
    assert gold["case_count"] == 257
    assert gold["all_pass"] and gold["failed_case_count"] == 0, gold["failed_case_ids"]
    print(f"PASS: engine; 60 documents, 7 publishers, {calls} pair evaluations in {duration:.3f}s; 257/257 GOLD; unchanged output")
