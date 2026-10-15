from __future__ import annotations

"""canonical_relation_v1: jedyny publiczny model relacji w całej aplikacji.

Moduł nie rozpoznaje tekstu i nie posiada fallbacków. Relacje są tworzone tylko
przez ``canonical_relation_builder`` na podstawie ``EntityGraph``. TOP, raport,
API, UI, audyt ról i statystyki odczytują dokładnie ten sam słownik
``canonical_relation``.
"""

from typing import Any, Dict, List

CANONICAL_RELATION_SECTION = "canonical_relations"
CANONICAL_RELATION_FIELD = "canonical_relation"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def empty_canonical_relation() -> Dict[str, Any]:
    return {
        "relation_id": "",
        "segment_id": "",
        "fragment_type": "",
        "speaker": "",
        "speaker_entity_id": "",
        "speaker_role": "mówca nieustalony",
        "speaker_kind": "",
        "speaker_action": "",
        "attribution_marker": "",
        "affiliation": "",
        "affiliation_entity_id": "",
        "claim_subject": "",
        "claim_subject_entity_id": "",
        "claim_action": "",
        "claim_object": "",
        "claim": "",
        "target": "",
        "target_entity_id": "",
        "target_type": "",
        "topic": "",
        "target_person": [],
        "target_institution": [],
        "mentioned_entities": [],
        "institution": "",
        "institution_entity_id": "",
        "source": "",
        "source_entity_id": "",
        "document_source": "",
        "document_sources": [],
        "image_sources": [],
        "document_source_entity_id": "",
        "medium": "",
        "medium_entity_id": "",
        "program": "",
        "object": "",
        "evidence": [],
        "confidence": 0.0,
        "warnings": ["brak_relacji_kanonicznej"],
        "single_source_of_truth": True,
        "pipeline_stage": "canonical_relation_v1",
    }


