"""SORA: isolated read-only quote database and HTTP regression checks."""
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"


def result(statement, speaker="Jan Testowy"):
    return {"analysis_run_id":"cytaty-test", "sekcje":{"fact_opinia_cytat":[{
        "claim_type":"cytat_przypisany", "claim_type_pl":"Cytat przypisany",
        "phrase":statement, "fragment":statement, "speaker":speaker,
        "relation_id":"r-test", "requires_review":False
    }]}}


with tempfile.TemporaryDirectory(prefix="sora-quotes-") as tmp:
    with ZipFile(ASSET) as z:
        assert z.testzip() is None
        assert "clean_core/quote_database.py" in z.namelist()
        assert "static/shared-content.js" in z.namelist()
        z.extractall(tmp)
    os.environ["DROGOWSKAZY_DB_PATH"] = str(Path(tmp) / "quote_test.sqlite3")
    sys.path.insert(0, tmp)
    import app as sora
    from clean_core.quote_database import selected_quote_database

    text = "Ten cytat został powtórzony dosłownie w dwóch wybranych publikacjach."
    rows = [
        ({"id":1, "is_article":True, "relative_path":"TVN24/a.txt"}, result(text)),
        ({"id":2, "is_article":True, "relative_path":"PAP/b.txt"}, result(text)),
        ({"id":3, "is_article":True, "relative_path":"INNA/c.txt"}, result(text)),
        ({"id":4, "is_article":False, "relative_path":"PAP/technical.json"}, result(text))
    ]
    # Explicitly selected groups only, no leaked unselected documents.
    v = selected_quote_database(iter(rows), mode="folder", groups=["TVN24", "PAP"])
    assert v["ok"] and v["read_only"]
    assert v["quote_count"] == 2, v
    assert len(v["same_statement_across_groups"]) == 1, v
    assert {r["group"] for r in v["records"]} == {"TVN24", "PAP"}
    assert len(selected_quote_database(iter(rows), mode="folder",groups=["PAP"])["same_statement_across_groups"]) == 0
    for bad in ([], [f"Grupa-{n}" for n in range(11)]):
        try:
            selected_quote_database(iter(rows), mode="folder", groups=bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid selection accepted")

    # Real HTTP route should use saved results, not mutate/replace DB.
    with sora.app.test_client() as client:
        invalid = client.get("/api/baza/cytaty_wybranych")
        assert invalid.status_code == 400, invalid.get_data(as_text=True)
        for index, folder in enumerate(["TVN24", "PAP"]):
            body = ("TYTUŁ: test\nŹRÓDŁO: " + folder + "\nLEAD: Informacja\nTREŚĆ: " + text)
            v = sora.DOCUMENT_DATABASE.begin_import(
                text=body, filename=f"{index}.txt",
                relative_path=f"{folder}/{index}.txt",
                extension=".txt",encoding="utf-8",source_bytes=len(body.encode()),
                app_version="test"
            )
            doc = v["document"]
            sora.DOCUMENT_DATABASE.mark_success(
                doc["id"],result(text),
                expected_content_sha256=doc["content_sha256"]
            )
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            before=db.execute("SELECT id, status, content_sha256 FROM documents ORDER BY id").fetchall()
        response=client.get("/api/baza/cytaty_wybranych?mode=folder&group=TVN24&group=PAP")
        assert response.status_code==200,response.get_data(as_text=True)
        payload=response.get_json()
        assert payload["quote_count"]==2,payload
        assert len(payload["same_statement_across_groups"])==1,payload
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            after=db.execute("SELECT id, status, content_sha256 FROM documents ORDER BY id").fetchall()
        assert before==after
print("PASS: selected quote database, exact cross-group reuse, nonarticle excluded, HTTP read-only")
