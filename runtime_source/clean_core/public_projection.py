from __future__ import annotations

"""Current — kompaktowa publiczna projekcja zaakceptowanych relacji."""

import re
from typing import Any, Dict, Iterable, List

from .version import STAGE


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,:;–—-")




MALFORMED_CLAIM_SLOT_RE = re.compile(
    r"\b(?:pan|pani|minister|ministra|poseł|posłanka|senator|senatorka|prezes|prezydent)\s+(?:i|oraz)(?=\s|[,.;:!?]|$)",
    re.I,
)


def _headline_lead_overlap(claim: str) -> bool:
    """Wykrywa nagłówek sklejony z leadem przez powtarzający się wczesny n-gram.

    Nie usuwa relacji z raportu; służy wyłącznie jako bramka jakości TOP.
    """
    tokens = re.findall(r"[a-z0-9ąćęłńóśźż-]+", _clean(claim).casefold(), re.I)
    if len(tokens) < 10:
        return False
    max_start = min(10, len(tokens) - 3)
    for n in (6, 5, 4, 3):
        if len(tokens) < n * 2 + 2:
            continue
        for i in range(max_start):
            gram = tuple(tokens[i:i+n])
            # Trójgram musi zawierać charakterystyczny token, aby nie karać
            # zwykłych powtórek funkcyjnych typu „że to jest”.
            if n == 3 and not any(len(tok) >= 6 for tok in gram):
                continue
            for j in range(i + n + 2, len(tokens) - n + 1):
                if tuple(tokens[j:j+n]) == gram:
                    return True
    return False


def _claim_quality_flags(value: Any) -> List[str]:
    claim = _clean(value)
    flags: List[str] = []
    if not claim:
        return ["empty_claim"]
    if MALFORMED_CLAIM_SLOT_RE.search(claim):
        flags.append("dangling_honorific")
    if claim.count("(") != claim.count(")"):
        flags.append("broken_parenthetical")
    if re.search(r"\b(?:pan|pani|minister|poseł|posłanka|senator|prezes)\s*[,;:]\s*(?:i|oraz)?\b", claim, re.I):
        flags.append("incomplete_named_slot")
    if re.search(r"(?:^|\s)[–—-]\s*red\.?\s*(?:$|[,)])", claim, re.I):
        flags.append("broken_editorial_insert")
    if re.search(r"(?:https?://|pic\.twitter\.com|(?:^|\s)@[A-Za-z0-9_]{2,}|(?:twitter|x)\.com/)", claim, re.I):
        flags.append("social_embed_artifact")
    if re.search(r"\|\s*[A-Z]{1,8}\s*\(@[A-Za-z0-9_]+\)", claim):
        flags.append("embedded_account_signature")
    if _headline_lead_overlap(claim):
        flags.append("headline_lead_overlap")
    words = re.findall(r"[\wąćęłńóśźż-]+", claim, re.I)
    stripped = claim.lstrip('\"„” ')
    if stripped and stripped[0].islower() and (
        len(words) <= 2
        or (len(words) <= 6 and re.match(r"^(?:w|we|na|do|od|po|przy|według|wg|o|z|ze|za|dla|bez|pod|nad|się|że|jak)\b", stripped, re.I))
    ):
        flags.append("short_lowercase_fragment")
    if claim.count('\"') % 2 == 1 or claim.count('„') != claim.count('”'):
        flags.append("unbalanced_quote_fragment")
    if re.search(r"\bŹródło(?:\s+wideo|\s+zdj\.)?\s*:", claim, re.I):
        flags.append("source_marker_artifact")
    return list(dict.fromkeys(flags))


