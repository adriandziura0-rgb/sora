from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .version import STAGE as CLAIM_STAGE

QUOTE_RX = re.compile(r"[„\"]([^„”\"\n]{8,260})[”\"]")
ATTRIBUTION_RX = re.compile(
    r"\b(?:powiedzia[łl]a?|stwierdzi[łl]a?|oceni[łl]a?|uwa[żz]a|uzna[łl]a?|zapowiedzia[łl]a?|"
    r"podkre[śs]li[łl]a?|zaznaczy[łl]a?|doda[łl]a?|przekaza[łl]a?|wed[łl]ug|zdaniem|w\s+ocenie)\b",
    re.I,
)
FACT_RX = re.compile(
    r"\b(?:ma\s+(?:si[ęe]\s+)?(?:stawi[ćc]|odby[ćc]|zosta[ćc])|zosta[łl]a?|b[ęe]dzie|jest|s[ąa]|"
    r"odby[łl]a?|przyj[ęe][łl]a?|podpisa[łl]a?|wezwa[łl]a?|skierowa[łl]a?|rozpocz[ęe][łl]a?|"
    r"komisja|posiedzenie|ustawa|trybuna[łl]|s[ąa]d|prokuratur|sejm|senat)\b",
    re.I,
)
EVALUATION_RX = re.compile(
    r"\b(?:skandal|cyrk|b[łl]azenad|kompromitacj|nielegaln|bezprawn|kluczow|gro[źz]n|"
    r"nadu[żz]y|manipulacj|propagand|atak|presj|chaos|absurd|haniebn|zaskakuj[ąa]c)\w*\b",
    re.I,
)


def _sentences(text: str) -> List[Tuple[int, int, str]]:
    text = text or ""
    out: List[Tuple[int, int, str]] = []
    for m in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text, re.U):
        frag = text[m.start():m.end()].strip()
        if frag:
            out.append((m.start(), m.end(), frag))
    if not out and text.strip():
        out.append((0, len(text), text.strip()))
    return out


def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def _card(label: str, claim_type: str, claim_pl: str, fragment: str, phrase: str, start: int, end: int, why: str, *, speaker: str = "", target: str = "", topic: str = "", object_name: str = "", medium: str = "", program: str = "", source_name: str = "", document_source: str = "", action: str = "", attribution_marker: str = "", relation_id: str = "", score: float = 6.0) -> Dict[str, Any]:
    return {
        "label": label,
        "level": "R2" if claim_type in {"opinia_cytowana", "cytat"} else "R1",
        "analysis_level": "R2" if claim_type in {"opinia_cytowana", "cytat"} else "R1",
        "analysis_level_name": "Fakt/opinia/cytat",
        "role": "FACT_OPINION_QUOTE",
        "fragment": _clean(fragment),
        "phrase": _clean(phrase),
        "start": int(start),
        "end": int(end),
        "confidence": "medium",
        "pattern_confidence": "medium",
        "interpretation_confidence": "medium",
        "score": float(score),
        "rank_score": float(score),
        "analytical_relevance": "high" if claim_type in {"opinia_cytowana", "ocena_redakcyjna"} else "medium",
        "requires_review": claim_type in {"ocena_redakcyjna", "interpretacja_systemu"},
        "why": why,
        "source": source_name,
        "source_name": source_name,
        "pipeline_stage": CLAIM_STAGE,
        "speech_action": action,
        "relation_id": relation_id,
        "single_source_of_truth": bool(relation_id),
        "claim_type": claim_type,
        "claim_type_pl": claim_pl,
        "speaker": speaker,
        "target": target,
        "topic": topic,
        "object": object_name,
        "medium": medium,
        "program": program,
        "document_source": document_source,
        "attribution_marker": attribution_marker,
        "status_pl": claim_pl,
    }


def _locate(text: str, fragment: str, claim: str = "") -> Tuple[int, int]:
    for value in (fragment, claim):
        value = _clean(value)
        if not value:
            continue
        pos = text.find(value)
        if pos >= 0:
            return pos, pos + len(value)
    return -1, -1


