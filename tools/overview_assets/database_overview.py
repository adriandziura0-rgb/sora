"""Przekrojowy raport tylko do odczytu dla zaznaczonych artykułów Sory.

Nie przelicza analiz, nie dotyka kolektora, importu ani schematu SQLite.
Zwraca metryki wyłącznie 1–10 grup jawnie wybranych przez użytkownika.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from .document_kind import is_article_document
from .editorial_compare import _GroupAccumulator, comparison_group, VALID_MODES, MAX_COMPARE_GROUPS

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
    names = list(dict.fromkeys(str(n).strip() for n in groups if str(n).strip()))
    if not 1 <= len(names) <= MAX_COMPARE_GROUPS:
        raise ValueError("Zaznacz od 1 do 10 folderów lub redakcji.")
    wanted = {name.casefold() for name in names}
    stats = {"selected_groups": len(names)}
    all_articles = _GroupAccumulator("Zaznaczone artykuły")
    by_publisher: dict[str, _GroupAccumulator] = {}
    last_documents: list[dict[str, Any]] = []

    for document, result in rows:
        if not isinstance(document, dict) or not isinstance(result, dict):
            continue
        if not is_article_document(document):
            continue
        document_id = int(document.get("id") or 0)
        if document_id <= 0:
            continue
        group = comparison_group(document, result, safe_mode)
        if group.casefold() not in wanted:
            continue
        publisher = comparison_group(document, result, "publisher") or "(nieustalona redakcja)"
        if publisher not in by_publisher:
            by_publisher[publisher] = _GroupAccumulator(publisher)
        all_articles.add(document, result)
        by_publisher[publisher].add(document, result)
        last_documents.append({
            "id": document_id,
            "name": str(document.get("filename") or ""),
            "path": str(document.get("relative_path") or ""),
            "publisher": publisher,
            "analyzed_at": str(document.get("analyzed_at") or ""),
        })
        if len(last_documents) > 12:
            last_documents.pop(0)

    # Nie dopisujemy danych do SQLite i nie zmieniamy zapisanych analiz.
    groups = [group.summary() for group in by_publisher.values()]
    groups.sort(key=lambda g: (-g["documents"], g["name"].casefold()))
    used = all_articles.documents
    stats.update(articles=used, done_articles=used, processing=0, error=0, duplicates=0, support_files=0)
    notes = ["Raport dotyczy wyłącznie ukończonych analiz w zaznaczonych grupach. Nie obejmuje całej bazy."]
    if len(groups) < 2:
        notes.append("Do porównania redakcji zaznacz co najmniej dwie. Analiza jednej grupy również jest dostępna.")
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
        "recent_documents": list(reversed(last_documents)),
        "notes": notes,
        "method": (
            "Wyłącznie zaznaczone grupy, tylko ukończone artykuły; "
            "pliki techniczne wyłączone. Wyniki tylko z zapisanych analiz SQLite. "
            "Nie uruchamia ponownie silnika ani nie zmienia dokumentów."
        ),
    }
