from __future__ import annotations

from typing import Any, Dict, List

CATEGORY = {
    "person": "Osoby",
    "institution": "Instytucje",
    "party": "Partie / afiliacje",
    "medium": "Media i źródła",
    "product": "Inne podmioty",
}


def build_entity_group_cards(actor_cards: List[Dict[str, Any]], source_cards: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """ER3: grupuje wyłącznie gotowe encje kanoniczne.

    Nie wyszukuje nazw regexem w treści kart i nie tworzy nowych encji.
    """
    buckets: Dict[str, Dict[str, Any]] = {}
    for card in list(actor_cards or []) + list(source_cards or []):
        name = str(card.get("canonical_name") or card.get("phrase") or "").strip()
        entity_id = str(card.get("entity_id") or "").strip()
        entity_type = str(card.get("entity_type") or "").strip()
        if not name or not entity_id:
            continue
        category = CATEGORY.get(entity_type, "Inne podmioty")
        bucket = buckets.setdefault(category, {"items": {}, "count": 0})
        bucket["items"][entity_id] = name
        bucket["count"] += int(card.get("mentions") or 1)

    out: List[Dict[str, Any]] = []
    for category in ("Osoby", "Instytucje", "Partie / afiliacje", "Media i źródła", "Inne podmioty"):
        bucket = buckets.get(category)
        if not bucket:
            continue
        items = sorted(bucket["items"].values(), key=str.lower)
        out.append({
            "label": "ER3_CANONICAL_ENTITY_GROUP",
            "level": "R1",
            "analysis_level": "R1",
            "analysis_level_name": "Kanoniczna grupa encji",
            "role": "CANONICAL_ENTITY_GROUP",
            "fragment": ", ".join(items[:12]),
            "phrase": category,
            "start": -1,
            "end": -1,
            "confidence": "high",
            "pattern_confidence": "high",
            "interpretation_confidence": "high",
            "score": 7.0,
            "rank_score": 7.0,
            "analytical_relevance": "medium",
            "requires_review": False,
            "why": "ER3: grupa zbudowana wyłącznie z entity_id i canonical_name; renderer nie wykrywa nazw samodzielnie.",
            "source": "canonical_entity_builder",
            "items": items,
            "count": len(items),
            "grouped_counts": {category: len(items)},
            "status_pl": f"{category}: {len(items)}",
        })
    return out