def _relation_claim_type(action: str, sentence: str, claim: str, attribution_marker: str = "") -> Tuple[str, str, str, float]:
    action = _clean(action).casefold()
    attribution_marker = _clean(attribution_marker).casefold()
    quoted = bool(claim and re.search(rf"[\"„]{re.escape(claim[:80])}", sentence or "", re.I))
    if action.startswith("zapowied"):
        return "zapowiedz_przypisana", "Zapowiedź przypisana", "FACT_OPINION_QUOTE_ZAPOWIEDZ_PRZYPISANA", 7.4
    if action in {"ocenił", "oceniła", "uznał", "uznała", "stwierdził", "stwierdziła", "zaznaczył", "zaznaczyła"} or attribution_marker in {"według", "wg", "zdaniem", "w ocenie", "w opinii"}:
        return "opinia_cytowana", "Opinia cytowana", "FACT_OPINION_QUOTE_OPINIA_CYTOWANA", 7.3
    if quoted:
        return "cytat_przypisany", "Cytat przypisany", "FACT_OPINION_QUOTE_CYTAT_PRZYPISANY", 7.1
    return "twierdzenie_przypisane", "Wypowiedź przypisana", "FACT_OPINION_QUOTE_WYPOWIEDZ_PRZYPISANA", 6.9


def detect_fact_opinion_quote_cards(
    text: str,
    canonical_relations: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Klasyfikuje materiał na podstawie jednej ``CanonicalRelation``.

    Current nie zgaduje ponownie mówcy i nie skanuje cytatów niezależnie.
    Każda karta jest typowanym widokiem zaakceptowanej CanonicalRelation.
    """
    text = text or ""
    cards: List[Dict[str, Any]] = []
    covered_sentences: set[str] = set()

    for card in canonical_relations or []:
        rr = card.get("canonical_relation") if isinstance(card, dict) else None
        if not isinstance(rr, dict):
            continue
        sentence = _clean(rr.get("sentence") or card.get("fragment"))
        claim = _clean(rr.get("claim"))
        speaker = _clean(rr.get("speaker"))
        if not claim or not speaker:
            continue
        action = _clean(rr.get("speaker_action") or rr.get("action"))
        attribution_marker = _clean(rr.get("attribution_marker"))
        claim_type, claim_pl, label, score = _relation_claim_type(action, sentence, claim, attribution_marker)
        start, end = _locate(text, sentence, claim)
        covered_sentences.add(sentence.casefold())
        cards.append(_card(
            label, claim_type, claim_pl, sentence or claim, claim, start, end,
            "Status twierdzenia korzysta z tej samej zaakceptowanej relacji co TOP i raport; źródła są prezentowane w mapie źródeł.",
            speaker=speaker,
            target=_clean(rr.get("target")), topic=_clean(rr.get("topic")), object_name=_clean(rr.get("object")),
            medium=_clean(rr.get("medium")), program=_clean(rr.get("program")),
            source_name=_clean(rr.get("source")), document_source=_clean(rr.get("document_source")),
            action=action, attribution_marker=attribution_marker,
            relation_id=_clean(rr.get("relation_id")), score=score,
        ))

    # Current: nie istnieje już niezależny skaner cytatów ani faktów.
    # Sekcja jest wyłącznie typowanym widokiem accepted_relations.

    best: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for c in cards:
        key = (str(c.get("claim_type") or ""), str(c.get("relation_id") or ""), _clean(c.get("phrase")).casefold())
        old = best.get(key)
        if old is None or float(c.get("score", 0)) > float(old.get("score", 0)):
            best[key] = c
    return sorted(best.values(), key=lambda c: (int(c.get("start", -1)) if int(c.get("start", -1)) >= 0 else 10**9, -float(c.get("score", 0))))[:80]


def summarize_claim_types(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for c in cards or []:
        label = str(c.get("claim_type_pl") or c.get("claim_type") or "Inne")
        counts[label] = counts.get(label, 0) + 1
    order = ["Fakt opisowy", "Wypowiedź przypisana", "Zapowiedź przypisana", "Opinia cytowana", "Cytat przypisany", "Cytat", "Źródło/medium"]
    items = []
    for name in order:
        if name in counts:
            items.append({"typ": name, "liczba": counts.pop(name)})
    for name, count in sorted(counts.items()):
        items.append({"typ": name, "liczba": count})
    return items