def _relation_context_claim_flags(relation: Dict[str, Any]) -> List[str]:
    claim = _clean(relation.get("claim"))
    flags = _claim_quality_flags(claim)
    claim_words = re.findall(r"[\wąćęłńóśźż-]+", claim, re.I)
    sentence = _clean(relation.get("sentence"))
    sentence_words = re.findall(r"[\wąćęłńóśźż-]+", sentence, re.I)
    action = _clean(relation.get("speaker_action")).casefold()

    if claim and sentence:
        pos = sentence.find(claim)
        if pos >= 0:
            end = pos + len(claim)
            if pos > 0 and sentence[pos - 1].isalpha() and claim[:1].isalpha():
                flags.append("claim_starts_mid_token")
            if end < len(sentence) and sentence[end].isalpha() and claim[-1:].isalpha():
                flags.append("claim_ends_mid_token")

    # Krótki claim wycięty z dużo dłuższego zdania jest częstą sygnaturą
    # urwanego cytatu/obiektu (np. „znacznie szerszym materiałem”).
    if len(claim_words) <= 4 and len(sentence_words) >= 10:
        flags.append("short_extracted_fragment")

    # „X komentował te zatrzymania w TVN24” informuje o samym fakcie
    # komentowania, ale nie zawiera treści komentarza. Taka karta nie może
    # wyglądać jak pewna relacja wypowiedzi.
    if action.startswith("komentowa") and re.match(r"^(?:te|tę|to|tą|ten|tych|tej)\b", claim, re.I):
        flags.append("comment_object_not_statement")

    return list(dict.fromkeys(flags))


MALFORMED_SPEAKER_ACTION_RE = re.compile(
    r"\b(?:powiedzia[łl]|stwierdzi[łl]|oceni[łl]|zaznaczy[łl]|podkreśli[łl]|"
    r"przypomnia[łl]|poinformowa[łl]|odpowiedzia[łl]|doda[łl]|wyjaśni[łl]|"
    r"skomentowa[łl]|zapowiedzia[łl]|potwierdzi[łl])\b",
    re.I,
)

def _top_relation_is_plausible(relation: Dict[str, Any]) -> bool:
    """Końcowa bramka publicznego TOP-u, niezależna od rankingu.

    Nie naprawia relacji i nie tworzy drugiego resolvera. Zatrzymuje jedynie
    ewidentnie uszkodzony mówca→claim przed wejściem do skrótu dla odbiorcy.
    Pełna relacja nadal pozostaje audytowalna w warstwie szczegółowej.
    """
    speaker = _clean(relation.get("speaker"))
    if not speaker:
        return True
    if MALFORMED_SPEAKER_ACTION_RE.search(speaker):
        return False
    # Artefakt OCR/scrapingu typu „KPRM Zaznaczył” łączy skrót instytucji z
    # czasownikiem i nie może być traktowany jak osoba.
    tokens = speaker.split()
    if len(tokens) >= 2 and tokens[0].isupper() and 2 <= len(tokens[0]) <= 10:
        if any(MALFORMED_SPEAKER_ACTION_RE.fullmatch(tok.strip(".,:;!?–—-")) for tok in tokens[1:]):
            return False
    severe_claim_flags = {
        "empty_claim", "dangling_honorific", "incomplete_named_slot",
        "broken_parenthetical", "broken_editorial_insert",
        "social_embed_artifact", "embedded_account_signature", "headline_lead_overlap",
        "source_marker_artifact", "short_lowercase_fragment", "unbalanced_quote_fragment",
        "short_extracted_fragment", "comment_object_not_statement",
        "claim_starts_mid_token", "claim_ends_mid_token",
    }
    if severe_claim_flags.intersection(_relation_context_claim_flags(relation)):
        return False
    return True


