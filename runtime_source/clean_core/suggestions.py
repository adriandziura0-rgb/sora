from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Dict, List


SUGGESTION_CONTRACT = "clean_suggestions_v1"


def _top_examples(cards: list[Any], limit: int) -> list[dict[str, Any]]:
    return [c.to_dict() for c in cards[:limit]]


def _pl_card_fields(title: str, action: str, reason: str, status: str = "Do przeglądu") -> dict[str, Any]:
    """Pola prezentacyjne po polsku. Nie zastępują pól technicznych, tylko pomagają UI."""
    return {
        "tytul_pl": title,
        "dzialanie_pl": action,
        "uzasadnienie_pl": reason,
        "status_pl": status,
    }


def build_clean_suggestions(
    *,
    card_factory: Callable[..., Any],
    p0: list[Any],
    p1_all: list[Any],
    candidates: list[Any],
    text: str,
) -> List[Dict[str, Any]]:
    """Czysta warstwa sugestii.

    Zasady:
    - sugestie są zbiorcze, nie jedna karta na każdy marker;
    - sugestie nie są decyzjami P1;
    - funkcja nie używa bazy, sesji, plików ani architektury spoza linii T;
    - komunikaty użytkownika są po polsku.
    """
    suggestions: List[Dict[str, Any]] = []
    label_counts = Counter(c.label for c in p0)
    structure_candidates = [c for c in p1_all if c.role == "STRUCTURE_CANDIDATE"]
    p1_confirmed = [c for c in p1_all if c.role == "DECISION_SUGGESTION"]

    if p0:
        title = "Grupuj surowe markery P0"
        action = "Pokazuj P0 jako podgląd: grupy, liczniki i kilka przykładów. Nie awansuj P0 do werdyktu."
        reason = f"W tekście znaleziono {len(p0)} surowych markerów w {len(label_counts)} grupach. To są wskazówki, a nie potwierdzona technika."
        card = card_factory(
            "SUGGEST_P0_PREVIEW_GROUPING", "META", "SUGGESTION_ONLY", text[:500],
            phrase="podgląd P0", confidence="high", score=3.0,
            why=reason, requires_review=True,
        ).to_dict()
        card.update(_pl_card_fields(title, action, reason))
        card.update({"examples": _top_examples(p0, 5), "grouped_counts": dict(label_counts)})
        suggestions.append(card)

    if structure_candidates:
        by_label = Counter(c.label for c in structure_candidates)
        title = "Zostaw filtr istotności"
        action = "Struktury poprawne językowo, ale słabo istotne analitycznie, trzymaj jako kandydatów do przeglądu."
        reason = f"Wykryto {len(structure_candidates)} struktur opisowych. Nie powinny być głównymi kartami P1 bez mocnego kontekstu argumentacyjnego."
        card = card_factory(
            "SUGGEST_KEEP_RELEVANCE_FILTER", "META", "SUGGESTION_ONLY", text[:500],
            phrase="filtr istotności", confidence="high", score=3.2,
            why=reason, requires_review=True,
        ).to_dict()
        card.update(_pl_card_fields(title, action, reason))
        card.update({"examples": _top_examples(structure_candidates, 4), "grouped_counts": dict(by_label)})
        suggestions.append(card)

    cand_counts = Counter(c.label for c in candidates)
    for label, count in cand_counts.items():
        examples = [c.to_dict() for c in candidates if c.label == label][:3]
        title = "Kandydat semantyczny do sprawdzenia"
        action = "Sprawdź ręcznie, czy trop semantyczny tworzy pełną strukturę analityczną."
        reason = f"Wykryto {count} kandydatów typu {label}. To nie jest potwierdzona decyzja, tylko trop do przeglądu."
        card = card_factory(
            label, "P1", "SEMANTIC_CANDIDATE", examples[0]["fragment"] if examples else text[:500],
            phrase="kandydat semantyczny", confidence="medium", score=2.5,
            why=reason, requires_review=True,
        ).to_dict()
        card.update(_pl_card_fields(title, action, reason))
        card.update({"examples": examples, "count": count})
        suggestions.append(card)

    if not p1_confirmed and p0 and not candidates:
        title = "Brak mocnej techniki P1"
        action = "Zostaw wynik jako obserwację P0. Nie dorabiaj decyzji, jeśli brakuje pełnej struktury."
        reason = "Tekst ma surowe markery, ale nie ma mocnej, istotnej struktury P1. To poprawne zachowanie systemu."
        card = card_factory(
            "NO_STRONG_P1_DECISIONS", "META", "REPORT_ONLY", text[:500],
            phrase="brak mocnych P1", confidence="high", score=0,
            why=reason, requires_review=False,
        ).to_dict()
        card.update(_pl_card_fields(title, action, reason, status="Informacja"))
        suggestions.append(card)

    if not suggestions:
        title = "Brak mocnych sugestii"
        action = "Nie pokazuj sztucznych kart. Zwróć krótki komunikat, że nie ma mocnych kandydatów."
        reason = "Nie znaleziono mocnych kandydatów rozwojowych. System nie generuje sugestii z pojedynczych, słabych sygnałów."
        card = card_factory(
            "NO_STRONG_SUGGESTIONS", "META", "REPORT_ONLY", text[:300],
            phrase="brak mocnych sugestii", confidence="high", score=0,
            why=reason, requires_review=False,
        ).to_dict()
        card.update(_pl_card_fields(title, action, reason, status="Informacja"))
        suggestions.append(card)

    return suggestions[:7]


def polish_suggestions_summary(suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "liczba_sugestii": len(suggestions),
        "do_przegladu": sum(1 for s in suggestions if s.get("requires_review")),
        "informacyjne": sum(1 for s in suggestions if not s.get("requires_review")),
        "zasada": "Sugestie są pomocą analityczną, nie werdyktem.",
    }
