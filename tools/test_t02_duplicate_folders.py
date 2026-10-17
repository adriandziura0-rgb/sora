"""SORA T02: dwie lokalizacje tego samego tekstu i widocznosc w raportach.

Uruchomienie z root repo (Python 3.11+, tylko standard library):
    python tools/test_t02_duplicate_folders.py --audit

--audit: wypisuje JSON i zalicza odtworzenie obecnego defektu (bez naprawy).
--gate: wymaga przypisania artykulu do obu folderow, do przyszlej regresji;
        na bazowym kodzie 1.2.17 ma zakonczyc sie FAIL.

Wazne: uzywa PRAWDZIWYCH modulow clean_core z tego checkoutu, na bazach
SQLite tworzonych w TemporaryDirectory; nie otwiera bazy uzytkownika,
nie modyfikuje klasyfikatora ani schematu.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime_source"))

from clean_core.document_database import DocumentDatabase  # noqa: E402
from clean_core.editorial_compare import list_comparison_groups  # noqa: E402
from clean_core.database_overview import build_selected_database_overview  # noqa: E402

SOURCE_TEXT = (
    "TYTUŁ: Syntetyczny artykuł do testu dwóch folderów\n"
    "TREŚĆ: Identyczny tekst występuje w dwóch zbiorach.\n"
    "To tylko dane testowe. Nie stanowią materiału prasowego."
)
UNIQUE_TEXT = SOURCE_TEXT + "\nInna wersja treści do kontroli negatywnej."


def insert(database: DocumentDatabase, folder: str, text: str) -> dict:
    filename = "ten_sam.txt"
    data = database.begin_import(
        text=text, filename=filename, relative_path=f"{folder}/{filename}",
        extension=".txt", encoding="utf-8", source_bytes=len(text.encode("utf-8")),
        app_version="T02-synthetic",
    )
    if data["action"] in ("new", "replacement", "retry"):
        doc = data["document"]
        database.mark_success(
            int(doc["id"]),
            {"analysis_run_id": "t02-" + doc["content_sha256"][:12],
             "dlugosc_tekstu": len(text), "sekcje": {}, "dokument": {}},
            expected_content_sha256=doc["content_sha256"],
            retried=data["action"] != "new",
        )
    return data


def scenario(tmp: Path, order: tuple[str, ...], different: bool = False) -> dict:
    database = DocumentDatabase(tmp / "syntetyczna.sqlite3")
    actions = []
    for index, folder in enumerate(order):
        text = UNIQUE_TEXT if different and index == 1 else SOURCE_TEXT
        entry = insert(database, folder, text)
        actions.append({"folder": folder, "action": entry["action"],
                        "document_id": entry["document"]["id"]})

    with sqlite3.connect(database.path) as connection:
        documents = [
            {"id": int(row[0]), "relative_path": str(row[1]),
             "status": str(row[2]), "content_sha256": str(row[3])}
            for row in connection.execute(
                "SELECT id, relative_path, status, content_sha256 FROM documents ORDER BY id"
            )
        ]
        events = [
            {"document_id": int(row[0]) if row[0] is not None else None,
             "relative_path": str(row[1]), "outcome": str(row[2])}
            for row in connection.execute(
                "SELECT document_id, relative_path, outcome FROM import_events ORDER BY id"
            )
        ]
        integrity_check = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_check = connection.execute("PRAGMA foreign_key_check").fetchall()

    rows = list(database.iter_completed_results(include_text=True, article_only=True))
    groups = list_comparison_groups(rows, mode="folder")
    overview = build_selected_database_overview(
        rows, mode="folder", groups=["Folder_A", "Folder_B"]
    )
    per_folder = {
        folder: {
            "saved_documents": len(database.list_documents(folder=folder)),
            "comparison_group_count": next(
                (int(g["documents"]) for g in groups if g["id"] == folder), 0
            ),
        }
        for folder in ("Folder_A", "Folder_B")
    }
    return {
        "actions": actions,
        "documents": documents,
        "import_events": events,
        "list_document_folders": database.list_document_folders(),
        "comparison_groups": groups,
        "selected_overview_articles": overview["analyzed_articles"],
        "selected_overview_groups": overview["selected_groups"],
        "selected_overview_read_only": overview["read_only"],
        "stats": database.stats(),
        "per_folder": per_folder,
        "integrity_check": integrity_check,
        "foreign_key_check": len(foreign_key_check),
    }


def test() -> dict:
    with tempfile.TemporaryDirectory(prefix="sora-t02-", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        results = {}
        for name, order, different in (
            ("A_potem_B_identical", ("Folder_A", "Folder_B"), False),
            ("B_potem_A_identical", ("Folder_B", "Folder_A"), False),
            ("A_potem_B_different", ("Folder_A", "Folder_B"), True),
            ("A_potem_B_3x_duplicate", ("Folder_A", "Folder_B", "Folder_B"), False),
        ):
            case_dir = root / name
            case_dir.mkdir()
            results[name] = scenario(case_dir, order, different=different)

    for label, case in results.items():
        assert case["integrity_check"] == "ok", (label, case["integrity_check"])
        assert case["foreign_key_check"] == 0, (label, case["foreign_key_check"])
        assert case["selected_overview_read_only"] is True
        assert case["selected_overview_groups"] == ["Folder_A", "Folder_B"]

    first = results["A_potem_B_identical"]
    second = results["B_potem_A_identical"]
    distinct = results["A_potem_B_different"]
    repeated = results["A_potem_B_3x_duplicate"]

    assert [x["action"] for x in first["actions"]] == ["new", "duplicate"]
    assert len(first["documents"]) == 1
    assert first["stats"]["duplicates"] == 1
    assert first["per_folder"]["Folder_A"]["saved_documents"] == 1
    assert first["per_folder"]["Folder_B"]["saved_documents"] == 0
    assert first["per_folder"]["Folder_B"]["comparison_group_count"] == 0
    assert first["selected_overview_articles"] == 1
    assert first["import_events"][1]["relative_path"] == "Folder_B/ten_sam.txt"

    assert [x["action"] for x in second["actions"]] == ["new", "duplicate"]
    assert len(second["documents"]) == 1
    assert second["per_folder"]["Folder_A"]["saved_documents"] == 0
    assert second["per_folder"]["Folder_B"]["saved_documents"] == 1

    assert [x["action"] for x in distinct["actions"]] == ["new", "new"]
    assert len(distinct["documents"]) == 2
    assert distinct["per_folder"]["Folder_A"]["comparison_group_count"] == 1
    assert distinct["per_folder"]["Folder_B"]["comparison_group_count"] == 1

    assert [x["action"] for x in repeated["actions"]] == ["new", "duplicate", "duplicate"]
    assert repeated["stats"]["duplicates"] == 2
    assert len(repeated["import_events"]) == 3
    assert len(repeated["documents"]) == 1
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true", help="Zapisz obecny zachowany defekt jako dowód")
    parser.add_argument("--gate", action="store_true", help="Przyszła bramka: oba foldery muszą być reprezentowane")
    args = parser.parse_args()
    results = test()
    print(json.dumps({"test": "SORA-T02", "code": "runtime_source/clean_core",
                      "cases": results}, ensure_ascii=False, indent=2))
    if args.gate:
        a = results["A_potem_B_identical"]
        both = all(
            a["per_folder"][name]["comparison_group_count"] == 1
            for name in ("Folder_A", "Folder_B")
        )
        if not both:
            print("FAIL T02 GATE: identyczny artykuł z folderów A/B nie ma obu przypisań", file=sys.stderr)
            return 1
        print("PASS T02 GATE: obie lokalizacje widoczne bez podwójnego przeliczania")
    else:
        print("PASS T02 AUDIT: odtworzono błąd na prawdziwych modułach; to NIE jest wynik poprawności semantyki.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