def _relation_quality_score(relation: Dict[str, Any]) -> float:
    """Jedyny publiczny scoring relacji.

    ETAP aktywny kontrakt: confidence resolvera jest tylko jednym składnikiem. Ranking
    różnicuje relacje na podstawie kompletności i jakości dowodu, bez tworzenia
    drugiej listy TOP ani osobnego pipeline'u.
    """
    confidence = max(0.0, min(1.0, float(relation.get("confidence") or 0.0)))
    # Current: confidence nie może nasycać 80% skali. Resztę wyniku budują
    # kompletność atrybucji, czystość claimu i jakość lokalnego dowodu.
    score = confidence * 5.4

    speaker = _clean(relation.get("speaker"))
    action = _clean(relation.get("speaker_action") or relation.get("attribution_marker"))
    claim = _clean(relation.get("claim"))
    target = _clean(relation.get("target"))
    topic = _clean(relation.get("topic"))
    medium = _clean(relation.get("medium"))
    source = _clean(relation.get("source"))
    document_sources = [x for x in (relation.get("document_sources") or []) if _clean(x)]
    mode = _clean(relation.get("speaker_resolution_mode") or (relation.get("speaker_resolution") or {}).get("mode"))

    if speaker and action:
        score += 0.90
    target_mode = _clean(relation.get("target_resolution_mode"))
    if target:
        if target_mode in {"claim_local_raw_match", "claim_local_explicit_cue", "role_target"}:
            score += 0.55
        else:
            score -= 1.20
    elif topic:
        score += 0.30
    if medium or source or document_sources:
        score += 0.45

    words = re.findall(r"[\wąćęłńóśźż-]+", claim, re.I)
    if 8 <= len(words) <= 80:
        score += 0.80
    elif 4 <= len(words) < 8 or 80 < len(words) <= 140:
        score += 0.35
    elif len(words) < 4:
        score -= 0.60

    claim_flags = _relation_context_claim_flags(relation)
    if {"social_embed_artifact", "embedded_account_signature"}.intersection(claim_flags):
        score -= 3.50
    elif "headline_lead_overlap" in claim_flags:
        score -= 2.80
    elif "dangling_honorific" in claim_flags or "incomplete_named_slot" in claim_flags:
        score -= 2.40
    elif claim_flags:
        score -= 0.80

    # Atrybucja jawna jest najmocniejsza; dziedziczenie nadal może być poprawne,
    # ale powinno mieć minimalnie niższy priorytet w TOP.
    if mode == "explicit_sentence":
        score += 0.30
    elif mode == "surname_alias":
        score += 0.18
    elif mode == "inherited_same_block":
        score -= 0.15

    # Nie pozwalamy publicznemu rankingowi przekroczyć 9.95, żeby zachować
    # dotychczasową skalę, ale wynik nie jest już stałą kopią confidence.
    return round(max(0.0, min(9.95, score)), 2)

