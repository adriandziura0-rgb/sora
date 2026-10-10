"""Read-only whole-database analysis: all sources, figures, and mobile UI assets."""
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"
with tempfile.TemporaryDirectory(prefix="sora-full-db-", ignore_cleanup_errors=True) as tmp:
    with zipfile.ZipFile(ASSET) as archive:
        assert archive.testzip() is None
        assert "clean_core/database_overview.py" in archive.namelist()
        assert "static/full-database.js" in archive.namelist()
        assert "static/full-database.css" in archive.namelist()
        assert b"webkitdirectory" in archive.read("templates/index.html"), "Plikowy wybór folderu musi pozostać"
        archive.extractall(tmp)
    os.environ["DROGOWSKAZY_DB_PATH"] = str(Path(tmp) / "isolated-test.sqlite3")
    sys.path.insert(0, tmp)
    import app as sora
    from clean_core.database_overview import build_full_database_overview

    with sora.app.test_client() as client:
        blank = client.get("/api/baza/raport_calosciowy")
        assert blank.status_code == 200, blank.get_data(as_text=True)
        empty = blank.get_json()
        assert empty["ok"] is True and empty["analyzed_articles"] == 0
        assert empty["publisher_count"] == 0

        sources = ("TVN24","PAP","Onet","Interia","RMF24","Polsat News",
                   "TVP Info","Gazeta Wyborcza","Do Rzeczy","Dziennik.pl",
                   "Gazeta.pl","Money.pl")
        for index, source in enumerate(sources):
            source_text = (
                f"TYTUŁ: Raport badawczy {index}\nŹRÓDŁO: {source}\n"
                f"URL: https://example.org/news/{index}\n"
                f"LEAD: Komisja przeanalizowała sprawę numer {index}.\n"
                f"TREŚĆ: Minister powiedział, że projekt numer {index} wymaga analizy."
            )
            entry = sora.DOCUMENT_DATABASE.begin_import(
                text=source_text, filename=f"article{index}.txt",
                relative_path=f"{source}/article{index}.txt",
                extension=".txt", encoding="utf-8",
                source_bytes=len(source_text.encode("utf-8")), app_version="test",
            )
            doc = entry["document"]
            result = {
                "analysis_run_id":f"case-{index}",
                "dlugosc_tekstu":len(source_text),
                "sekcje":{
                    "relacje_wypowiedzi":[{
                        "relation_id":f"r-{index}",
                        "kto_mowi":"minister",
                        "o_kim":"projekt", "temat":"badanie",
                        "wymaga_przegladu": bool(index % 2),
                    }],
                    "potwierdzone_p1":[{"tytul":"Weryfikacja"}] if index%2==0 else [],
                },
                "p0":{"liczba_markerow":1,"wedlug_etykiet":{"Sygnał":1}},
            }
            sora.DOCUMENT_DATABASE.mark_success(
                doc["id"],result,expected_content_sha256=doc["content_sha256"]
            )

        before = sora.DOCUMENT_DATABASE.stats()
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            state_before = db.execute(
                "SELECT id, content_sha256, status, analysis_run_id FROM documents ORDER BY id"
            ).fetchall()
        response = client.get("/api/baza/raport_calosciowy")
        assert response.status_code == 200, response.get_data(as_text=True)
        full = response.get_json()
        assert full["ok"] is True and full["read_only"] is True
        assert full["analyzed_articles"] == len(sources), full
        assert full["publisher_count"] == len(sources), full["sources"]
        assert len(full["sources"]) == len(sources), "Nie ograniczaj raportu do 10 redakcji"
        assert full["summary"]["relations"] == len(sources)
        assert full["summary"]["documents_with_relation"] == len(sources)
        assert full["stats"]["done_articles"] == len(sources)
        assert sum(item["documents"] for item in full["sources"]) == len(sources)
        assert full["rankings"]["speakers"][0] == {"name":"minister","count":len(sources)}
        assert full["rankings"]["topics"][0] == {"name":"badanie","count":len(sources)}
        assert full["rankings"]["p0"][0] == {"name":"Sygnał","count":len(sources)}
        assert len(full["recent_documents"]) == len(sources)
        assert sora.DOCUMENT_DATABASE.stats() == before
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            state_after = db.execute(
                "SELECT id, content_sha256, status, analysis_run_id FROM documents ORDER BY id"
            ).fetchall()
        assert state_before == state_after, "Raport nie może modyfikować danych"
        html = client.get("/").get_data(as_text=True)
        assert "Cała baza — wyniki i porównania" in html
        assert 'id="soraFullOverview"' in html
        assert client.get("/static/full-database.js").status_code == 200
        assert client.get("/static/full-database.css").status_code == 200
        assert client.get("/api/baza/status").status_code == 200
        assert client.get("/api/baza/porownanie/grupy").status_code == 200
        print("PASS: 12 publishers, whole SQLite data, 12 relations, topic/actor/P0 rankings,"
              " no writes, UI assets and existing APIs")
