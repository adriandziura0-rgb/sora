"""Przekrojowy raport tylko do odczytu dla zaznaczonych artykułów Sory.

Nie przelicza analiz, nie dotyka kolektora, importu ani schematu SQLite.
Zwraca metryki wyłącznie 1–10 grup jawnie wybranych przez użytkownika.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from heapq import heappush, heapreplace
from typing import Any, Iterable

from .document_kind import is_article_document
from .editorial_compare import (_GroupAccumulator, comparison_group, _publisher_from_structured_text, VALID_MODES, MAX_COMPARE_GROUPS)

OVERVIEW_SCHEMA = "sora_selected_database_overview_v1"


def _ranking(counter: Counter, maximum: int = 12) -> list[dict[str, Any]]:
    return [{"name": str(label), "count": int(count)}
            for label, count in counter.most_common(maximum) if count > 0]


def build_selected_database_overview(
    rows: Iterable[tuple[dict[str, Any], dict[str, Any]]],
    *,
    mode: str,
    groups: list[str],
) -> dict[str, Any]:
    """Nigdy nie odczytuje analizy całej bazy bez jawnego zaznaczenia."""
    safe_mode = str(mode or "").strip().casefold()
    if safe_mode not in VALID_MODES:
        raise ValueError("Wybierz foldery lub redakcje.")
    names = []
    wanted = set()
    for raw_name in groups:
        name = str(raw_name).strip()
        if name and name.casefold() not in wanted:
            names.append(name)
            wanted.add(name.casefold())
    if not 1 <= len(names) <= MAX_COMPARE_GROUPS:
        raise ValueError("Zaznacz od 1 do 10 folderów lub redakcji.")
    stats = {"selected_groups": len(names)}
    all_articles = _GroupAccumulator("Zaznaczone artykuły")
    by_publisher: dict[str, _GroupAccumulator] = {}
    recent_heap: list[tuple[tuple[str, int], dict[str, Any]]] = []
    source_evidence = Counter()
    source_by_publisher: dict[str, Counter] = {}

    for document, result in rows:
        if not isinstance(document, dict) or not isinstance(result, dict):
            continue
        if not is_article_document(document):
            continue
        try:
            document_id = int(document.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if document_id <= 0:
            continue
        group = comparison_group(document, result, safe_mode)
        if group.casefold() not in wanted:
            continue
        publisher = comparison_group(document, result, "publisher") or "(nieustalona redakcja)"
        # Pole document_source w starszych wynikach może wskazywać agencję,
        # autora lub medium PRZYWOŁANE, nie wydawcę artykułu.
        # Potwierdzenie pochodzi wyłącznie z jawnego nagłówka/URL dokumentu.
        declared = _publisher_from_structured_text(document)
        source_status = ("potwierdzone" if declared else
                         "nieustalone" if publisher == "(nieustalona redakcja)"
                         else "tylko metadane lub folder")
        source_evidence[source_status] += 1
        source_by_publisher.setdefault(publisher, Counter())[source_status] += 1
        if publisher not in by_publisher:
            by_publisher[publisher] = _GroupAccumulator(publisher)
        all_articles.add(document, result)
        by_publisher[publisher].add(document, result)
        recent_document = {
            "id": document_id,
            "name": str(document.get("filename") or ""),
            "path": str(document.get("relative_path") or ""),
            "publisher": publisher,
            "publisher_evidence": source_status,
            "analyzed_at": str(document.get("analyzed_at") or ""),
        }
        recent_key = (recent_document["analyzed_at"], document_id)
        if len(recent_heap) < 12:
            heappush(recent_heap, (recent_key, recent_document))
        elif recent_key > recent_heap[0][0]:
            heapreplace(recent_heap, (recent_key, recent_document))


    # Nie dopisujemy danych do SQLite i nie zmieniamy zapisanych analiz.
    groups = [group.summary() for group in by_publisher.values()]
    groups.sort(key=lambda g: (-g["documents"], g["name"].casefold()))
    used = all_articles.documents
    # Odczyt dotyczy tylko ukończonych analiz. Nie zgadujemy liczby
    # dokumentów w kolejce, błędów ani duplikatów w zaznaczonych grupach.
    stats.update(articles=used, done_articles=used, stats_scope="tylko ukończone analizy")
    notes = ["Raport dotyczy wyłącznie ukończonych analiz w zaznaczonych grupach. Nie obejmuje całej bazy."]
    if len(groups) < 2:
        notes.append("Do porównania redakcji zaznacz co najmniej dwie. Analiza jednej grupy również jest dostępna.")
    if source_evidence["tylko metadane lub folder"] or source_evidence["nieustalone"]:
        notes.append(
            "Źródło publikacji nie jest potwierdzone dla wszystkich artykułów. "
            "Folder, nazwa serwisu w metadanych i źródło cytowane w tekście to różne informacje. "
            "Nie przypisujemy automatycznie artykułów do TVP, TVN24 ani innych redakcji "
            "wyłącznie na podstawie dowolnej nazwy folderu."
        )
    if groups and min(g["documents"] for g in groups) < 5:
        notes.append("Niektóre redakcje mają mniej niż 5 artykułów. Różnice wskaźników są bardzo niestabilne.")
    if groups and max(g["documents"] for g in groups) >= 4 * max(1, min(g["documents"] for g in groups)):
        notes.append("Próby redakcji różnią się wielkością. Porównuj wskaźniki /1000 słów i odsetki, nie same liczby.")
    notes.append(
        "Sygnały P0–P5 i relacje są automatycznymi oznaczeniami wymagającymi weryfikacji, "
        "nie dowodem intencji redakcji. Identyczne teksty z różnych źródeł mogą jeszcze "
        "wymagać osobnego przypisania publikacji."
    )

    return {
        "ok": True,
        "schema": OVERVIEW_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "tylko zaznaczone foldery lub redakcje",
        "selection_mode": safe_mode,
        "selected_groups": names,
        "read_only": True,
        "stats": stats,
        "analyzed_articles": used,
        "publisher_count": len(groups),
        "summary": all_articles.summary(),
        "sources": groups,
        "source_audit": {
            "scope": "tylko zaznaczone ukończone artykuły",
            "confirmed": source_evidence["potwierdzone"],
            "indirect": source_evidence["tylko metadane lub folder"],
            "unknown": source_evidence["nieustalone"],
            "per_publisher": [
                {"publisher": name, "confirmed": counter["potwierdzone"],
                 "indirect": counter["tylko metadane lub folder"],
                 "unknown": counter["nieustalone"]}
                for name, counter in sorted(source_by_publisher.items())
            ],
            "method": "Potwierdzone: jawny źródłowy nagłówek artykułu lub URL; "
                      "pośrednie: tylko wcześniejsze metadane lub rozpoznana ścieżka. "
                      "Nie zmienia dawnych analiz ani nie dopisuje źródła w SQLite.",
        },
        "rankings": {
            "speakers": _ranking(all_articles.speakers),
            "targets": _ranking(all_articles.targets),
            "topics": _ranking(all_articles.topics),
            "cited_sources": _ranking(all_articles.cited_sources),
            "claim_types": _ranking(all_articles.claim_types),
            "p0": _ranking(all_articles.p0),
            "p1": _ranking(all_articles.p1),
            "p2": _ranking(all_articles.p2),
            "p3": _ranking(all_articles.p3),
            "p4": _ranking(all_articles.p4),
            "p5": _ranking(all_articles.p5),
        },
        "recent_documents": [item[1] for item in sorted(recent_heap, key=lambda item: item[0], reverse=True)],
        "notes": notes,
        "method": (
            "Wyłącznie zaznaczone grupy, tylko ukończone artykuły; "
            "pliki techniczne wyłączone. Wyniki tylko z zapisanych analiz SQLite. "
            "Nie uruchamia ponownie silnika ani nie zmienia dokumentów."
        ),
    }