def relation_to_card(relation: Dict[str, Any]) -> Dict[str, Any]:
    speaker = _clean(relation.get("speaker"))
    action = _clean(relation.get("speaker_action"))
    claim = _clean(relation.get("claim"))
    target = _clean(relation.get("target"))
    statement_relation = {
        "kto_mowi": speaker,
        "o_kim": target,
        "co_mowi": claim,
        "topic": _clean(relation.get("topic")),
        "object": _clean(relation.get("object")),
        "medium": _clean(relation.get("medium")),
        "zrodlo": _clean(relation.get("source")),
        "zrodlo_dokumentu": _clean(relation.get("document_source")),
        "zrodla_dokumentu": list(relation.get("document_sources") or []),
        "zrodla_zdjec": list(relation.get("image_sources") or []),
        "afiliacja": _clean(relation.get("affiliation")),
        "program": _clean(relation.get("program")),
        "attribution_marker": _clean(relation.get("attribution_marker")),
    }
    resolution_mode = _clean(relation.get("speaker_resolution_mode"))
    resolution_method = _clean(relation.get("speaker_resolution_method"))
    confidence = float(relation.get("confidence") or 0.0)
    warnings = set(relation.get("warnings") or [])
    risky_warnings = {
        "source_continuation_same_block",
        "speaker_resolved_from_previous_explicit_role",
        "speaker_resolved_from_following_explicit_signature",
        "speaker_inherited_from_previous_sentence",
    }
    sentence = _clean(relation.get("sentence"))
    claim_flags = _relation_context_claim_flags(relation)
    complex_attribution = bool(
        re.search(r"\b(?:powołując|powołujac)\s+się\s+na\b|\b(?:według|wg)\b", sentence, re.I)
        and len(re.findall(r"\b[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+)+\b", sentence)) >= 2
    )
    multi_attribution = len(re.findall(
        r"\b(?:powiedział|powiedziała|stwierdził|stwierdziła|przekazał|przekazała|mówił|mówiła|odparł|odparła|dodał|dodała|relacjonował|relacjonowała|zeznał|zeznała|wskazał|wskazała)\b",
        sentence, re.I,
    )) >= 2
    requires_review = bool(
        resolution_mode in {"inherited_same_block", "surname_alias"}
        or resolution_method in {"forward_quote_signature_attribution", "surname_attribution_resolved_from_document_alias", "source_quote_continuation"}
        or bool(risky_warnings.intersection(warnings))
        or complex_attribution
        or multi_attribution
        or bool({"source_marker_artifact", "short_lowercase_fragment", "unbalanced_quote_fragment", "short_extracted_fragment", "comment_object_not_statement", "claim_starts_mid_token", "claim_ends_mid_token"}.intersection(claim_flags))
        or confidence < 0.80
    )
    return {
        "label": "Relacja wypowiedzi",
        "level": "PUBLIC",
        "role": "DECISION",
        "fragment": _clean(relation.get("sentence") or claim),
        "phrase": claim,
        "claim": claim,
        "claim_quality_flags": claim_flags,
        "claim_top_eligible": not bool({"empty_claim", "dangling_honorific", "incomplete_named_slot", "social_embed_artifact", "embedded_account_signature", "headline_lead_overlap", "source_marker_artifact", "short_lowercase_fragment", "unbalanced_quote_fragment", "short_extracted_fragment", "comment_object_not_statement", "claim_starts_mid_token", "claim_ends_mid_token"}.intersection(claim_flags)),
        "speaker": speaker,
        "kto_mowi": speaker,
        "speaker_entity_id": _clean(relation.get("speaker_entity_id")),
        "speaker_resolution_mode": _clean(relation.get("speaker_resolution_mode")),
        "speaker_resolution_method": _clean(relation.get("speaker_resolution_method")),
        "coreference_scope": _clean(relation.get("coreference_scope")),
        "coreference_score": float(relation.get("coreference_score") or 0.0),
        "coreference_gender_previous": _clean(relation.get("coreference_gender_previous")),
        "coreference_gender_current": _clean(relation.get("coreference_gender_current")),
        "coreference_gender_agreement": bool(relation.get("coreference_gender_agreement")),
        "target": target,
        "target_entity_id": _clean(relation.get("target_entity_id")),
        "target_resolution_mode": _clean(relation.get("target_resolution_mode")),
        "target_quality": _clean(relation.get("target_quality")),
        "dotyczy": target or _clean(relation.get("topic")),
        "object": _clean(relation.get("object")),
        "action": action,
        "speaker_action": action,
        "attribution_marker": _clean(relation.get("attribution_marker")),
        "medium": _clean(relation.get("medium")),
        "source": _clean(relation.get("source")),
        "document_source": _clean(relation.get("document_source")),
        "document_sources": list(relation.get("document_sources") or []),
        "image_sources": list(relation.get("image_sources") or []),
        "affiliation": _clean(relation.get("affiliation")),
        "program": _clean(relation.get("program")),
        "statement_relation": statement_relation,
        "relation": " → ".join(value for value in (speaker or _clean(relation.get("source")), action, claim) if value),
        "relation_id": _clean(relation.get("relation_id")),
        # Tożsamość dokumentu jest częścią kontraktu publicznego. Nie wolno
        # jej odtwarzać ani zerować w warstwie prezentacji.
        "document_id": _clean(relation.get("document_id")),
        "document_index": int(relation.get("document_index") or 0),
        "single_source_of_truth": True,
        "segment_id": _clean(relation.get("segment_id")),
        "confidence": confidence,
        "raw_confidence": float(relation.get("raw_confidence") or confidence),
        "warnings": list(relation.get("warnings") or []),
        "supporting_document_ids": list(relation.get("supporting_document_ids") or []),
        "supporting_relation_ids": list(relation.get("supporting_relation_ids") or []),
        "deduped_repetitions_count": int(relation.get("deduped_repetitions_count") or 0),
        "score": _relation_quality_score(relation),
        "rank_score": _relation_quality_score(relation),
        "why": "Karta publiczna pochodzi bezpośrednio z zaakceptowanej relacji.",
        "canonical_relation": relation,
        "canonical_relation_status": STAGE,
        "requires_review": requires_review,
    }


