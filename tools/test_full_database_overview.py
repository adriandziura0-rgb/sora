"""Read-only analytics for EXPLICIT selection; unselected documents never appear."""
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
        assert "static/import-recovery.js" in archive.namelist()
        assert b"import-recovery.js" in archive.read("templates/index.html")
        assert b"webkitdirectory" in archive.read("templates/index.html"), "Plikowy wybór folderu musi pozostać"
        archive.extractall(tmp)
    os.environ["DROGOWSKAZY_DB_PATH"] = str(Path(tmp) / "isolated-test.sqlite3")
    sys.path.insert(0, tmp)
    import app as sora
    from clean_core.database_overview import build_selected_database_overview

    with sora.app.test_client() as client:
        blank = client.get("/api/baza/analiza_wybranych")
        assert blank.status_code == 400, "Brak zaznaczenia nie może uruchomić całej bazy"
        assert client.get("/api/baza/raport_calosciowy").status_code == 404
        empty = client.get("/api/baza/analiza_wybranych?mode=folder&group=Brak")
        assert empty.status_code == 200 and empty.get_json()["analyzed_articles"] == 0
        assert client.get("/api/baza/analiza_wybranych?mode=all&group=TVN24").status_code == 400
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
        response = client.get("/api/baza/analiza_wybranych?mode=publisher&group=TVN24&group=PAP")
        assert response.status_code == 200, response.get_data(as_text=True)
        selected = response.get_json()
        assert selected["ok"] and selected["read_only"]
        assert selected["selected_groups"] == ["TVN24","PAP"]
        assert selected["analyzed_articles"] == 2, selected
        assert selected["publisher_count"] == 2, selected["sources"]
        assert selected["summary"]["relations"] == 2
        assert selected["summary"]["documents_with_relation"] == 2
        assert selected["stats"]["done_articles"] == 2
        assert "processing" not in selected["stats"], "Nie podajemy zmyślonej liczby oczekujących"
        assert "error" not in selected["stats"], "Nie podajemy zmyślonej liczby błędów"
        assert selected["source_audit"]["confirmed"] == 2
        assert selected["source_audit"]["indirect"] == 0
        assert selected["source_audit"]["unknown"] == 0
        assert all(item["publisher_evidence"] == "potwierdzone"
                   for item in selected["recent_documents"])
        # Kolejny odczyt ma pochodzić z cache'u, bez ponownego iterowania
        # i dekompresji wszystkich zapisanych analiz.
        from unittest.mock import patch
        with patch.object(sora.DOCUMENT_DATABASE, "iter_completed_results",
                          side_effect=AssertionError("Nie wolno ponownie skanować bazy")):
            cached = client.get("/api/baza/analiza_wybranych?mode=publisher&group=TVN24&group=PAP")
            assert cached.status_code == 200
            assert cached.get_json()["analyzed_articles"] == 2
        assert client.get("/api/baza/analiza_wybranych?mode=publisher&group=TVN24&group=tvn24").get_json()["selected_groups"] == ["TVN24"]
        assert all(d["publisher"] in {"TVN24","PAP"} for d in selected["recent_documents"])
        assert selected["rankings"]["speakers"][0] == {"name":"minister","count":2}
        assert selected["rankings"]["topics"][0] == {"name":"badanie","count":2}
        assert selected["rankings"]["p0"][0] == {"name":"Sygnał","count":2}
        assert client.get("/api/baza/analiza_wybranych?mode=publisher&group=TVN24").get_json()["analyzed_articles"] == 1
        assert client.get("/api/baza/analiza_wybranych?mode=folder&group=PAP").get_json()["analyzed_articles"] == 1
        too_many = "&".join("group=" + x.replace(" ","%20") for x in sources[:11])
        assert client.get("/api/baza/analiza_wybranych?mode=folder&" + too_many).status_code == 400
        assert sora.DOCUMENT_DATABASE.stats() == before
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            state_after = db.execute(
                "SELECT id, content_sha256, status, analysis_run_id FROM documents ORDER BY id"
            ).fetchall()
        assert state_before == state_after, "Raport nie może modyfikować danych"
        # 15 dodatkowych dokumentów tej samej wybranej grupy: najnowsze 12
        # bez gromadzenia historii dokumentów w pamięci.
        for index in range(15):
            source_text = f"TYTUŁ: uzupełnienie {index}\nŹRÓDŁO: TVN24\nTREŚĆ: seria {index}"
            entry = sora.DOCUMENT_DATABASE.begin_import(
                text=source_text, filename=f"extra-{index}.txt",
                relative_path=f"TVN24/extra-{index}.txt", extension=".txt",
                encoding="utf-8", source_bytes=len(source_text.encode("utf-8")),
                app_version="test",
            )
            doc = entry["document"]
            sora.DOCUMENT_DATABASE.mark_success(
                doc["id"], {"analysis_run_id": f"extra-{index}", "sekcje": {}},
                expected_content_sha256=doc["content_sha256"],
            )
        extra = client.get("/api/baza/analiza_wybranych?mode=publisher&group=TVN24")
        assert extra.status_code == 200
        most_recent = extra.get_json()["recent_documents"]
        assert len(most_recent) == 12 and len({item["id"] for item in most_recent}) == 12
        assert all(item["publisher"] == "TVN24" for item in most_recent)
        # Nowy zapis unieważnia cache nawet wtedy, gdy użytkownik
        # wybrał te same grupy. Raport nie może ukrywać nowych artykułów.
        assert extra.get_json()["analyzed_articles"] == 16
        assert extra.get_json()["source_audit"]["indirect"] == 15
        # Folder o nazwie sugerującej redakcję NIE potwierdza źródła
        # publikacji i NIE może stać się automatycznie 'tvp.info'.
        raw = "TYTUŁ: Artykuł bez źródła\nTREŚĆ: Przykładowa treść bez daty i URL"
        row = sora.DOCUMENT_DATABASE.begin_import(
            text=raw, filename="bez-zrodla.txt",
            relative_path="pogaduszki tvp/bez-zrodla.txt", extension=".txt",
            encoding="utf-8", source_bytes=len(raw.encode("utf-8")),
            app_version="test",
        )["document"]
        sora.DOCUMENT_DATABASE.mark_success(
            row["id"], {"analysis_run_id": "missing-source", "sekcje": {}},
            expected_content_sha256=row["content_sha256"],
        )
        doubtful = client.get("/api/baza/analiza_wybranych?mode=folder&group=pogaduszki%20tvp")
        assert doubtful.status_code == 200
        assert doubtful.get_json()["source_audit"]["unknown"] == 1
        assert doubtful.get_json()["source_audit"]["confirmed"] == 0
        html = client.get("/").get_data(as_text=True)
        assert "Pokaż analizę zaznaczonych" in html
        assert "Cała baza — wyniki i porównania" not in html
        assert "sora-selection-layout" in html
        assert 'id="soraFullOverview"' in html
        assert client.get("/static/full-database.js").status_code == 200
        assert client.get("/static/full-database.css").status_code == 200
        assert client.get("/api/baza/status").status_code == 200
        assert client.get("/api/baza/porownanie/grupy").status_code == 200
        print("PASS: 12 documents in database; only two selected analyzed, one selected supported,"
              " empty selection rejected, no writes, Android UI and original imports intact")
