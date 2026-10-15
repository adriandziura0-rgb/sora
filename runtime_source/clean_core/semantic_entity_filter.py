from __future__ import annotations

"""ER2.5: obowiązkowa bramka semantyczna przed EntityGraph.

Moduł nie poprawia gotowych kart. Odrzuca błędnych kandydatów zanim zostaną
zarejestrowani jako encje. Każdy kandydat do EntityRegistry przechodzi przez
jedną funkcję ``validate_entity_candidate``.
"""

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .entity_role_policy import is_public_entity_name

EDITORIAL_PHRASES = {
    "link", "link skopiowany", "link skopiowany do schowka", "podziel się",
    "tagi", "źródło", "autorka", "autor", "czytaj więcej", "zobacz także",
}

FUNCTION_WORDS = {
    "a", "aby", "albo", "ale", "ani", "bardziej", "bo", "by", "być", "czy",
    "dla", "do", "gdy", "gdyby", "i", "jak", "jednak", "każdy", "lecz", "lub",
    "mimo", "na", "nad", "nie", "o", "od", "oraz", "po", "pod", "ponieważ",
    "przy", "przez", "się", "tak", "też", "to", "w", "we", "według", "więc",
    "wobec", "z", "za", "ze", "żeby", "że", "proponują", "domagają", "próbowano",
}

# Słowa rozpoczynające zdanie, które dawny regex mylił z imieniem.
BAD_NAME_START = {
    "Bardziej", "Przy", "Proponują", "Link", "Podziel", "Tagi", "Źródło",
    "Według", "Jednak", "Decyzja", "Osoby", "Grupa", "Aktor", "Inwigilacja",
}

BAD_SINGLETONS = FUNCTION_WORDS | {
    "biura", "decyzja", "demokracji", "grupa", "osoby", "temat", "kontroli",
}

ALLOWED_TYPES = {"person", "institution", "medium", "product", "party", "organization", "place", "topic"}

PERSON_FORBIDDEN_TOKENS = {
    "instytut", "instytucie", "instytutu", "zakład", "zakładu", "kryminologii",
    "karnego", "uniwersytet", "uniwersytetu", "uw", "suwerennej", "polski",
    "holding", "group", "lab", "laboratory", "international", "foundation",
    "association", "institute", "security", "poczta", "rada", "rady", "ministrów",
    "ministerstwa", "sejmu", "senatu", "marszałek", "wicemarszałek", "lider",
    "liderka", "pakt", "paktu", "amber", "gold",
    "trybunał", "trybunału", "trybunałem", "stanu",
    "psl-trzeciej", "drogi", "sojuszu", "lewicy", "demokratycznej",
}

# Akro-nazwa organizacji z końcówką fleksyjną, np. „CIECH-u”, nie może być
# pierwszym tokenem osoby. Zostawiamy inicjały typu „J.”, ale blokujemy formy
# z co najmniej trzema wielkimi literami przed łącznikiem.
ORG_ACRONYM_PREFIX_RE = re.compile(r"^[A-ZĄĆĘŁŃÓŚŹŻ]{3,}(?:-[a-ząćęłńóśźż]{1,4})?$", re.UNICODE)


@dataclass(frozen=True)
class EntityCandidateVerdict:
    accepted: bool
    cleaned: str
    reason: str = ""


def clean_candidate(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip(" \t\r\n,.:;!?()[]{}\"„”'–—-"))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9-]+", value)


def _is_editorial(value: str) -> bool:
    low = value.casefold()
    return low in EDITORIAL_PHRASES or any(low.startswith(x + " ") for x in EDITORIAL_PHRASES)


