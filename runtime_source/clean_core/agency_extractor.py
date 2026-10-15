from __future__ import annotations

"""Current — mapa sprawczości wyłącznie z CanonicalRelation.

Usunięto dawny skaner czasowników, strony biernej i nominalizacji. Mapa publiczna nie interpretuje tekstu po raz drugi.
Każdy wiersz jest projekcją istniejącej relacji canonical_relation_v1.
"""

import hashlib
import re
from collections import Counter
from typing import Any, Dict, Iterable, List

from .version import STAGE
QUALITY_STAGE = STAGE


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,:;–—-")


def _relation_id(relation_id: str, actor: str, action: str, claim: str) -> str:
    raw = "|".join((_clean(relation_id), _clean(actor).casefold(), _clean(action).casefold(), _clean(claim).casefold()))
    return "agency_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_agency_cards(
    text: str,
    canonical_relation_cards: Iterable[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Buduje mapę ``kto → mówi/robi → co`` bez skanowania ``text``.

    Parametr ``text`` pozostaje wyłącznie dla zgodności wywołania; jego treść nie
    jest analizowana. Brak relacji kanonicznych oznacza pustą mapę.
    """
    del text
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for card in canonical_relation_cards or []:
        rr = card.get("canonical_relation") if isinstance(card, dict) else None
        if not isinstance(rr, dict) or rr.get("rejected"):
            continue
        actor = _clean(rr.get("speaker"))
        action = _clean(rr.get("speaker_action"))
        claim = _clean(rr.get("claim"))
        relation_id = _clean(rr.get("relation_id"))
        if not actor or not action or not claim or not relation_id:
            continue
        if relation_id in seen:
            continue
        seen.add(relation_id)
        target = _clean(rr.get("target"))
        topic = _clean(rr.get("topic"))
        obj = _clean(rr.get("object"))
        relation_text = f"{actor} → {action} → {claim}"
        out.append({
            "label": "Q1_AGENCY_FROM_CANONICAL_RELATION",
            "level": "R2",
            "role": "AGENCY_RELATION",
            "fragment": _clean(rr.get("sentence") or claim),
            "phrase": relation_text,
            "actor": actor,
            "actor_entity_id": _clean(rr.get("speaker_entity_id")),
            "action": action,
            "object": claim,
            "target": target,
            "topic": topic,
            "claim_object": obj,
            "medium": _clean(rr.get("medium")),
            "program": _clean(rr.get("program")),
            "source_name": _clean(rr.get("source")),
            "document_source": _clean(rr.get("document_source")),
            "document_sources": list(rr.get("document_sources") or []),
            "agency_type": "canonical_relation",
            "hidden_actor": False,
            "confidence": round(float(rr.get("confidence") or 0.0), 3),
            "score": round(float(rr.get("confidence") or 0.0) * 10, 2),
            "rank_score": round(float(rr.get("confidence") or 0.0) * 10, 2),
            "relation": relation_text,
            "relation_id": relation_id,
            "agency_relation_id": _relation_id(relation_id, actor, action, claim),
            "source": "canonical_relation",
            "pipeline_stage": STAGE,
            "implementation_stage": STAGE,
            "quality_stage": QUALITY_STAGE,
            "why": "Mapa sprawczości jest bezpośrednią projekcją jednej zaakceptowanej relacji.",
        })
    return out


def build_agency_ranking(cards: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts = Counter(_clean(c.get("actor")) for c in cards if _clean(c.get("actor")))
    return [
        {
            "label": "Q1_AGENCY_ACTOR_RANKING",
            "level": "INFO",
            "role": "REPORT_ONLY",
            "actor": actor,
            "phrase": actor,
            "action_count": count,
            "score": count,
            "rank_score": count,
            "pipeline_stage": STAGE,
            "implementation_stage": STAGE,
            "quality_stage": QUALITY_STAGE,
            "why": f"{count} zaakceptowanych relacji przypisanych aktorowi.",
        }
        for actor, count in counts.most_common()
    ]
