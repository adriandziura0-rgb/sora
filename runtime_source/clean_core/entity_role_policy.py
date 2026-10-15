from __future__ import annotations

"""Current: centralna polityka typów i ról encji.

Typ encji opisuje czym jest byt. Rola opisuje wyłącznie jego użycie w konkretnej
relacji. Osoba, instytucja lub partia może być jawnym nadawcą, jeżeli występuje
w pozycji podmiotu przy czasowniku raportującym. Medium pozostaje źródłem, a
tytuł funkcyjny nie jest częścią kanonicznej nazwy osoby.
"""

import re
from typing import Any

PERSON_TITLE_PATTERN = re.compile(
    r"^(?:(?:wice)?przewodniczący|(?:wice)?przewodnicząca|europoseł|europosłanka|"
    r"poseł|posłanka|senator|senatorka|minister|ministra|wiceminister|wiceministra|"
    r"rzecznik|rzeczniczka|prokurator|prokuratorka|premier|prezydent|"
    r"szef|szefowa|reporter|reporterka|dziennikarz|dziennikarka|redaktor|redaktorka|"
    r"ekspert|ekspertka|profesor|doktor|sędzia|sędzina|komisarz|mecenas|pan|pani|"
    r"przedstawiciel|przedstawicielka|marszałek|wicemarszałek|lider|liderka)\s+",
    re.I,
)

TECHNICAL_NAME_RE = re.compile(
    r"^(?:R\d{1,3}|T\d{1,3}|P\d{1,3}|Q\d{1,3})[ _.-]|"
    r"(?:canonical[_ ]entity|core[_ ]agency|core[_ ]actor|agency[_ ]relation|"
    r"entity[_ ]graph|report[_ ]only|decision[_ ]suggestion)$",
    re.I,
)

NON_ENTITY_LABELS = {
    "osoby", "aktorzy", "aktor", "grupa", "inne podmioty", "instytucje / partie",
    "media i źródła", "media i zrodla", "źródła", "zrodla", "temat",
}

ROLE_ALLOWED_TYPES = {
    "speaker": {"person", "institution", "party"},
    "claim_subject": {"person", "institution"},
    "target": {"person", "institution", "product"},
    "institution": {"institution"},
    "medium": {"medium"},
    "source": {"medium", "institution"},
    "affiliation": {"party"},
    "mentioned": {"person", "institution", "medium", "party", "product"},
}

SPEECH_ROLE_NAMES = {"speaker", "kto_mowi"}


def clean_name(value: Any) -> str:
    raw = str(value or "")
    keeps_initial_dot = bool(re.search(r"(?:^|\s)[A-ZĄĆĘŁŃÓŚŹŻ]\.\s*$", raw))
    text = re.sub(r"\s+", " ", raw.strip(" \t\r\n,.:;!?()[]{}\"„”'–—-"))
    if keeps_initial_dot and text and not text.endswith("."):
        text += "."
    return text


def strip_person_title(value: Any) -> str:
    text = clean_name(value)
    previous = None
    while text and text != previous:
        previous = text
        text = PERSON_TITLE_PATTERN.sub("", text).strip()
    return text


def is_public_entity_name(value: Any) -> bool:
    text = clean_name(value)
    if not text or text.casefold() in NON_ENTITY_LABELS:
        return False
    if TECHNICAL_NAME_RE.search(text):
        return False
    low = text.casefold()
    if "canonical entity" in low or "core agency" in low or "core actor" in low:
        return False
    return True


def role_allows_type(role: str, entity_type: str) -> bool:
    allowed = ROLE_ALLOWED_TYPES.get(str(role or "mentioned"), ROLE_ALLOWED_TYPES["mentioned"])
    return str(entity_type or "") in allowed


def role_for_type(entity_type: str) -> str:
    return {
        "person": "participant",
        "institution": "institution",
        "medium": "medium",
        "party": "affiliation",
        "product": "topic_object",
    }.get(str(entity_type or ""), "mentioned")
