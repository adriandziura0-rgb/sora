"""E2E niezależnego wyszukiwania wspólnej treści — bez zapisu do SQLite."""
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "app/src/main/assets/drogowskazy-runtime.zip"

COMMON = ("Komisja przedstawiła dziś nowe wyniki przesłuchań i szczegółowy raport "
          "dotyczący użycia systemu inwigilacyjnego podczas poprzedniej kadencji "
          "oraz zapowiedziała publikację pełnej dokumentacji w najbliższych tygodniach.")
DIFF_A = ("Dodatkowo pierwszy artykuł szczegółowo opisuje stanowisko prawników "
          "uczestniczących w posiedzeniu komisji oraz dokładny harmonogram "
          "udostępniania materiałów wszystkim zainteresowanym organizacjom.")
DIFF_B = ("Drugi artykuł natomiast przedstawia reakcje przedstawicieli opozycji "
          "i omawia następstwa finansowe raportu dla administracji samorządowej "
          "oraz niezależnych instytucji publicznych.")


def article(title, group, common, different):
    return (f"TYTUŁ: {title}\nŹRÓDŁO: {group}\n"
            f"URL: https://przyklad.invalid/{group}/{title.replace(' ', '-')}\n"
            f"LEAD: Porównanie materiałów prasowych i przedstawionych informacji.\n"
            f"TREŚĆ: {common}\n\n{different}")


with tempfile.TemporaryDirectory(prefix="sora-shared-test-", ignore_cleanup_errors=True) as temporary:
    with ZipFile(ASSET) as archive:
        assert archive.testzip() is None
        assert "clean_core/shared_content.py" in archive.namelist()
        assert "static/shared-content.js" in archive.namelist()
        assert "static/shared-content.css" in archive.namelist()
        html = archive.read("templates/index.html")
        assert b"findSharedContentBtn" in html
        assert b"sharedContentPanel" in html
        archive.extractall(temporary)
    os.environ["DROGOWSKAZY_DB_PATH"] = str(Path(temporary) / "isolated.sqlite3")
    sys.path.insert(0, temporary)
    import app as sora
    from clean_core.shared_content import compare_shared_content

    with sora.app.test_client() as client:
        missing = client.get("/api/baza/wspolna_tresc?mode=folder&group=TVN24")
        assert missing.status_code == 400
        assert client.get("/api/baza/wspolna_tresc?mode=all&group=TVN24&group=PAP").status_code == 400
        data = [
            ("Raport komisji o działaniu systemu Pegasus", "TVN24", COMMON, DIFF_A),
            ("Raport komisji o działaniu systemu Pegasus", "PAP", COMMON, DIFF_B),
            ("Inny artykuł poświęcony regionalnym inwestycjom", "Onet",
             "W dniu dzisiejszym odbyło się spotkanie na temat rozwoju infrastruktury "
             "transportowej w kilku regionach kraju oraz zmian w budżetach lokalnych. "
             "Dyskutowano o budowie nowych połączeń kolejowych i przywracaniu komunikacji.",
             "Samorządy przedstawiły propozycje inwestycji i długofalowe plany "
             "rozwoju lokalnego transportu w najbliższych latach."),
        ]
        for index, (title, group, common, different) in enumerate(data):
            text = article(title, group, common, different)
            entry = sora.DOCUMENT_DATABASE.begin_import(
                text=text, filename=f"artykul-{index}.txt",
                relative_path=f"{group}/artykul-{index}.txt",
                extension=".txt", encoding="utf-8",
                source_bytes=len(text.encode("utf-8")), app_version="test")
            doc = entry["document"]
            sora.DOCUMENT_DATABASE.mark_success(
                doc["id"], {"analysis_run_id": f"shared-{index}", "sekcje": {}},
                expected_content_sha256=doc["content_sha256"])

        status = sora.DOCUMENT_DATABASE.stats()
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            before = db.execute(
                "SELECT id, content_sha256, status, analysis_run_id FROM documents ORDER BY id"
            ).fetchall()
        path = "/api/baza/wspolna_tresc?mode=folder&group=TVN24&group=PAP"
        response = client.get(path)
        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        assert payload["ok"] and payload["read_only"]
        assert payload["selected_articles"] == 2
        assert payload["examined_articles"] == 2
        assert len(payload["matches"]) == 1, payload["matches"]
        pair = payload["matches"][0]
        assert pair["match_kind"] == "wspólny fragment"
        assert pair["matching_words"] >= 8
        assert pair["shared"] and pair["only_left"] and pair["only_right"]
        assert {pair["left"]["group"], pair["right"]["group"]} == {"TVN24", "PAP"}
        # Ponowne żądanie: ponownego iterowania/dekompresowania artykułów nie ma.
        with patch.object(sora.DOCUMENT_DATABASE,"iter_completed_results",
                          side_effect=AssertionError("Powtórzone skanowanie bazy")):
            cached = client.get(path)
            assert cached.status_code == 200
            assert cached.get_json()["matches"] == payload["matches"]
        # Niezaznaczona redakcja nie może przeciec do wyniku.
        out = client.get("/api/baza/wspolna_tresc?mode=folder&group=PAP&group=Onet")
        assert out.status_code == 200
        assert not out.get_json()["matches"]
        assert sora.DOCUMENT_DATABASE.stats() == status
        with sqlite3.connect(os.environ["DROGOWSKAZY_DB_PATH"]) as db:
            after = db.execute(
                "SELECT id, content_sha256, status, analysis_run_id FROM documents ORDER BY id"
            ).fetchall()
        assert before == after, "Analiza treści nie może nic zmienić w SQLite"
        # Po dodaniu nowej analizy cache musi się zmienić.
        extra = article("Raport komisji o działaniu systemu Pegasus", "PAP",
                        COMMON, DIFF_B + " Dodatkowy komunikat.")
        doc = sora.DOCUMENT_DATABASE.begin_import(
            text=extra, filename="nowy.txt", relative_path="PAP/nowy.txt",
            extension=".txt", encoding="utf-8",
            source_bytes=len(extra.encode("utf-8")), app_version="test")["document"]
        sora.DOCUMENT_DATABASE.mark_success(doc["id"], {"analysis_run_id": "shared-next", "sekcje": {}},
                                             expected_content_sha256=doc["content_sha256"])
        changed = client.get(path)
        assert changed.status_code == 200
        assert changed.get_json()["examined_articles"] == 3
    print("PASS: independent shared-passages and differences, explicit selection, cache,"
          " unchanged SQLite, correct invalidation, no cross-folder leaks")