def read_canonical_relation(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> Dict[str, Any]:
    """Odczytuje relację bez ponownej analizy, aliasów i pól zgodności."""
    del text_context
    c = card or {}
    relation = c.get(CANONICAL_RELATION_FIELD) if isinstance(c.get(CANONICAL_RELATION_FIELD), dict) else None
    if relation is None and c.get("single_source_of_truth") is True and c.get("relation_id"):
        relation = c
    if relation is None:
        return empty_canonical_relation()

    out = empty_canonical_relation()
    out.update(relation)
    for key in (
        "relation_id", "segment_id", "fragment_type", "speaker", "speaker_entity_id",
        "speaker_role", "speaker_kind", "speaker_action", "attribution_marker", "affiliation", "affiliation_entity_id",
        "claim_subject", "claim_subject_entity_id", "claim_action", "claim_object", "claim", "target",
        "target_entity_id", "target_type", "topic", "institution", "institution_entity_id",
        "source", "source_entity_id", "document_source", "document_source_entity_id", "medium", "medium_entity_id", "program", "object",
    ):
        out[key] = _clean(out.get(key))
    for key in ("target_person", "target_institution", "mentioned_entities", "warnings", "evidence", "document_sources", "image_sources"):
        out[key] = list(out.get(key) or [])
    out["confidence"] = float(out.get("confidence") or 0.0)
    out["single_source_of_truth"] = True
    out["pipeline_stage"] = "canonical_relation_v1"
    return out


def apply_canonical_relation(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> Dict[str, Any]:
    out = dict(card or {})
    relation = read_canonical_relation(out, text_context=text_context)
    out[CANONICAL_RELATION_FIELD] = relation
    out["relation_id"] = relation["relation_id"]
    out["segment_id"] = relation["segment_id"]
    return out


def get_canonical_relation_cards(sections: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    cards = (sections or {}).get(CANONICAL_RELATION_SECTION, [])
    return [c for c in cards if isinstance(c, dict) and read_canonical_relation(c).get("relation_id")]


def canonical_relation(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> Dict[str, Any]:
    return read_canonical_relation(card, text_context=text_context)


def render_relation(card: Dict[str, Any] | None = None, *, view: str = "generic", text_context: Any = "") -> Dict[str, Any]:
    relation = read_canonical_relation(card, text_context=text_context)
    return {
        "view": view,
        "relation_id": relation["relation_id"],
        "segment_id": relation["segment_id"],
        "speaker": relation["speaker"],
        "speaker_entity_id": relation["speaker_entity_id"],
        "speaker_action": relation["speaker_action"],
        "attribution_marker": relation["attribution_marker"],
        "claim_subject": relation["claim_subject"],
        "claim_subject_entity_id": relation["claim_subject_entity_id"],
        "claim": relation["claim"],
        "target": relation["target"],
        "topic": relation["topic"],
        "institution": relation["institution"],
        "affiliation": relation["affiliation"],
        "source": relation["source"],
        "document_source": relation["document_source"],
        "document_sources": list(relation.get("document_sources") or []),
        "image_sources": list(relation.get("image_sources") or []),
        "medium": relation["medium"],
        "program": relation["program"],
        "object": relation["object"],
        # Tożsamość dokumentu jest częścią publicznego kontraktu. Adapter
        # musi kopiować ją z CanonicalRelation zamiast pozostawiać starsze
        # puste pola karty prezentacyjnej.
        "document_id": relation["document_id"],
        "document_index": relation["document_index"],
        "confidence": relation["confidence"],
        "warnings": relation["warnings"],
    }


def relation_view_fingerprint(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> tuple:
    relation = read_canonical_relation(card, text_context=text_context)
    return tuple(relation.get(k) for k in (
        "relation_id", "speaker_entity_id", "speaker", "speaker_action",
        "claim_subject_entity_id", "claim_subject", "claim", "target", "topic",
    ))


def build_canonical_relation_views(sections: Dict[str, Any] | None, *, text_context: Any = "") -> List[Dict[str, Any]]:
    return [render_relation(card, text_context=text_context) for card in get_canonical_relation_cards(sections)]


def build_relation_view_bundle(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> Dict[str, Dict[str, Any]]:
    return {name: render_relation(card, view=name, text_context=text_context) for name in ("top", "report", "speaker", "json")}


def assert_canonical_views_consistent(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> bool:
    bundle = build_relation_view_bundle(card, text_context=text_context)
    fingerprints = {
        tuple(view.get(k) for k in ("relation_id", "speaker_entity_id", "speaker", "speaker_action", "claim_subject_entity_id", "claim_subject", "claim", "target"))
        for view in bundle.values()
    }
    return len(fingerprints) == 1


def synchronize_public_relation_fields(card: Dict[str, Any] | None = None, *, text_context: Any = "") -> Dict[str, Any]:
    """Synchronizuje publiczne pola karty z jedną ``CanonicalRelation``.

    Adapter niczego nie rozpoznaje i nie rekonstruuje. Kopiuje jedynie pola z
    relacji canonical_relation_v1, dzięki czemu TOP, API i raport nie mogą mieć innego mówcy,
    źródła, medium, tematu ani treści niż zagnieżdżona relacja kanoniczna.
    """
    out = dict(card or {})
    relation = read_canonical_relation(out, text_context=text_context)
    if not relation.get("relation_id"):
        return out

    out[CANONICAL_RELATION_FIELD] = relation
    out.update({
        "relation_id": relation["relation_id"],
        "segment_id": relation["segment_id"],
        "speaker": relation["speaker"],
        "speaker_entity_id": relation["speaker_entity_id"],
        "kto_mowi": relation["speaker"],
        "actor": relation["speaker"],
        "action": relation["speaker_action"],
        "speaker_action": relation["speaker_action"],
        "attribution_marker": relation["attribution_marker"],
        "claim": relation["claim"],
        "co_mowi": relation["claim"],
        "target": relation["target"],
        "dotyczy": relation["target"],
        "topic": relation["topic"],
        "claim_subject": relation["claim_subject"],
        "institution": relation["institution"],
        "affiliation": relation["affiliation"],
        "source": relation["source"],
        "document_source": relation["document_source"],
        "document_sources": list(relation.get("document_sources") or []),
        "image_sources": list(relation.get("image_sources") or []),
        "medium": relation["medium"],
        "program": relation["program"],
        "object": relation["object"],
        # Tożsamość dokumentu jest częścią publicznego kontraktu. Adapter
        # musi kopiować ją z CanonicalRelation zamiast pozostawiać starsze
        # puste pola karty prezentacyjnej.
        "document_id": relation["document_id"],
        "document_index": relation["document_index"],
        "confidence": relation["confidence"],
        "warnings": list(relation["warnings"]),
        "audience_topic": relation["target"] or relation["topic"] or relation["object"] or relation["claim_subject"],
        "audience_sense": relation["claim"],
        "public_relation_view": "current",
    })
    return out