def rejected_to_card(rejection: Dict[str, Any]) -> Dict[str, Any]:
    reasons = list(rejection.get("reasons") or [])
    reason = reasons[0] if reasons else _clean(rejection.get("reason")) or "rejected_relation"
    return {
        "label": "Relacja odrzucona",
        "level": "BLOCKED",
        "role": "BLOCKED_BY_GUARD",
        "fragment": _clean(rejection.get("sentence") or rejection.get("claim")),
        "phrase": reason,
        "reason": reason,
        "reasons": reasons or [reason],
        "why": "Relacja została odrzucona przez końcową bramkę integralności.",
        "score": 0,
        "rank_score": 0,
        "blocked": True,
        "relation_id": _clean(rejection.get("relation_id")),
        "pipeline_stage": STAGE,
    }


def accepted_cards(relations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [relation_to_card(relation) for relation in relations]


def rejected_cards(relations: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [rejected_to_card(relation) for relation in relations]



def _semantic_claim_key(value: Any) -> str:
    text = _clean(value).casefold()
    text = re.sub(r'^["„”\s]+|["„”\s]+$', '', text)
    text = re.sub(r'^(?:zdaniem|według|wg)\s+[a-ząćęłńóśźż-]+(?:\s+[a-ząćęłńóśźż-]+){0,2}\s+', '', text, flags=re.I)
    text = re.sub(r'\s*[-–—]\s*(?:powiedział\w*|mówił\w*|stwierdził\w*|ocenił\w*|dodał\w*|podkreślił\w*)\s+[^.!?]{0,80}$', '', text, flags=re.I)
    text = re.sub(r'[^a-z0-9ąćęłńóśźż]+', ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()

def _semantic_relation_fingerprint(relation: Dict[str, Any]) -> str:
    speaker = _clean(relation.get("speaker_entity_id") or relation.get("speaker")).casefold()
    claim = _semantic_claim_key(relation.get("claim"))
    source = _clean(relation.get("source_entity_id") or relation.get("source")).casefold()
    return f"{speaker or source}|{claim}"

def build_compact_public_sections(
    accepted: Iterable[Dict[str, Any]],
    rejected: Iterable[Dict[str, Any]],
    *,
    top_limit: int = 5,
) -> Dict[str, List[Dict[str, Any]]]:
    """Zwraca jedyny zestaw kart przeznaczony do widoku i eksportu.

    Surowe warstwy diagnostyczne mogą pozostać dostępne w eksporcie technicznym, ale nie
    są ponownie publikowane jako osobne karty. Każde relation_id występuje raz.
    """
    accepted_rows = list(accepted)
    rejected_rows = list(rejected)
    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for relation in accepted_rows:
        relation_id = _clean(relation.get("relation_id"))
        if relation_id and relation_id in seen:
            continue
        if relation_id:
            seen.add(relation_id)
        card = relation_to_card(relation)
        unique.append(card)
    unique.sort(key=lambda card: float(card.get("rank_score") or 0), reverse=True)

    # Current: surowa lista relacji zachowuje wszystkie różne relation_id, ale TOP
    # nie pokazuje dwóch redakcyjnych wariantów tej samej wypowiedzi.
    top: List[Dict[str, Any]] = []
    semantic_seen: set[str] = set()
    for relation in accepted_rows:
        if not _top_relation_is_plausible(relation):
            continue
        fp = _semantic_relation_fingerprint(relation)
        if not fp or fp in semantic_seen:
            continue
        semantic_seen.add(fp)
        card = relation_to_card(relation)
        top.append(card)
    top.sort(key=lambda card: float(card.get("rank_score") or 0), reverse=True)
    blocked = [rejected_to_card(item) for item in rejected_rows]
    return {
        "relations": unique,
        "top": top[: max(0, int(top_limit))],
        "blocked": blocked,
    }