def validate_entity_candidate(
    value: Any,
    entity_type: str | None = None,
    *,
    known: bool = False,
) -> EntityCandidateVerdict:
    """Ocenia kandydata przed wpisaniem go do EntityRegistry.

    ``known=True`` jest używane wyłącznie dla nazw z kontrolowanego słownika.
    Nawet wtedy metatekst i puste wartości są odrzucane.
    """
    cleaned = clean_candidate(value)
    if not cleaned:
        return EntityCandidateVerdict(False, "", "empty")
    if not is_public_entity_name(cleaned):
        return EntityCandidateVerdict(False, cleaned, "technical_or_group_label")
    if _is_editorial(cleaned):
        return EntityCandidateVerdict(False, cleaned, "editorial")

    tokens = _tokens(cleaned)
    if not tokens:
        return EntityCandidateVerdict(False, cleaned, "no_tokens")
    low_tokens = [t.casefold() for t in tokens]

    if len(tokens) == 1 and low_tokens[0] in BAD_SINGLETONS:
        return EntityCandidateVerdict(False, cleaned, "function_word")
    if tokens[0] in BAD_NAME_START and not known:
        return EntityCandidateVerdict(False, cleaned, "bad_sentence_start")
    if all(t in FUNCTION_WORDS for t in low_tokens):
        return EntityCandidateVerdict(False, cleaned, "only_function_words")
    if len(tokens) > 6 and not known:
        return EntityCandidateVerdict(False, cleaned, "too_long")

    if entity_type and entity_type not in ALLOWED_TYPES:
        return EntityCandidateVerdict(False, cleaned, "unsupported_type")

    # Partykuła trybu warunkowego nie może zostać połknięta przez dynamiczną
    # nazwę instytucji (np. ``komisja by wyjaśniła`` -> ``komisja by``).
    # Przyimki w środku prawdziwych nazw pozostają dozwolone.
    if entity_type in {"institution", "organization", "party", "medium"} and low_tokens[-1] in {
        "by", "gdyby", "żeby", "aby", "że", "iż", "czy",
    }:
        return EntityCandidateVerdict(False, cleaned, "trailing_function_particle")

    if entity_type == "person":
        if len(tokens) < 2:
            return EntityCandidateVerdict(False, cleaned, "person_needs_full_name")
        if tokens[0] in BAD_NAME_START:
            return EntityCandidateVerdict(False, cleaned, "bad_person_start")
        if any(t.casefold() in FUNCTION_WORDS and not (len(t) == 1 and t.isupper()) for t in tokens):
            return EntityCandidateVerdict(False, cleaned, "function_word_in_person")
        if any(t.casefold() in PERSON_FORBIDDEN_TOKENS for t in tokens):
            return EntityCandidateVerdict(False, cleaned, "institution_or_affiliation_fragment_in_person")
        if ORG_ACRONYM_PREFIX_RE.match(tokens[0]):
            return EntityCandidateVerdict(False, cleaned, "organization_acronym_prefix_in_person")
        if not all(t[:1].isupper() for t in tokens):
            return EntityCandidateVerdict(False, cleaned, "person_capitalization")

    # Skróty partyjne muszą wyglądać jak skróty w tekście, a nie fragment słowa
    # po błędnym podziale, np. "ko misarzy".
    if entity_type == "party" and len(cleaned) <= 4 and cleaned != cleaned.upper() and not known:
        # Nazwy z kontrolowanego słownika (np. „PiS”) zachowują oficjalną
        # pisownię. Reguła wielkich liter dotyczy wyłącznie kandydatów
        # wykrytych automatycznie, aby odrzucać przypadkowe fragmenty słów.
        return EntityCandidateVerdict(False, cleaned, "party_abbreviation_case")

    return EntityCandidateVerdict(True, cleaned, "known" if known else "accepted")


def filter_entity_dicts(entities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entity in entities or []:
        verdict = validate_entity_candidate(
            entity.get("canonical_name"), entity.get("entity_type"), known=True
        )
        eid = str(entity.get("entity_id") or "")
        if not verdict.accepted or not eid or eid in seen:
            continue
        seen.add(eid)
        out.append(entity)
    return out
