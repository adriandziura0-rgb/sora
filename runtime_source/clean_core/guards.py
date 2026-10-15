from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

NEUTRAL_TECH_RX = re.compile(
    r"\b(?:transformacja\s+energetyczna|optymalizacja\s+(?:kodu|zapytania|algorytmu)|wdrozenie\s+aplikacji|uruchomienie\s+serwera|analiza\s+danych)\b",
    re.I,
)
WEAK_CONTRAST_RX = re.compile(
    r"\bnie\s+tylko\b.{1,180}\b(?:ale|lecz)\s+(?:takze|rowniez|tez)\b|\b(?:ale|jednak)\b.{0,80}\b(?:technicznie|informacyjnie|czasowo)\b",
    re.I,
)


def build_guard_cards(*, card_factory: Callable[..., Any], original_text: str, cleaned_info: Dict[str, Any], cleaned_text: str) -> List[Any]:
    """Jawny rejestr bramek P2.

    Nie zmienia decyzji klasyfikatora wstecznie, ale pokazuje analitykowi,
    co zostało uznane za metatekst albo neutralny kontekst i nie powinno
    zasilać głównych P1–P5.
    """
    cards: List[Any] = []
    for seg in cleaned_info.get("metatext_segments", []) or []:
        cards.append(card_factory(
            "GUARD_META_TEXT", "P1", "BLOCKED_BY_GUARD", str(seg.get("text") or ""),
            phrase=str(seg.get("kind") or "metatekst"), start=int(seg.get("start") or -1), end=int(seg.get("end") or -1),
            confidence="high", pattern_confidence="high", interpretation_confidence="high", score=0.0,
            why="P1/P2: fragment rozpoznany jako metatekst lub instrukcja analityczna. Nie zasila P0–P5 tekstu właściwego.",
            guards=["META_TEXT"], requires_review=False, blocked_promotion_to=["P0", "P1", "P2", "P3", "P4", "P5"],
        ))
    for match in NEUTRAL_TECH_RX.finditer(cleaned_text or ""):
        frag = cleaned_text[max(0, match.start()-80):min(len(cleaned_text), match.end()+120)].strip()
        cards.append(card_factory(
            "GUARD_NEUTRAL_TECHNICAL_CONTEXT", "P1", "BLOCKED_BY_GUARD", frag,
            phrase=match.group(0), start=match.start(), end=match.end(), confidence="high",
            pattern_confidence="high", interpretation_confidence="high", score=0.0,
            why="P2: neutralny kontekst techniczny. Nie awansuje do eufemizacji, nominalizacji ani depolityzacji.",
            guards=["NEUTRAL_TECHNICAL_CONTEXT"], requires_review=False,
            blocked_promotion_to=["P1_eufemizacja", "P1_nominalizacja", "P3_depolityzacja_decyzji"],
        ))
    for match in WEAK_CONTRAST_RX.finditer(cleaned_text or ""):
        frag = cleaned_text[max(0, match.start()-80):min(len(cleaned_text), match.end()+120)].strip()
        cards.append(card_factory(
            "GUARD_WEAK_CONTRAST", "P1", "BLOCKED_BY_GUARD", frag,
            phrase=match.group(0)[:80], start=match.start(), end=match.end(), confidence="medium",
            pattern_confidence="medium", interpretation_confidence="medium", score=0.0,
            why="P2: słaby kontrast lub rozszerzenie zakresu. Może być kandydatem formalnym, ale nie mocną antytezą.",
            guards=["WEAK_CONTRAST"], requires_review=False,
            blocked_promotion_to=["P1_antyteza"],
        ))
    return cards
