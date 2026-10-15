from __future__ import annotations

"""Current — końcowa bramka integralności relacji.

Tylko relacje zaakceptowane przez ten moduł mogą trafić do TOP, raportu,
mapy aktorów, mapy sprawczości i fakt/opinia/cytat.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List

from .semantic_entity_filter import validate_entity_candidate


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    reasons: List[str]


_FEMALE_NAMES = {
    "anita", "anna", "maria", "magdalena", "arleta", "beata", "patricia", "meraw",
    "katarzyna", "joanna", "ewa", "agnieszka", "monika", "małgorzata", "izabela",
}
_MALE_NAMES = {
    "marcin", "krzysztof", "zbigniew", "dariusz", "donald", "bartosz", "marek",
    "michał", "jan", "jarosław", "paweł", "wojciech", "mateusz", "tomasz", "mariusz",
    "omer", "avichai", "kobi", "roni", "ernest", "przemysław", "piotr", "andrzej",
    "jacek", "szymon", "włodzimierz", "witold", "sławomir", "robert", "maciej",
    "grzegorz", "patryk", "rafał", "mikołaj", "daniel", "donncha",
}
_FEMALE_ACTION_RE = re.compile(r"(?:ła|iała|owała)$", re.I)
_MALE_ACTION_RE = re.compile(r"(?:ł|iał|ował)$", re.I)
_BAD_END_RE = re.compile(r"\b(?:na|w|we|z|ze|do|od|o|po|przez|dla|i|oraz|a|ale|że|iż|który|która|które)$", re.I)
_BROKEN_START_RE = re.compile(
    r"^(?:taże|tępowania|g\s*odzinie|uporczyw\s+ego|immunitet\s+u|"
    r"senator\s+(?:koalicji|pis|lewicy)\b|poseł\s+(?:koalicji|pis|lewicy)\b|"
    r"posłanka\s+(?:koalicji|pis|lewicy)\b|klub\s+(?:czy|ale|że)\b)",
    re.I,
)
_SENTENCE_SOURCE_RE = re.compile(r"[.!?]|\b(?:został|została|zostało|przegłosowała|rozpoczęło|dotarł|nie było|funkcjonariusze)\b", re.I)
# Tytuł może być zapisany dowolną wielkością liter, ale sama nazwa własna
# MUSI zachować kapitalizację. Poprzednia wersja kompilowała cały wzorzec z
# re.I, przez co zwykły claim „Projekt wymaga poprawek” był fałszywie uznawany
# za nazwę osoby i odrzucany jako claim_named_entity_only.
_ENTITY_ONLY_CLAIM_RE = re.compile(
    r"^(?:(?i:doktor|dr|mecenas|profesor|prof|minister|premier|senator|poseł|posłanka|prokurator|rzecznik|rzeczniczka)\s+)?"
    r"[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+){1,3}$"
)

_MATERIAL_TRANSFER_RE = re.compile(
    r"^(?:"
    r"(?:im|mu|jej|nam|wam)\s+(?:te\s+)?(?:pieniądze|środki|dokumenty?|sprzęt)|"
    r"na\s+[^,.;]{0,90}\b(?:fundusz|konto|rachunek)\b[^,.;]{0,90}\b(?:kwotę|pieniądze|środki)\b|"
    # Dopełnienie może być poprzedzone odbiorcą lub przymiotnikiem:
    # „marszałkowi Sejmu wniosek”, „wszystkie odtajnione dokumenty”.
    r"(?:[\wąćęłńóśźż-]+\s+){0,6}(?:wniosek|dokumenty?|pieniądze|kwotę|środki|sprzęt|potwierdzenie)\b"
    r")",
    re.I,
)
_TOPIC_ONLY_SPEECH_RE = re.compile(
    r"^(?:o|na\s+temat|w\s+sprawie)\s+[^,.;:!?]{1,100}$",
    re.I,
)
_ANSWER_TARGET_RE = re.compile(
    r"^(?:(?:też|również)\s+)?(?:na\s+(?:słowa|pytanie|pytania|zarzut|zarzuty)|"
    r"w\s+odpowiedzi\s+na)\b",
    re.I,
)
_TRAILING_FOREIGN_SIGNATURE_RE = re.compile(
    r"\s[-–—]\s*(?:oznajmił[ao]?|powiedział[ao]?|stwierdził[ao]?|dodał[ao]?|"
    r"podkreślił[ao]?|ocenił[ao]?)\s*[.!?]*$",
    re.I,
)
_VAGUE_NEWS_RE = re.compile(r"\b(?:takiego|tego)\s+(?:newsa|newsa|doniesienia|informacji)\b", re.I)
_UNRESOLVED_SHORT_PREDICATE_RE = re.compile(
    r"^(?:nie\s+)?(?:dotarł[ao]?|przysz[łl][ao]?|wpłynęł[ao]?|został[ao]?|"
    r"odpowiedział[ao]?|powiedział[ao]?)$",
    re.I,
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,:;–—-")


def _speaker_gender(name: str) -> str:
    first = _clean(name).split()[0].casefold() if _clean(name).split() else ""
    if first in _FEMALE_NAMES:
        return "female"
    if first in _MALE_NAMES:
        return "male"
    if first.endswith("a") and first not in {"kuba", "barnaba", "donncha"}:
        return "female"
    return "unknown"


def _action_gender(action: str) -> str:
    value = _clean(action).casefold()
    if not value:
        return "unknown"
    if _FEMALE_ACTION_RE.search(value):
        return "female"
    if _MALE_ACTION_RE.search(value):
        return "male"
    return "unknown"


def _speaker_contract_reasons(relation: Dict[str, Any]) -> List[str]:
    """Twarda bramka kanonicznego kontraktu pochodzenia mówcy.

    Nie próbujemy tu ponownie zgadywać osoby. Walidujemy wyłącznie ślad
    utworzony przez jedyny aktywny resolver. Dzięki temu afiliacja, tytuł
    albo przypadkowa encja z claimu nie mogą zostać wtórnie mówcą.
    """
    speaker = _clean(relation.get("speaker"))
    if not speaker:
        return []
    # Kanoniczny kontrakt waliduje provenance tylko dla relacji z aktywnego pipeline'u,
    # który jawnie oznacza nowy kontrakt. Nie zmieniamy semantyki publicznej
    # funkcji validate_relation dla ręcznie składanych relacji.
    if _clean(relation.get("speaker_contract")) != "canonical_speaker_v1":
        return []

    resolution = relation.get("speaker_resolution") or {}
    mode = _clean(resolution.get("mode") or relation.get("speaker_resolution_mode"))
    method = _clean(resolution.get("method") or relation.get("speaker_resolution_method"))
    reasons: List[str] = []

    allowed_modes = {"explicit_sentence", "surname_alias", "inherited_same_block"}
    if mode not in allowed_modes:
        reasons.append("speaker_provenance_missing")
        return reasons

    if mode == "inherited_same_block":
        allowed_methods = {"same_block_role_or_pronoun_attribution", "same_block_previous_explicit_speaker"}
        warning = _clean(resolution.get("warning"))
        if method not in allowed_methods:
            reasons.append("speaker_inheritance_method_invalid")
        if not bool(resolution.get("has_context")):
            reasons.append("speaker_inheritance_without_context")
        if warning not in {"speaker_inherited_from_previous_sentence", "speaker_resolved_from_previous_explicit_role"}:
            reasons.append("speaker_inheritance_unproven")


    if mode == "surname_alias" and method != "surname_attribution_resolved_from_document_alias":
        reasons.append("speaker_alias_method_invalid")

    # Afiliacja i mówca muszą być dwoma różnymi bytami i różnymi typami.
    speaker_id = _clean(relation.get("speaker_entity_id"))
    affiliation_id = _clean(relation.get("affiliation_entity_id"))
    if affiliation_id and speaker_id and affiliation_id == speaker_id:
        reasons.append("affiliation_used_as_speaker")
    if affiliation_id and not affiliation_id.startswith("party:"):
        reasons.append("affiliation_not_party")

    return reasons


def validate_document_sources(sources: Iterable[str]) -> List[str]:
    reasons: List[str] = []
    for source in sources:
        value = _clean(source)
        if not value:
            continue
        if len(value) > 70 or len(value.split()) > 6 or _SENTENCE_SOURCE_RE.search(value):
            reasons.append("invalid_document_source")
            break
    return reasons


def _has_reported_clause_after_action(sentence: str, action: str) -> bool:
    if not sentence or not action:
        return False
    return bool(re.search(
        rf"(?<!\w){re.escape(action)}(?!\w)\s*[,;:]?\s*(?:że|iż)\b",
        sentence,
        re.I,
    ))


def _quality_gate_reasons(relation: Dict[str, Any]) -> List[str]:
    """Konserwatywna bramka błędów semantycznych wykrytych w audycie 3fa.

    Reguły wymagają równocześnie sposobu atrybucji, czasownika i lokalnego
    kształtu zdania. Nie próbują zgadywać brakującej treści; jeśli nie da się
    jej odtworzyć z dowodu, karta zostaje zablokowana i pozostaje w audycie.
    """
    speaker = _clean(relation.get("speaker"))
    source = _clean(relation.get("source"))
    action = _clean(relation.get("speaker_action")).casefold()
    claim = _clean(relation.get("claim"))
    sentence = _clean(relation.get("sentence"))
    method = _clean(relation.get("attribution_method") or relation.get("speaker_resolution_method"))
    words = re.findall(r"[\wąćęłńóśźż-]+", claim, re.I)
    reasons: List[str] = []

    if speaker and re.search(r"\b(?:by|gdyby|żeby|aby|że|iż|czy)$", speaker, re.I):
        reasons.append("speaker_contains_trailing_function_particle")

    # ``przekazać`` jest wieloznaczne. Zachowujemy jawne ``przekazał, że...``,
    # ale blokujemy pieniądze, sprzęt i dokumenty urzędowe.
    if action in {"przekazał", "przekazała", "przekazało"}:
        if _MATERIAL_TRANSFER_RE.search(claim) and not _has_reported_clause_after_action(sentence, action):
            reasons.append("material_transfer_not_speech")

    # Zeznawanie staje się relacją wypowiedzi dopiero z treścią po ``że/iż``.
    if action in {"zeznawał", "zeznawała", "zeznał", "zeznała"}:
        if not _has_reported_clause_after_action(sentence, action):
            reasons.append("testimony_activity_without_claim")

    # ``O kwestii X mówiła Y`` opisuje temat/czynność, a nie samą tezę.
    if action in {"mówił", "mówiła", "mówiło"} and _TOPIC_ONLY_SPEECH_RE.fullmatch(claim):
        reasons.append("speech_topic_without_claim")

    # „X zwrócił się do Y i powiedział, że…” zawiera dwa czasowniki, ale
    # pierwszy opisuje adresata aktu mowy, a nie jego treść. Nie publikujemy
    # osobnej relacji z claimem zaczynającym się od „się do…”. Właściwa
    # treść zostaje wyłapana przez jawne „powiedział/wyjaśnił/…” niżej w zdaniu.
    if action in {"zwrócił", "zwróciła"} and re.match(r"^się\s+do\b", claim, re.I):
        reasons.append("addressing_action_without_claim")

    # Czasownik w następniku hipotezy nie dowodzi, że dana osoba faktycznie
    # wypowiedziała słowa.
    if speaker and action:
        for match in re.finditer(rf"(?<!\w){re.escape(action)}(?!\w)", sentence, re.I):
            prefix = sentence[:match.start()]
            conditional = list(re.finditer(r"\bgdyby\b", prefix, re.I))
            if not conditional:
                continue
            boundary = max(prefix.rfind("."), prefix.rfind("!"), prefix.rfind("?"), prefix.rfind(";"))
            marker_end = conditional[-1].end()
            speaker_tokens = speaker.split()
            speaker_cue = speaker if speaker and speaker.casefold() in prefix[marker_end:].casefold() else (
                speaker_tokens[-1] if speaker_tokens and speaker_tokens[-1].casefold() in prefix[marker_end:].casefold() else ""
            )
            if conditional[-1].start() > boundary and speaker_cue:
                reasons.append("hypothetical_speech_not_asserted")
                break

    # Przy aliasie na początku zdania relatyw ``sąd..., który uznał`` nie
    # może przejąć mówcy ``Bosacki``. Bezpośrednie ``Jan, który powiedział``
    # pozostaje dozwolone.
    if speaker and action and method == "leading_surname_explicit_alias":
        relative_re = re.compile(
            rf"\b(?:który|która|które|którzy)\b[^,.;:!?]{{0,80}}?"
            rf"(?<!\w){re.escape(action)}(?!\w)",
            re.I,
        )
        for rel in relative_re.finditer(sentence):
            before_relative = sentence[:rel.start()].rstrip(" ,")
            forms = {speaker.casefold(), speaker.split()[-1].casefold() if speaker.split() else ""}
            if not any(before_relative.casefold().endswith(form) for form in forms if form):
                reasons.append("relative_clause_subject_mismatch")
                break

    if claim and (claim.endswith("…") or re.search(r"\.{3,}$", claim)):
        reasons.append("claim_ends_with_ellipsis")
    if re.fullmatch(r"takich\s+osób\s*,?\s+jak", claim, re.I):
        reasons.append("claim_broken_parenthetical")
    if method == "trailing_surname_explicit_alias" and re.match(r"^(?:ale\s+i|i|oraz)\b", claim, re.I):
        reasons.append("claim_starts_with_detached_conjunction")
    if action in {"odpowiedział", "odpowiedziała", "odpowiedziało"} and _ANSWER_TARGET_RE.match(claim):
        reasons.append("answer_target_without_answer")
    if _TRAILING_FOREIGN_SIGNATURE_RE.search(claim):
        reasons.append("foreign_trailing_attribution_in_claim")
    if len(words) <= 3 and _UNRESOLVED_SHORT_PREDICATE_RE.fullmatch(claim):
        reasons.append("unresolved_short_predicate")
    embedded_short = re.match(
        r"^jak\s+(?:mówi|twierdzi|podaje)\s+[^,]{1,80},\s*(?P<predicate>.+)$",
        claim,
        re.I,
    )
    if embedded_short and _UNRESOLVED_SHORT_PREDICATE_RE.fullmatch(_clean(embedded_short.group("predicate"))):
        reasons.append("unresolved_short_predicate")
    if _VAGUE_NEWS_RE.search(claim) and not re.search(r"\b(?:że|iż)\b", claim, re.I):
        reasons.append("vague_anaphoric_news_claim")

    # Awaryjna ochrona źródła: sam cytowany okolicznik nie jest pełną tezą.
    if source and method == "attribution_prefix" and len(words) <= 5 and not re.search(
        r"\b(?:jest|są|był|była|było|będą|ma|mają|może|mogą|musi|muszą|"
        r"podjął|podjęła|podejmował|podejmowała|uznał|uznała|stwierdził|stwierdziła)\b",
        claim,
        re.I,
    ):
        reasons.append("source_claim_not_propositional")

    return list(dict.fromkeys(reasons))


def validate_relation(relation: Dict[str, Any]) -> ValidationResult:
    reasons: List[str] = []
    speaker = _clean(relation.get("speaker"))
    speaker_kind = _clean(relation.get("speaker_kind"))
    action = _clean(relation.get("speaker_action"))
    claim = _clean(relation.get("claim"))
    source = _clean(relation.get("source"))

    # Current: jakość metadanych źródłowych jest ostrzeżeniem dokumentu, a nie
    # powodem odrzucenia poprawnej semantycznie relacji.
    source_warnings = validate_document_sources(relation.get("document_sources") or [])
    if source_warnings:
        relation.setdefault("document_source_warnings", [])
        relation["document_source_warnings"] = list(dict.fromkeys(list(relation.get("document_source_warnings") or []) + source_warnings))
    reasons.extend(_speaker_contract_reasons(relation))
    reasons.extend(_quality_gate_reasons(relation))

    if speaker:
        entity_id = _clean(relation.get("speaker_entity_id"))
        if speaker_kind == "person":
            if not entity_id.startswith("person:"):
                reasons.append("speaker_not_confirmed_person")
            person_verdict = validate_entity_candidate(speaker, "person")
            if not person_verdict.accepted:
                reasons.append("speaker_name_not_person_like")
            sg = _speaker_gender(speaker)
            ag = _action_gender(action)
            if ag == "unknown":
                ag = _clean(relation.get("coreference_gender_current")) or "unknown"
            if ag == "unknown" and _clean(relation.get("speaker_resolution_mode")) == "inherited_same_block":
                trailing_action = re.search(r"[-–—]\s*([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+ł[ao]?)\s*[.!?]*$", claim, re.I)
                if trailing_action:
                    ag = _action_gender(trailing_action.group(1))
            if sg != "unknown" and ag != "unknown" and sg != ag:
                reasons.append("speaker_action_gender_mismatch")
        elif speaker_kind in {"institution", "party", "organization"}:
            # Jawna instytucja/partia może być nadawcą („Rząd poinformował…”,
            # „PiS twierdzi…”). Wymagamy kanonicznego entity_id właściwego typu.
            expected_prefix = "party:" if speaker_kind == "party" else "institution:" if speaker_kind == "institution" else ""
            if expected_prefix and not entity_id.startswith(expected_prefix):
                reasons.append("institutional_speaker_not_canonical")
        elif speaker_kind in {"source", "media"}:
            if not (source or entity_id or _clean(relation.get("medium"))):
                reasons.append("source_speaker_not_confirmed")
        else:
            reasons.append("speaker_not_confirmed_person_or_source")
    elif not source:
        reasons.append("unresolved_attribution")

    if speaker and not action and not _clean(relation.get("attribution_marker")):
        reasons.append("missing_speech_action")

    # aktywny kontrakt: target musi być nie tylko kanoniczny, ale lokalnie udowodniony w claimie.
    # Brak targetu jest dozwolony; fałszywy target nie.
    target = _clean(relation.get("target"))
    target_type = _clean(relation.get("target_type"))
    target_id = _clean(relation.get("target_entity_id"))
    target_mode = _clean(relation.get("target_resolution_mode"))
    if target:
        if target_type == "role":
            if target_mode != "role_target":
                reasons.append("target_role_provenance_invalid")
        else:
            if target_type not in {"person", "institution", "product"}:
                reasons.append("target_type_invalid")
            if not target_id or not target_id.startswith(("person:", "institution:", "product:")):
                reasons.append("target_not_canonical_entity")
            if target_mode not in {
                "claim_local_raw_match", "claim_local_explicit_cue", "predicate_local_raw_match",
                "claim_lead_named_entity", "claim_named_product",
            }:
                reasons.append("target_not_claim_local")

    words = re.findall(r"[\wąćęłńóśźż-]+", claim, re.I)
    if re.search(r"\bŹródło(?:\s+wideo|\s+zdj\.)?\s*:", claim, re.I):
        reasons.append("claim_contains_source_ui_artifact")
    if len(words) < 2:
        reasons.append("claim_too_short")
    if _BAD_END_RE.search(claim):
        reasons.append("claim_incomplete_ending")
    if _BROKEN_START_RE.search(claim):
        reasons.append("claim_broken_start")
    if claim and claim[0].islower() and len(words) < 2 and not claim.startswith(('"', '„')):
        reasons.append("claim_fragment_not_standalone")
    # Current: sama nazwa osoby/roli nie jest treścią wypowiedzi. Twarda bramka
    # zatrzymuje relacje typu „Krzysztof Brejza → mówi: Doktor Mikołaj Małecki”.
    if claim and _ENTITY_ONLY_CLAIM_RE.fullmatch(claim):
        reasons.append("claim_named_entity_only")

    # Role nie mogą być mówcą nawet wtedy, gdy resolver podał je jako tekst.
    low = speaker.casefold()
    if low.startswith(("nowej lewicy", "platformy obywatelskiej", "koalicji obywatelskiej", "funduszu ", "ministerstwa ")):
        reasons.append("non_person_role_as_speaker")
    if low.startswith(("pan ", "pani ", "przedstawicielka ", "przedstawiciel ")):
        reasons.append("speaker_not_canonical")

    return ValidationResult(not reasons, list(dict.fromkeys(reasons)))
