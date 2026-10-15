from __future__ import annotations

"""Current — jedyny aktywny resolver relacji wypowiedzi.

Resolver rozpoznaje wyłącznie jawne konstrukcje atrybucyjne. Nie zgaduje aktora
z przypadkowych wielkich liter i nie traktuje przymiotników jako czasowników.
Obsługiwane są między innymi:

* ``X powiedział/stwierdził/ocenił, że ...``;
* ``... — powiedział X``;
* ``w ocenie X ...`` / ``zdaniem X ...`` / ``według X ...``;
* ``medium pisze/twierdzi/podaje, że ...``;
* lokalne dziedziczenie mówcy dla ``Dodał, że ...``.

Publiczne funkcje zachowują dotychczasowe nazwy. Dodatkowy bundle zwraca również
jawne odrzucenia, aby bramki mogły pokazać przyczynę niewytworzenia relacji.
"""

import re
from typing import Any, Dict, List, Tuple

from .entity_registry import ENTITY_SPECS, COMMON_GIVEN_NAMES, PERSON_TOKEN_NOMINATIVE, normalize_person_surface
from .semantic_entity_filter import validate_entity_candidate
from .segmentation import analyzable_blocks

from .version import STAGE


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _subject_scan_text(value: Any) -> str:
    """Usuwa dopowiedzenia redakcyjne przed szukaniem podmiotu.

    Nazwisko wspomniane w nawiasie lub po ``nawiązując do`` nie może
    przejąć bieżącej wypowiedzi. Treść claimu pozostaje niezmieniona.
    """
    text = _clean(value)
    text = re.sub(r"\([^)]*\)", " ", text)
    # Nazwa medium w konstrukcji „X w rozmowie z "Medium" ...” jest
    # źródłem/kontekstem rozmowy, nigdy kandydatem na osobę mówiącą.
    text = re.sub(r"\b(?:w\s+rozmowie\s+z|dla)\s+[\"„][^\"”]{2,100}[\"”]", " ", text, flags=re.I)
    # To samo dla niecytowanych nazw znanych mediów. W eksporcie prasowym
    # konstrukcja ``w Radiu ZET Żurek powiedział`` albo ``w Interii Bochenek
    # przekazał`` nie może utworzyć osoby ``Radiu Zet Żurek``.
    if globals().get("MEDIA_ALT"):
        text = re.sub(
            rf"\b(?:w\s+rozmowie\s+z|dla|w|we)\s+(?:{MEDIA_ALT})(?!\w)",
            " ", text, flags=re.I,
        )
    # Typowe spójniki międzyzdaniowe nie są częścią nazwy nadawcy.
    text = re.sub(
        r"^(?:ponadto|dodatkowo|co\s+więcej|jednocześnie|tymczasem|natomiast|z\s+kolei|również|także)\s+",
        "", text, flags=re.I,
    )
    # Podpis zdjęcia sklejony z treścią nie może zanieczyścić podmiotu.
    text = re.sub(
        r"^(?:(?:fot\.?\s+)?(?:Adobe\s+Stock|Shutterstock|Getty\s+Images|PAP))\s+(?=(?:Firma|Spółka|Koncern|Grupa)\b)",
        "", text, flags=re.I,
    )
    text = re.sub(r"\b(?:nawiązując|odnosząc|zwracając się)\s+do\b.*$", " ", text, flags=re.I)
    return _clean(text)


PERSON_ACTIONS: Tuple[str, ...] = (
    "tłumaczyła", "tłumaczył", "komentowała", "komentował", "odpowiedziała", "odpowiedział",
    "przypomniała", "przypomniał", "poinformowała", "poinformował", "przekazała", "przekazał",
    "podkreśliła", "podkreślił", "stwierdziła", "stwierdził", "powiedziała", "powiedział",
    "zapowiedziała", "zapowiedział", "wyjaśniła", "wyjaśnił", "zaznaczyła", "zaznaczył",
    "przyznała", "przyznał", "oceniła", "ocenił", "dodała", "dodał", "orzekła", "orzekł",
    "uznała", "uznał", "zdecydowała", "zdecydował", "ustaliła", "ustalił", "oświadczyła",
    "oświadczył", "mówiła", "mówił", "apelowała", "apelował", "potwierdziła", "potwierdził",
    "wskazała", "wskazał", "zauważyła", "zauważył", "podsumowała", "podsumował",
    "zapytała", "zapytał", "skomentowała", "skomentował", "wspomniała", "wspomniał",
    "skwitowała", "skwitował", "sugerowała", "sugerował", "zaapelowała", "zaapelował",
    "wymieniła", "wymienił", "zwróciła", "zwrócił",
    "odparła", "odparł", "zeznawała", "zeznawał", "zeznała", "zeznał",
    "zaprzeczyła", "zaprzeczył", "wyjaśniała", "wyjaśniał", "wskazywała", "wskazywał",
    "napisała", "napisał", "pisała", "pisał",
    "kontynuowała", "kontynuował", "zapewniła", "zapewnił",
    "przewidywała", "przewidywał",
)
SOURCE_ACTIONS: Tuple[str, ...] = (
    "pisze", "napisała", "napisał", "opisuje", "opisała", "opisał", "podaje", "podała", "podał",
    "informuje", "poinformowała", "poinformował", "twierdzi", "twierdziła", "twierdził",
    "relacjonuje", "relacjonowała", "relacjonował", "czytamy",
)
# Neutrum jest częste dla nazw instytucji i partii: ministerstwo/PSL/CBA
# „poinformowało”, „stwierdziło”, „wyjaśniło”. Te formy są częścią tego samego
# resolvera, a nie równoległą ścieżką instytucjonalną.
INSTITUTION_ACTIONS: Tuple[str, ...] = (
    "poinformowało", "stwierdziło", "wyjaśniło", "podało", "potwierdziło",
    "zapowiedziało", "oceniło", "podkreśliło", "zaznaczyło", "przyznało",
    "oświadczyło", "uznało", "zdecydowało", "ustaliło", "przekazało",
    "opisało", "napisało", "twierdziło", "relacjonowało", "dodało", "mówiło",
    "wskazało", "zauważyło", "przypomniało", "zapewniło",
)
ACTION_FORMS: Tuple[str, ...] = tuple(dict.fromkeys(PERSON_ACTIONS + SOURCE_ACTIONS + INSTITUTION_ACTIONS))
ACTION_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, ACTION_FORMS), key=len, reverse=True)) + r")\b", re.I)
ANAPHORIC_START_RE = re.compile(
    r"^(?:[,;:]\s*)?(?:[-–—]\s*)?(?P<action>" + "|".join(sorted(map(re.escape, ACTION_FORMS), key=len, reverse=True)) + r")\b",
    re.I,
)


def _action_gender(action: Any) -> str:
    """Zwraca jawny rodzaj formy czasu przeszłego, jeśli jest kodowany w formie.

    Nie próbujemy zgadywać rodzaju dla czasu teraźniejszego (np. ``twierdzi``).
    Ta funkcja służy wyłącznie jako bramka przeciw oczywistemu błędnemu
    dziedziczeniu typu ``powiedział ... / Dodała ...``.
    """
    value = _clean(action).casefold()
    if not value:
        return ""
    if re.search(r"ł[oa]$", value):
        return "neuter" if value.endswith("ło") else "female"
    if value.endswith("ła"):
        return "female"
    if value.endswith("ł"):
        return "male"
    return ""

TITLE_WORDS = (
    "europoseł", "europosłanka", "poseł", "posłanka", "senator", "senatorka", "minister", "ministra",
    "wiceminister", "wiceministra", "rzecznik", "rzeczniczka", "prokurator", "prokuratorka", "premier",
    "prezydent", "przewodniczący", "przewodnicząca", "wiceprzewodniczący", "wiceprzewodnicząca",
    "szef", "szefowa", "ekspert", "ekspertka", "profesor", "doktor", "sędzia", "sędzina",
    "reporter", "reporterka", "dziennikarz", "dziennikarka", "redaktor", "redaktorka",
    "zastępca", "zastępczyni", "zastępcy", "prokuratora", "pan", "pani",
    "przedstawiciel", "przedstawicielka", "marszałek", "wicemarszałek", "lider", "liderka",
    "reprezentant", "reprezentantka", "prezes", "prezeska", "wiceprezes", "wiceprezeska",
    "wicepremier", "wicepremiera",
)
TITLE_RE = re.compile(r"^(?:" + "|".join(TITLE_WORDS) + r")\s+", re.I)
TITLE_TOKEN_RE = re.compile(r"\b(?:" + "|".join(TITLE_WORDS) + r")\b", re.I)

CAP_TOKEN = r"[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż’\'-]+"
PERSON_END_RE = re.compile(rf"(?P<subject>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,2}})\s*$")
PERSON_START_RE = re.compile(rf"^(?P<subject>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,2}})\b")
COLON_RE = re.compile(rf"\b(?P<subject>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,2}})\s*:\s*(?P<claim>[^\n]{{4,320}})")

KNOWN_INSTITUTION_FORMS: List[str] = []
for _spec in ENTITY_SPECS:
    if _spec.get("type") == "institution":
        KNOWN_INSTITUTION_FORMS.extend([str(_spec.get("canonical") or ""), *[str(x) for x in _spec.get("aliases", ())]])
KNOWN_INSTITUTION_FORMS = sorted({x for x in KNOWN_INSTITUTION_FORMS if x}, key=len, reverse=True)
KNOWN_INSTITUTION_ALT = "|".join(re.escape(x) for x in KNOWN_INSTITUTION_FORMS)

INSTITUTION_CORE = (
    rf"(?:(?:{KNOWN_INSTITUTION_ALT})|komisja(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){{0,7}}|"
    r"sąd(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,6}|"
    r"prokuratura(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,6}|"
    r"ministerstwo(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,6}|"
    r"fundusz(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,7}|"
    r"stowarzyszenie(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,7}|"
    r"stowarzyszenia(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,7}|"
    r"trybunał(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,6}|"
    r"sejm|senat|rząd|resort|policja|rada(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,5}|poczta(?:\s+[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż-]+){0,3}|ABW|CBA|NIK|TK|Citizen\s+Lab)"
)
INSTITUTION_END_RE = re.compile(rf"(?<!\w)(?P<subject>{INSTITUTION_CORE})\s*$", re.I)
INSTITUTION_START_RE = re.compile(rf"^(?P<subject>{INSTITUTION_CORE})\b", re.I)

# Ogólna bramka instytucjonalna. Nie opiera się na konkretnych nazwach własnych,
# tylko na głowie frazy nominalnej. Chroni m.in. metonimie urzędowe typu
# „Pałac Elizejski przekazał” i rozbudowane nazwy typu „Centralna Prokuratura
# Śledcza poinformowała”, które nie mogą być rejestrowane jako osoby.
INSTITUTION_HEAD_RE = re.compile(
    r"\b(?:pałac\w*|prokuratur\w*|biur\w*|kancelari\w*|sąd\w*|trybunał\w*|komisj\w*|ministerstw\w*|"
    r"urzęd\w*|urząd\w*|agencj\w*|fundusz\w*|stowarzysz\w*|fundacj\w*|związk\w*|rząd\w*|sejm\w*|senat\w*|policj\w*|izb\w*|resort\w*|"
    r"rad(?:a|y|zie|ę|ą|ami|ach|om)|poczt\w*|firm\w*|spółk\w*)\b",
    re.I,
)


def _looks_institution_phrase(value: Any) -> bool:
    raw = _clean(value).strip(" ,:;–—-\"„”'")
    if not raw:
        return False
    if INSTITUTION_HEAD_RE.search(raw) or ORGANIZATION_SUFFIX_RE.search(raw):
        return True
    low = raw.casefold()
    # Złożone nazwy organizacyjne, które nie mają polskiej głowy typu „urząd”.
    return low in {"poczta polska", "rady ministrów", "rada ministrów", "amber gold"}

MEDIA_FORMS: List[str] = []
for _spec in ENTITY_SPECS:
    if _spec.get("type") == "medium":
        MEDIA_FORMS.extend([str(_spec.get("canonical") or ""), *[str(x) for x in _spec.get("aliases", ())]])
MEDIA_FORMS = sorted({x for x in MEDIA_FORMS if x}, key=len, reverse=True)
MEDIA_ALT = "|".join(re.escape(x) for x in MEDIA_FORMS)
MEDIA_END_RE = re.compile(rf"(?P<subject>(?:{MEDIA_ALT}|GW))\s*$", re.I)
MEDIA_START_RE = re.compile(rf"^(?P<subject>(?:{MEDIA_ALT}|GW))\b", re.I)

# Partie i komitety mogą być jawnym instytucjonalnym nadawcą wypowiedzi
# („PiS twierdzi…”, „KO poinformowała…”). To nie zmienia afiliacji osoby w
# mówcę: kandydat partyjny jest używany tylko wtedy, gdy stoi w pozycji
# gramatycznego podmiotu przy czasowniku raportującym.
PARTY_FORMS: List[str] = []
for _spec in ENTITY_SPECS:
    if _spec.get("type") == "party":
        PARTY_FORMS.extend([str(_spec.get("canonical") or ""), *[str(x) for x in _spec.get("aliases", ())]])
PARTY_FORMS = sorted({x for x in PARTY_FORMS if x}, key=len, reverse=True)
PARTY_ALT = "|".join(re.escape(x) for x in PARTY_FORMS)
PARTY_END_RE = re.compile(rf"(?P<subject>(?:{PARTY_ALT}))\s*$", re.I)
PARTY_START_RE = re.compile(rf"^(?P<subject>(?:{PARTY_ALT}))\b", re.I)

PRODUCT_FORMS: List[str] = []
for _spec in ENTITY_SPECS:
    if _spec.get("type") == "product":
        PRODUCT_FORMS.extend([str(_spec.get("canonical") or ""), *[str(x) for x in _spec.get("aliases", ())]])
PRODUCT_FORMS = sorted({x for x in PRODUCT_FORMS if x}, key=len, reverse=True)
PRODUCT_START_RE = re.compile(r"^(?:" + "|".join(re.escape(x) + r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]*" for x in PRODUCT_FORMS) + r")\b", re.I) if PRODUCT_FORMS else re.compile(r"a^")
ORGANIZATION_SUFFIX_RE = re.compile(r"\b(?:Holding|Group|Lab|Laboratory|International|Foundation|Association|Institute)$", re.I)
ROLE_ONLY_NAME_RE = re.compile(r"^(?:marszałek|wicemarszałek|lider|liderka|prezydent|premier|minister|wiceminister|przewodniczący|przewodnicząca|szef|szefowa|rzecznik|rzeczniczka)(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż’\'-]+){0,4}$", re.I)

BAD_NAME_FIRST = {
    "Ostatecznie", "Wcześniej", "Następnie", "Według", "Reporterka", "Reporter", "Pytany", "Pytana",
    "Jak", "Po", "Przed", "Gdy", "Kiedy", "Jednocześnie", "Natomiast", "Komisja", "Sąd", "Sejm",
    "Senat", "Rząd", "Policja", "Trybunał", "Prokuratura", "Źródło", "Fundusz", "Funduszu", "Ministerstwo", "Koalicji", "Prawa", "Gazety", "Gazecie", "Wyborcza", "Wyborczej",
    "Platformy", "Obywatelskiej", "Unii", "Europejskiej", "Belkę", "Europie", "Europa", "Zachodniej",
    "Pan", "Pani", "Przedstawiciel", "Przedstawicielka", "Nowej", "Lewicy",
    "Mecenas", "Minister", "Wiceminister", "Premier", "Prezydent", "Rzecznik",
    "Prokurator", "Poseł", "Posłanka", "Senator", "Senatorka", "Prezes", "Szef", "Szefowa",
    "Prawnik", "Profesor", "Ekspert", "Ekspertka", "Przewodniczący", "Przewodnicząca",
    "Sopotu", "Stanach", "Zjednoczonych", "Skarbu", "Centralna", "Pałac",
    "Wicemarszałek", "Marszałek", "Lider", "Security", "Amnesty", "Poczta", "Rada", "Rady",
    "Pakt", "Paktu", "Amber", "Stowarzyszenie", "Stowarzyszenia", "Fundacja", "Fundacji",
}
META_RE = re.compile(
    r"\b(?:CZYTAJ|ZOBACZ|DOWIEDZ|TAGI|PODZIEL SIĘ|LINK SKOPIOWANY|ŹRÓDŁO ZDJĘCIA|AUTORKA?/AUTOR)\b",
    re.I,
)
TARGET_PREP_RE = re.compile(
    r"\b(?:o|wobec|przeciwko|na temat|w sprawie|dotycząc(?:y|a|e)|odnośnie)\s+"
    r"(?P<target>[A-ZĄĆĘŁŃÓŚŹŻ][^,.;:!?]{1,100})",
    re.I,
)
BEHAVIOR_TARGET_RE = re.compile(rf"\b(?:zachowanie|postępowanie|działania?)\s+(?P<target>{CAP_TOKEN}\s+{CAP_TOKEN})\b", re.I)
ATTRIBUTION_PREFIX_RE = re.compile(
    r"^(?P<marker>w\s+ocenie|w\s+opinii|zdaniem|według|wg)\s+(?P<body>.+)$",
    re.I,
)
ATTRIBUTION_SIGNAL_RE = re.compile(
    r"\b(?:w\s+ocenie|w\s+opinii|zdaniem|według|wg|powiedzia[łł]|stwierdzi[łł]|oceni[łł]|"
    r"mówi[łł]|pisze|twierdzi|podaje|opisuje|poinformowa[łł])\b",
    re.I,
)

ROLE_ONLY_ATTRIBUTION_RE = re.compile(
    r"^(?P<marker>w\s+ocenie|w\s+opinii|zdaniem|według|wg)\s+"
    r"(?P<title>(?:zastępcy?|prokuratora?|ministra?|premiera?|prezydenta?|rzecznika?|szefa?|"
    r"posła|posłanki|senatora|senatorki)"
    r"(?:\s+(?:Koalicji\s+Obywatelskiej|Platformy\s+Obywatelskiej|Nowej\s+Lewicy|"
    r"Polski\s+2050|KO|PiS|PSL|Konfederacji|Lewicy|[a-ząćęłńóśźż-]+)){0,5})\s+(?P<claim>.+)$",
    re.I,
)
PRONOUN_ATTRIBUTION_RE = re.compile(
    r"^(?P<marker>w\s+(?:jego|jej)\s+ocenie|jego\s+zdaniem|jej\s+zdaniem)\s+(?P<claim>.+)$",
    re.I,
)
ANAPHORIC_END_RE = re.compile(
    r"^(?P<claim>.+?)\s*[-–—]\s*(?P<action>"
    + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))
    + r")\s*[.!?]*$",
    re.I,
)
ANAPHORIC_JAK_RE = re.compile(
    r"^jak\s+(?P<action>"
    + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))
    + r")\s*[,;:]\s*(?P<claim>.+)$",
    re.I,
)
# Current: jawna konstrukcja „Jak komentował Kwiatkowski, ...” ma własnego
# mówcę w tym samym zdaniu. Nie jest anaforą do poprzedniej osoby.
JAK_NAMED_ATTRIBUTION_RE = re.compile(
    rf"^jak\s+(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})"
    rf"\s+(?P<speaker>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,2}})\s*[,;:]\s*(?P<claim>.+)$",
    re.I,
)

# Kontynuacje mówcy nie mogą szukać nowej osoby w późniejszym dopowiedzeniu.
# Przykład: „... jest na — mówiła nawiązując do ... Marcina Romanowskiego”.
ANAPHORIC_TRAILING_RE = re.compile(
    r"^(?P<claim>.+?)\s*[-–—]\s*(?P<action>"
    + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))
    + r")"
    + r"(?:\s+(?:poseł|posłanka|senator|senatorka|minister|premier|prezydent|rzecznik|prokurator)"
      r"(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż.-]{1,30}){0,3})?"
    + r"\s*,?(?:\s+(?:dalej|następnie|również|też|nawiązując|odnosząc|zwracając|oceniając|dodając)\b.*)?[.!?]*$",
    re.I,
)
ROLE_CONTINUATION_RE = re.compile(
    r"^(?:przedstawiciel(?:ka)?|posłanka?|senator(?:ka)?|wiceprzewodnicząc(?:a|y)|marszałek|wicemarszałek|lider(?:ka)?|prezydent)"
    r"(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+){1,4}\s+"
    r"(?P<action>" + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True)) + r")\b(?P<claim>.*)$",
    re.I,
)

ROLE_ACTION_CONTINUATION_RE = re.compile(
    r"^(?P<title>minister|wiceminister|premier|prezydent|rzecznik|prokurator|mecenas|europoseł|poseł|posłanka|senator|senatorka|prezes|przewodniczący|przewodnicząca|profesor|prawnik|ekspert|ekspertka|marszałek|wicemarszałek|lider|liderka|szef(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ]{2,8})?)"
    r"(?:\s+(?:KO|PiS|PSL|Lewicy|Konfederacji|Polski\s+2050|Nowej\s+Lewicy|Koalicji\s+Obywatelskiej|Platformy\s+Obywatelskiej))?"
    r"(?:\s+(?:Sejmu|Senatu|Sopotu|komisji|rządu|partii))?\s+"
    r"(?:(?:Stowarzyszen\w*|Fundacj\w*|Związk\w*)(?:\s+(?:[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+|[\"„][^\"”]{1,80}[\"”])){0,5}\s+)?"
    r"(?P<action>" + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True)) + r")\b(?P<claim>.*)$",
    re.I,
)

ROLE_PASSIVE_ACTION_CONTINUATION_RE = re.compile(
    r"^(?P<title>przewodniczący|przewodnicząca|minister|wiceminister|premier|prezydent|rzecznik|prokurator|profesor|prawnik|ekspert|ekspertka|marszałek|wicemarszałek|lider|liderka)\b"
    r"(?P<middle>.{0,320}?\b(?:pytany|pytana|zapytany|zapytana|proszony|proszona)\b.{0,260}?)"
    r"(?P<action>" + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True)) + r")\b(?P<claim>.*)$",
    re.I,
)

BARE_PASSIVE_ACTION_CONTINUATION_RE = re.compile(
    r"^(?:pytany|pytana|zapytany|zapytana|proszony|proszona)\b(?P<middle>.{0,420}?)"
    r"(?P<action>" + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True)) + r")\b(?P<claim>.*)$",
    re.I,
)

# Current: jawny podpis po cytacie może zawierać program, medium, funkcję i afiliację
# przed imieniem i nazwiskiem. Ten wzorzec ma pierwszeństwo przed ogólnym skanem.
QUOTE_ROLE_PERSON_RE = re.compile(
    rf"^(?P<claim>.+?)\s*[-–—]\s*(?P<action>(?i:{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))}))"
    rf"(?P<context>.{{0,180}}?)(?P<speaker>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)"
    rf"(?:\s+(?i:z|ze)\s+(?:(?i:portalu|serwisu|redakcji|telewizji|radia)\s+)?{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,3}})?"
    r"(?:[,.;:!?]|$)",
)
SURNAME_ATTRIBUTION_RE = re.compile(
    rf"^(?P<marker>w\s+ocenie|w\s+opinii|zdaniem|według|wg)\s+(?P<surname>{CAP_TOKEN})\s+(?P<claim>.+)$",
    re.I,
)

# Current: jawne nazwisko w nagłówku cytatu i nazwisko po czasowniku
# raportującym są atrybucją tylko wtedy, gdy można je jednoznacznie rozwinąć
# z aliasów bieżącego dokumentu.
SURNAME_COLON_RE = re.compile(rf"^(?P<surname>{CAP_TOKEN})\s*:\s*(?P<claim>.+)$", re.I)
TRAILING_NAMED_SPEAKER_RE = re.compile(
    rf"^(?P<claim>.+?)\s*[-–—]\s*(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})"
    rf"(?:\s+(?:z\s+kolei|także|też|natomiast))?"
    rf"(?:\s+(?:poseł|posłanka|senator|senatorka|minister|premier|prezydent|rzecznik|prokurator|mecenas))?"
    rf"\s+(?P<surname>{CAP_TOKEN})(?:\s*,?\s*(?:zabierając|nawiązując|odnosząc|dodając|komentując|wyjaśniając)\b.*)?[.!?]*$",
    re.I,
)
PASSIVE_INTERVIEW_CONTEXT_RE = re.compile(
    rf"^(?P<speaker>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s+"
    r"(?:był|była)\s+(?:pytany|pytana|proszony|proszona)\b(?P<claim>.*)$", re.I,
)
SPEAKER_CONTEXT_INTRO_RE = re.compile(
    rf"^(?:Jako\s+(?:pierwszy|pierwsza)\s+)?(?:głos\s+zabrał(?:a)?|wypowiadał(?:a)?\s+się|"
    rf"na\s+pytania\s+odpowiadał(?:a)?|przemawiał(?:a)?)\s+(?P<speaker>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)(?:[,.]|$)",
    re.I,
)
ROLE_DESCRIPTOR_END_RE = re.compile(
    r"^(?P<claim>.+?)\s*[-–—]\s*(?P<action>"
    + "|".join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))
    + r")\s+(?P<descriptor>(?:były|była|obecny|obecna)?\s*(?:dyrektor|szef|szefowa|minister|premier|prezydent|rzecznik|rzeczniczka|gość|gosc|europoseł|poseł|posłanka|senator|senatorka|prokurator|reporter|reporterka)(?:\s+[^,.;:!?]{0,70})?)[.!?]*$",
    re.I,
)
CITIZEN_LAB_SOURCE_RE = re.compile(
    r"^(?:według\s+(?:informacji|analizy)\s+[^.]{0,180}?\b(?:przez|grupy)\s+)?(?P<source>Citizen\s+Lab)\b(?P<claim>.+)$",
    re.I,
)


def _blocks(text: str) -> List[Tuple[str, int, int, List[str]]]:
    blocks: List[Tuple[str, int, int, List[str]]] = []
    for block in analyzable_blocks(text):
        sentences = [_clean(item.get("text")) for item in block if _clean(item.get("text"))]
        if not sentences:
            continue
        document_id = _clean(block[0].get("document_id"))
        document_index = int(block[0].get("document_index") or 0)
        block_index = int(block[0].get("block_index") or 0)
        blocks.append((document_id, document_index, block_index, sentences))
    return blocks


def _blocks_from_segments(segments: List[Dict[str, Any]]) -> List[Tuple[str, int, int, List[str]]]:
    """Buduje bloki z segmentów już utworzonych przez PipelineContext.

    To jest kanoniczna ścieżka dla pełnego pipeline: resolver nie segmentuje
    tekstu drugi raz i przez to nie może wygenerować innego ``document_id``.
    """
    grouped: Dict[Tuple[str, int, int], List[Tuple[int, str]]] = {}
    for item in segments or []:
        if not bool(item.get("analyzable")):
            continue
        text = _clean(item.get("text"))
        doc_id = _clean(item.get("document_id"))
        if not text or not doc_id:
            continue
        doc_index = int(item.get("document_index") or 0)
        block_index = int(item.get("block_index") or 0)
        segment_index = int(item.get("segment_index") or 0)
        grouped.setdefault((doc_id, doc_index, block_index), []).append((segment_index, text))
    out: List[Tuple[str, int, int, List[str]]] = []
    for (doc_id, doc_index, block_index), rows in sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        sentences = [text for _idx, text in sorted(rows)]
        if sentences:
            out.append((doc_id, doc_index, block_index, sentences))
    return out


def _normalize_person(raw: str) -> str:
    # Current: jedyna morfologia osoby żyje w EntityRegistry. Resolver tylko
    # przygotowuje powierzchnię i deleguje canonicalizację.
    value = TITLE_RE.sub("", _clean(raw)).strip(" ,:;–—-\"„”'")
    return normalize_person_surface(value)


def _person_aliases(text: str) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    clean_text = _clean(text)
    # Nazwa medium nie może wejść do nakładającego się okna imię/nazwisko.
    # Maskujemy ją przed budową aliasów, zachowując resztę dokumentu, np.
    # ``w Radiu ZET Żurek`` oraz ``Interii Bochenek``.
    for form in MEDIA_FORMS:
        clean_text = re.sub(rf"(?<!\w){re.escape(form)}(?!\w)", " ", clean_text, flags=re.I)
    clean_text = _clean(clean_text)
    known_given = {
        str(x).casefold() for x in COMMON_GIVEN_NAMES
    } | set(PERSON_TOKEN_NOMINATIVE) | {
        str(x).casefold() for x in PERSON_TOKEN_NOMINATIVE.values()
    }

    def register(person_raw: str, *, prefer_longer: bool = False) -> None:
        person = _valid_person_candidate(person_raw)
        if not person:
            return
        parts = person.split()
        # Nakładające się okno może skleić obiekt z następującą po nim osobą,
        # np. „Wosia Przemysław Nowak”. Jeżeli drugi token jest znanym imieniem,
        # a pierwszy nim nie jest, osobą jest końcowa para.
        if len(parts) == 3 and parts[0].casefold() not in known_given and parts[1].casefold() in known_given:
            person = _valid_person_candidate(" ".join(parts[-2:]))
            parts = person.split() if person else []
        if len(parts) < 2:
            return
        first = parts[0]
        if first in BAD_NAME_FIRST or first.isupper():
            return
        surname_key = parts[-1].casefold()
        current = aliases.get(surname_key, "")
        if not current or (prefer_longer and len(parts) > len(current.split())):
            aliases[surname_key] = person
        aliases.setdefault(person.casefold(), person)
        # Dla nazw 3-członowych typu Jan Maria Jackowski / Jan Krzysztof
        # Ardanowski pełny span ma pierwszeństwo nad nakładającą się parą
        # „Maria Jackowski”.
        if len(parts) == 3:
            prefix_key = " ".join(parts[:2]).casefold()
            if not aliases.get(prefix_key) or len(person.split()) > len(aliases[prefix_key].split()):
                aliases[prefix_key] = person

    # Najpierw pełne 3-tokenowe nazwiska z rozpoznawalnym imieniem. Dzięki temu
    # późniejsze nakładające się pary nie skracają „Jan Maria Jackowski” do
    # „Maria Jackowski”.
    for match in re.finditer(rf"(?=(\b{CAP_TOKEN}\s+{CAP_TOKEN}\s+{CAP_TOKEN}\b))", clean_text):
        raw = match.group(1)
        first = _normalize_person(raw).split()[0].casefold() if _normalize_person(raw) else ""
        if first in known_given:
            register(raw, prefer_longer=True)

    # Następnie pary Imię Nazwisko. Pary zaczynające się produktem, rolą,
    # instytucją lub organizacją odpadają w _valid_person_candidate.
    for match in re.finditer(rf"(?=(\b{CAP_TOKEN}\s+{CAP_TOKEN}\b))", clean_text):
        register(match.group(1))

    # Redakcyjne wtrącenie może rozdzielić pełne nazwisko:
    # ``(…, Jan Krzysztof - red.) Ardanowski``.
    for match in re.finditer(
        rf"\([^)]*?\b(?P<given>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{1,2}})\s*[-–—]\s*red\.?(?:[^)]*)\)\s*(?P<surname>{CAP_TOKEN})",
        clean_text,
        re.I,
    ):
        register(f"{match.group('given')} {match.group('surname')}", prefer_longer=True)

    # Ostatni przebieg zachowuje dotychczasowe wsparcie dla nazw 2/3-tokenowych,
    # ale nie może nadpisać lepszego pełnego aliasu gorszą frazą strukturalną.
    for raw in re.findall(rf"\b({CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\b", clean_text):
        if len(raw.split()) == 3 and re.search(rf"\bdo\s+spraw\s+{re.escape(raw)}\b", clean_text, re.I):
            raw = " ".join(raw.split()[-2:])
        register(raw, prefer_longer=len(raw.split()) == 3)
    return aliases

def _expand_person_alias(value: str, aliases: Dict[str, str]) -> str:
    clean = _normalize_person(value)
    if not clean:
        return clean
    direct = aliases.get(clean.casefold())
    if direct:
        return direct
    parts = clean.split()
    if len(parts) == 1:
        return aliases.get(parts[0].casefold(), clean)

    # Nie publikuj urwanego ``Jan Krzysztof`` jeżeli w dokumencie występuje
    # jednoznaczne ``Jan Krzysztof Ardanowski``.
    prefix_matches = {full for key, full in aliases.items() if full.casefold().startswith(clean.casefold() + " ")}
    if len(prefix_matches) == 1:
        return next(iter(prefix_matches))

    surname = parts[-1].casefold()
    stem = surname[: max(4, len(surname) - 3)]
    matches = [full for key, full in aliases.items() if key != surname and stem and stem in key]
    return matches[0] if len(set(matches)) == 1 else clean


def _known_medium(value: str) -> str:
    raw = _clean(value).strip("\"„”'")
    if raw.casefold() == "gw":
        return "Gazeta Wyborcza"
    for form in MEDIA_FORMS:
        if raw.casefold() == form.casefold():
            return form
    return ""


def _reporting_medium_after_verb(suffix: str) -> str:
    """Znajdź jawne medium po czasowniku źródłowym, zanim powstanie fałszywy mówca.

    Obsługuje m.in. „... - napisała w piątek Gazeta Wyborcza”. W takim
    układzie osoba wspomniana przed czasownikiem jest obiektem opisywanego
    zdarzenia, nie autorem aktu „napisała”.
    """
    local = _clean(suffix)[:140]
    for form in MEDIA_FORMS:
        match = re.search(rf"(?<!\w){re.escape(form)}(?!\w)", local, re.I)
        if match and match.start() <= 90:
            return _known_medium(form) or form
    if re.search(r"(?<!\w)GW(?!\w)", local, re.I):
        return "Gazeta Wyborcza"
    return ""


def _subject_kind(value: str) -> Tuple[str, str]:
    raw = _clean(value).strip(" ,:;–—-\"„”'")
    medium = _known_medium(raw)
    if medium:
        return medium, "medium"
    if INSTITUTION_START_RE.match(raw) or _looks_institution_phrase(raw):
        return raw, "institution"
    pm = PARTY_START_RE.match(raw)
    if pm:
        return _clean(pm.group("subject")), "party"
    person = _valid_person_candidate(raw)
    if person:
        return person, "person"
    return "", ""


def _capital_name_candidates(text: str) -> List[Tuple[int, str]]:
    """Zwraca nakładające się dwu- i trzytokenowe kandydatury nazw osobowych.

    Dawny regex konsumował ``Platformy Obywatelskiej Bartosz`` i nie widział już
    poprawnego, nakładającego się ``Bartosz Arłukowicz``.
    """
    rows: List[Tuple[int, str]] = []
    for count in (3, 2):
        pattern = rf"(?=(\b{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{{count-1}}}\b))"
        for match in re.finditer(pattern, text):
            rows.append((match.start(1), match.group(1)))
    rows.sort(key=lambda row: (row[0], -len(row[1])))
    return rows


def _named_person_in_signature(text: str) -> str:
    """Znajdź jawne Imię Nazwisko w podpisie rola/afiliacja + osoba.

    Używane po czasowniku raportującym, np. ``powiedział wicemarszałek
    Sejmu Włodzimierz Czarzasty`` lub ``mówił ... poseł KO Robert
    Kropiwnicki``. Sama rola bez nazwiska nigdy nie staje się mówcą.
    """
    # Przecinek może oddzielać kolejne funkcje tej samej osoby:
    # ``skomentował wicepremier, minister ... Radosław Sikorski``. Kończymy
    # dopiero przed treścią wypowiedzi (że/iż/czy) lub końcem zdania.
    signature = re.split(r"\b(?:że|iż|czy|bo|gdy|kiedy|aby|żeby)\b", _clean(text), maxsplit=1, flags=re.I)[0]
    signature = re.split(r"[;!?]", signature, maxsplit=1)[0][:240]
    if not TITLE_TOKEN_RE.search(signature):
        return ""
    known_given = {str(x).casefold() for x in COMMON_GIVEN_NAMES} | {
        str(x).casefold() for x in PERSON_TOKEN_NOMINATIVE.values()
    }
    people: List[Tuple[int, str]] = []
    for pos, raw in _capital_name_candidates(signature):
        person = _valid_person_candidate(raw)
        # W podpisie mogą wystąpić nazwy programu, partii i obiektu wypowiedzi.
        # Imię jest tutaj obowiązkowym dowodem osoby; sama para wielkich liter
        # (np. „Koalicja Obywatelska” albo „Wosia Przemysław”) nie wystarcza.
        if person and len(person.split()) >= 2 and person.split()[0].casefold() in known_given:
            people.append((pos, person))
    if not people:
        return ""
    # Podpis jest zwykle zakończony nazwiskiem; ostatnia wiarygodna osoba ma
    # pierwszeństwo przed nazwami partii/urzędów występującymi po funkcji.
    # Preferujemy najpóźniej zaczynającą się osobę, a przy tym samym początku
    # pełny trzyczęściowy zapis (Anna Maria Żukowska) zamiast jego podokna.
    # Dla nakładających się okien ``Anna Maria Żukowska`` i ``Maria
    # Żukowska`` oba spany kończą się w tym samym miejscu. Najpierw wybieramy
    # najpóźniejszy koniec podpisu, a przy remisie pełniejszą nazwę.
    people.sort(key=lambda row: (row[0] + len(row[1]), len(row[1].split()), row[0]))
    return people[-1][1]


def _valid_person_candidate(raw: str) -> str:
    person = _normalize_person(raw)
    if not person or len(person.split()) < 2:
        return ""
    tokens = person.split()
    if (
        tokens[0] in BAD_NAME_FIRST
        or INSTITUTION_START_RE.match(person)
        or PRODUCT_START_RE.match(person)
        or _looks_institution_phrase(person)
        or ROLE_ONLY_NAME_RE.match(person)
    ):
        return ""
    # Centralna bramka semantyczna osoby. Dzięki niej nazwa firmy/medium/roli
    # nie przechodzi jako PERSON tylko dlatego, że składa się z wielkich liter.
    verdict = validate_entity_candidate(person, "person")
    if not verdict.accepted:
        return ""
    # Current: czasownik raportujący nie może być drugim członem nazwiska.
    # To zatrzymuje artefakty korpusu typu „KPRM Zaznaczył”.
    action_tokens = {x.casefold() for x in ACTION_FORMS}
    if any(token.casefold().strip(".,:;!?–—-") in action_tokens for token in tokens):
        return ""
    return verdict.cleaned


def _last_full_person(text: str) -> str:
    local = _subject_scan_text(_clean(text)[-320:])
    for form in MEDIA_FORMS:
        local = re.sub(rf"(?<!\w){re.escape(form)}(?!\w)", " ", local, flags=re.I)

    # Gdy bezpośrednio przed czasownikiem stoi jawne Imię Nazwisko, preferujemy
    # tę końcową parę nad przypadkowym trójelementowym ciągiem z nazwą tematu,
    # np. „do spraw Pegasusa Przemysław Wipler relacjonował”.
    end_pair = re.search(rf"(?P<subject>{CAP_TOKEN}\s+{CAP_TOKEN})\s*$", local)
    if end_pair:
        person = _valid_person_candidate(end_pair.group("subject"))
        if person:
            return person

    for _pos, raw in reversed(_capital_name_candidates(local)):
        person = _valid_person_candidate(raw)
        if person:
            return person
    return ""


def _first_full_person(text: str) -> str:
    local = _subject_scan_text(_clean(text)[:360])
    for _pos, raw in _capital_name_candidates(local):
        person = _valid_person_candidate(raw)
        if person:
            return person
    return ""


def _relative_antecedent(prefix: str) -> str:
    matches = list(re.finditer(r"\b(?:który|która|którzy|które|którego|której)\b", prefix, re.I))
    if not matches:
        return ""
    rel = matches[-1]
    return _last_full_person(prefix[:rel.start()])


def _subject_before(prefix: str) -> Tuple[str, str]:
    # Jawna osoba na początku zdania z dopowiedzeniem funkcji/afiliacji pozostaje
    # podmiotem czasownika po zamykającym przecinku, np.
    # „Piotr Zgorzelski, wicemarszałek Sejmu z PSL-Trzeciej Drogi, mówił…”.
    # Nie wybieramy najbliższej kapitalizowanej frazy z dopowiedzenia.
    leading_appositive = re.match(
        rf"^\s*(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s*,\s*"
        r"(?P<appositive>[^.!?]{2,220})\s*,\s*$",
        prefix,
    )
    if leading_appositive:
        person = _valid_person_candidate(leading_appositive.group("person"))
        appositive = leading_appositive.group("appositive")
        if person and (TITLE_TOKEN_RE.search(appositive) or PARTY_START_RE.search(appositive) or re.search(r"\b(?:z|ze)\s+(?:PSL|PiS|KO|Konfederacj\w*|Lewic\w*|Koalicj\w*|Platform\w*)", appositive, re.I)):
            return person, "person"

    # Sama funkcja/rola bez nazwanej osoby nie jest encją-mówcą.
    # ``senator KO``, ``przedstawicielka Nowej Lewicy`` czy ``marszałek Sejmu``
    # pozostają nierozwiązane; nie wolno zastępować ich partią/instytucją.
    role_only_prefix = _clean(prefix).strip(" ,:;–—-\"„”'")
    if TITLE_TOKEN_RE.search(role_only_prefix) and not _named_person_in_signature(role_only_prefix):
        if re.match(r"^(?:jak\s+)?(?:pan\s+|pani\s+)?(?:przedstawiciel(?:ka)?|poseł|posłanka|senator|senatorka|marszałek|wicemarszałek|lider|liderka|szef|szefowa|prezes|prezeska|premier|prezydent|minister|wiceminister|przewodniczący|przewodnicząca)\b", role_only_prefix, re.I):
            return "", ""

    # Current: w konstrukcji „Krzysztof Kwiatkowski, mówiąc o ... Funduszu
    # Sprawiedliwości, przypomniał ...” podmiotem zdania głównego jest osoba
    # przed wtrąceniem imiesłowowym. Instytucja z dopełnienia nie może jej
    # przejąć tylko dlatego, że stoi bliżej czasownika.
    leading_participial = re.match(
        rf"^\s*(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s*,\s*"
        r"(?:mówiąc|komentując|odnosząc\s+się|nawiązując|przypominając|opisując|pytając|wyjaśniając)\b",
        prefix,
        re.I,
    )
    if leading_participial:
        person = _valid_person_candidate(leading_participial.group("person"))
        if person:
            return person, "person"

    # Jeśli zdanie zaczyna się samą rolą („Przewodnicząca komisji pytana ...
    # odpowiedziała”), osoba wspomniana wewnątrz pytania nie może zostać
    # uznana za podmiot. Osobę może dostarczyć wyłącznie bezpieczny kontekst
    # roli z tego samego bloku; bez niego pozostawiamy mówcę nierozwiązanego.
    if re.match(
        r"^\s*(?:przewodnicząca|przewodniczący|minister|wiceminister|premier|prezydent|rzecznik|prokurator|profesor|prawnik|ekspert|ekspertka)\b"
        r".{0,320}?\b(?:pytana|pytany|zapytana|zapytany|proszona|proszony)\b",
        prefix, re.I,
    ):
        return "", ""

    # Konstrukcje bierne/parentetyczne: „Joanna Kluzik-Rostkowska pytana,
    # czy ... Sławomira Mentzena, odpowiedziała ...”. Najbliższa nazwa przed
    # czasownikiem jest tu obiektem pytania, nie podmiotem „odpowiedziała”.
    leading_passive = re.match(
        rf"^\s*(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s+"
        r"(?:pytan[ay]|zapytan[ay]|proszon[ay]|poproszon[ay]|pytany\s+o|pytana\s+o)\b",
        prefix, re.I,
    )
    if leading_passive:
        person = _valid_person_candidate(leading_passive.group("person"))
        if person:
            return person, "person"

    # Sama forma „Pytana/Pytany, dlaczego X..., odpowiedziała/odpowiedział”
    # nie niesie nowego nazwanego podmiotu. Nazwy w treści pytania są obiektami;
    # mówcę może dostarczyć wyłącznie bezpieczny kontekst tego samego bloku.
    if re.match(r"^\s*(?:pytany|pytana|zapytany|zapytana|proszony|proszona)\b", prefix, re.I):
        return "", ""

    # Funkcja/urząd może poprzedzać pełne nazwisko i zawierać nazwę kraju lub
    # instytucji: ``prezydent Bułgarii Rumen Radew poinformował``. Wymagamy
    # jawnego tytułu oraz pełnego imienia i nazwiska; osoby z treści pytania
    # zostały odcięte przez powyższe blokady bierne.
    titled_person = _named_person_in_signature(prefix)
    if titled_person:
        return titled_person, "person"

    # Deskryptor roli w klauzie głównej może wracać do osoby nazwanej chwilę
    # wcześniej: „... Magdalena Sroka ..., przewodnicząca komisji powiedziała”.
    # Bierzemy ostatnią pełną osobę *przed* deskryptorem, nie wcześniejszego
    # mówcę z podrzędnej klauzy („Arleta Zalewska przypomniała, że ...”).
    role_matches = list(re.finditer(
        r"(?:^|[,;])\s*(?:pani\s+|pan\s+)?(?:przewodnicząca|przewodniczący|"
        r"wiceministra|wiceminister|ministra|minister|rzeczniczka|rzecznik|"
        r"szefowa|szef|posłanka|poseł|europosłanka|europoseł)\b",
        prefix, re.I,
    ))
    if role_matches:
        person = _last_full_person(prefix[:role_matches[-1].start()])
        if person:
            return person, "person"

    # Current: osoba z afiliacją przed czasownikiem. Najbliższa kapitalizowana
    # fraza może być partią, ale mówcą pozostaje jawne Imię Nazwisko.
    affiliation_person = re.search(
        r"([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+\s+[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+)\s+z\s+(?:Polskiego Stronnictwa Ludowego|Koalicji Obywatelskiej|Platformy Obywatelskiej|Prawa i Sprawiedliwości|Nowej Lewicy|Suwerennej Polski)(?:[^.!?]{0,120})$",
        prefix, re.I,
    )
    if affiliation_person:
        return _clean(affiliation_person.group(1)), "person"

    # Osoba + afiliacja skrótowa (KO/PiS/PSL/...) nadal ma osobę jako
    # podmiot gramatyczny. Afiliacja nie może wygrać tylko dlatego, że stoi
    # bezpośrednio przed czasownikiem: ``Jan Kowalski z KO powiedział``.
    person_party = re.search(
        rf"(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s+"
        rf"(?:(?:z|ze)\s+|\(\s*)(?:{PARTY_ALT})(?:\s*\))?(?:[^.!?]{{0,45}})$",
        prefix, re.I,
    )
    if person_party:
        person = _valid_person_candidate(person_party.group("person"))
        if person:
            return person, "person"

    # Także konstrukcja ``poseł KO Jan Kowalski powiedział``: funkcja i partia
    # są opisem osoby, a nie konkurencyjnym mówcą.
    titled_party_person = re.search(
        rf"(?:{ '|'.join(TITLE_WORDS) })\s+(?:{PARTY_ALT})\s+(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)(?:[^.!?]{{0,30}})$",
        prefix, re.I,
    )
    if titled_party_person:
        person = _valid_person_candidate(titled_party_person.group("person"))
        if person:
            return person, "person"

    prefix = _subject_scan_text(prefix).strip(" ,:;–—-\"„”' ")

    # Pełna znana nazwa medium ma pierwszeństwo przed wzorcem
    # ``osoba + medium``. Inaczej alias ``Wyborcza`` rozcinał nazwę
    # ``Gazeta Wyborcza`` na fałszywą osobę ``Gazeta`` + medium.
    full_medium = MEDIA_END_RE.search(prefix)
    if full_medium and full_medium.start("subject") == 0:
        return _known_medium(full_medium.group("subject")) or _clean(full_medium.group("subject")), "medium"

    # Osoba występująca bezpośrednio przed nazwą medium pozostaje mówcą;
    # medium jest kontekstem publikacji, np. ``Wroński RMF FM powiedział``.
    person_before_medium = re.search(
        rf"(?P<person>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,2}})\s+(?:(?:z|dla)\s+)?(?:{MEDIA_ALT})\s*$",
        prefix, re.I,
    )
    if person_before_medium:
        raw_person = _normalize_person(person_before_medium.group("person"))
        if raw_person and raw_person.split()[0] not in BAD_NAME_FIRST:
            return raw_person, "person"
    media_person = re.search(
        rf"(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN})\s+z\s+(?:{MEDIA_ALT})(?:[^.!?]{{0,80}})$",
        prefix, re.I,
    )
    if media_person:
        person = _valid_person_candidate(media_person.group("person"))
        if person:
            return person, "person"
    # Najpierw znane medium jako pełny span (np. „Radio ZET”), zanim ogólny
    # wzorzec „radio X” spróbuje skrócić je do samego X.
    mm = MEDIA_END_RE.search(prefix)
    if mm:
        return _known_medium(mm.group("subject")) or _clean(mm.group("subject")), "medium"

    # Dynamiczna nazwa medium po deskryptorze: dziennik „Le Monde” napisał,
    # portal X podał. Deskryptor rozstrzyga typ; sama kapitalizacja nie tworzy osoby.
    dynamic_publication = re.search(
        rf"(?<!\w)(?:dziennik|gazeta|portal|serwis|radio|telewizja|tygodnik|miesięcznik)\s+"
        rf"[\"„]?(?P<subject>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,3}})[\"”]?\s*$",
        prefix, re.I,
    )
    if dynamic_publication:
        return _clean(dynamic_publication.group("subject")), "medium"
    generic_publication = re.search(r"(?<!\w)(?P<subject>dziennik|gazeta|redakcja)\s*$", prefix, re.I)
    if generic_publication:
        return _clean(generic_publication.group("subject")), "medium"
    im = INSTITUTION_END_RE.search(prefix)
    if im:
        return _clean(im.group("subject")), "institution"
    party = PARTY_END_RE.search(prefix)
    if party:
        return _clean(party.group("subject")), "party"

    # ``Firma OpenAI poinformowała`` / ``spółka Orlen podała``: deskryptor
    # rozstrzyga typ organizacyjny, a nie staje się częścią nazwy osoby.
    company = re.search(
        rf"\b(?:firma|spółka|koncern|grupa)\s+(?P<subject>{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{0,3}})\s*$",
        prefix, re.I,
    )
    if company:
        return _clean(company.group("subject")), "institution"

    # Dokument/raport konkretnej instytucji jest metonimicznym źródłem, ale
    # kanonem pozostaje instytucja (``Kontrola NIK wykazała`` -> NIK).
    document_source = re.search(
        rf"\b(?:kontrola|raport|analiza|badanie)\s+(?P<subject>(?:{KNOWN_INSTITUTION_ALT}))\s*$",
        prefix, re.I,
    )
    if document_source:
        return _clean(document_source.group("subject")), "institution"
    person = _last_full_person(prefix)
    if person:
        return person, "person"
    pm = PERSON_END_RE.search(prefix)
    if pm:
        person = _normalize_person(pm.group("subject"))
        if person and person.split()[0] not in BAD_NAME_FIRST:
            return person, "person"
    return "", ""


def _subject_after(suffix: str) -> Tuple[str, str]:
    """Zwraca tylko podmiot jawnie zaczynający podpis po czasowniku.

    Nie przeszukuje całego dopowiedzenia. Dzięki temu osoba wspomniana po
    „nawiązując do” nie zastępuje aktywnej mówczyni.
    """
    suffix = _clean(suffix).lstrip(" ,:;–—-")
    local = suffix[:280]

    # Dopełnienie po przyimku nie jest podmiotem czasownika raportującego.
    # Szczególnie groźna była konstrukcja „przekazała do prokuratora ...
    # Adama Bodnara”, w której odbiorca dokumentu przejmował rolę mówcy.
    if re.match(r"^(?:do|dla|wobec|przeciwko|od|u)\b", local, re.I):
        return "", ""
    mm = MEDIA_START_RE.match(local.strip("\"„”'"))
    if mm:
        return _known_medium(mm.group("subject")) or _clean(mm.group("subject")), "medium"

    # Podpis może zawierać przysłówki, funkcję, urząd/afiliację i dopiero
    # potem pełne nazwisko. Jawna osoba ma pierwszeństwo nad opisem roli.
    named_after_role = _named_person_in_signature(local)
    if named_after_role:
        return named_after_role, "person"

    # Sama rola po czasowniku bez nazwiska nie może zostać zamieniona na
    # instytucję/partię: ``powiedział marszałek Sejmu`` pozostaje nierozwiązane.
    role_signature = _clean(local).split(",", 1)[0].strip(" ,:;–—-\"„”'")
    if TITLE_TOKEN_RE.search(role_signature) and re.search(
        r"\b(?:poseł|posłanka|senator|senatorka|marszałek|wicemarszałek|lider|liderka|szef|szefowa|premier|prezydent|minister|wiceminister|przewodniczący|przewodnicząca|przedstawiciel|przedstawicielka)\b",
        role_signature, re.I,
    ):
        return "", ""

    # Jawna instytucja może stać bezpośrednio po czasowniku także małą literą,
    # np. „przekazało biuro prasowe warszawskiego sądu okręgowego”. Nie próbujemy
    # robić z końcowych wielkich liter osoby; bierzemy lokalną frazę instytucjonalną.
    described_institution = re.match(
        r"(?P<subject>(?:(?!(?:że|iż|jak|czy|bo|gdy|kiedy|aby|żeby|który|która)\b)"
        r"(?:[a-ząćęłńóśźż-]+|[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż-]+)\s+){0,3}"
        r"(?:prokuratura|biuro|kancelaria|sąd|trybunał|komisja|ministerstwo|urząd|agencja|fundusz|rząd|sejm|senat|policja|izba|resort|pałac)"
        r"(?:\s+[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż.-]+){0,6})",
        local, re.I,
    )
    if described_institution:
        subject = _clean(described_institution.group("subject")).rstrip(".,;:!?")
        head = INSTITUTION_HEAD_RE.search(subject)
        lead = subject[:head.start()] if head else ""
        # ``zapowiedział dalszą walkę o Trybunał i ostrzegł`` zawiera nazwę
        # instytucji w dopełnieniu, nie instytucjonalny podpis po czasowniku.
        object_lead = bool(re.search(r"\b(?:o|do|dla|wobec|przeciwko|od|z|ze|na|nad|pod)\b", lead, re.I))
        if _looks_institution_phrase(subject) and not object_lead and not ACTION_RE.search(subject):
            return subject, "institution"

    lower_institution = re.match(
        r"(?P<subject>(?:biuro(?:\s+prasowe)?|prokuratura|kancelaria|sąd|trybunał|komisja|"
        r"ministerstwo|urząd|agencja|fundusz|rząd|sejm|senat|policja|izba|resort)"
        r"(?:\s+[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż.-]+){0,7})",
        local, re.I,
    )
    if lower_institution:
        return _clean(lower_institution.group("subject")).rstrip(".,;:!?"), "institution"

    # Osoba może wystąpić bezpośrednio po kontrolowanej nazwie medium,
    # a następnie mieć afiliację: „w TVN24 Witold Zembaczyński z KO”.
    # Dopasowanie osoby jest celowo czułe na wielkość liter.
    for form in MEDIA_FORMS:
        matches = list(re.finditer(rf"(?<!\w){re.escape(form)}(?!\w)", local, re.I))
        if not matches:
            continue
        tail = local[matches[-1].end():].lstrip(" \"„”',:;–—-")
        pm_after_medium = PERSON_START_RE.match(tail)
        if pm_after_medium:
            person = _valid_person_candidate(pm_after_medium.group("subject"))
            if person:
                return person, "person"

    # Podpis po nazwie programu/medium lub po tytule kończy się zwykle
    # imieniem i nazwiskiem. Najpierw odczytujemy wyłącznie końcową parę
    # tokenów rozpoczynających się wielką literą. Nie stosujemy tutaj re.I,
    # bo dawny regex uznawał „zastępca prokuratora” za nazwę osoby.
    end_local = local.rstrip(" .!?;:")
    if re.search(r"(?:\bw|\bwe|na\s+antenie|w\s+studiu)\b", local, re.I) or TITLE_TOKEN_RE.search(local[:220]):
        end_match = PERSON_END_RE.search(end_local)
        if end_match:
            person = _valid_person_candidate(end_match.group("subject"))
            if person:
                return person, "person"

    # Podpis po nazwie programu/medium, np.
    # „mówił w "Kropce nad i" w TVN24 Witold Zembaczyński”.
    # Prefiks i medium są niewrażliwe na wielkość liter, lecz kandydat osoby
    # jest ponownie sprawdzany na oryginalnym tekście.
    broadcast_prefix = re.search(r"(?:\bw|\bwe|na\s+antenie|w\s+studiu)\b", local, re.I)
    if broadcast_prefix:
        person = _last_full_person(local[broadcast_prefix.end():])
        if person and end_local.casefold().endswith(person.casefold()):
            return person, "person"

    # Jawny tytuł + imię i nazwisko może wystąpić po nazwie programu.
    if TITLE_TOKEN_RE.search(local[:220]):
        for _pos, raw in reversed(_capital_name_candidates(local)):
            person = _valid_person_candidate(raw)
            if person and end_local.casefold().endswith(person.casefold()):
                return person, "person"

    pm = PERSON_START_RE.match(local)
    if pm:
        person = _normalize_person(pm.group("subject"))
        if person and len(person.split()) >= 2 and person.split()[0] not in BAD_NAME_FIRST:
            return person, "person"

    # Jednotokenowe nazwisko jest dopuszczalne wyłącznie bezpośrednio po czasowniku.
    sm = re.match(rf"^(?P<subject>{CAP_TOKEN})(?=\s*[,.;:!?–—-]|$)", local)
    if sm and sm.group("subject") not in BAD_NAME_FIRST:
        return sm.group("subject"), "person"

    party = PARTY_START_RE.match(suffix)
    if party:
        surface = _clean(party.group("subject"))
        # Krótkie skróty partii są czułe na wielkość liter. Zwykły przyimek
        # „po” w „przekazał po przesłuchaniu” nie jest Platformą Obywatelską.
        if len(surface) > 3 or surface.isupper() or surface in {"PiS"}:
            return surface, "party"

    im = INSTITUTION_START_RE.match(suffix)
    if im:
        return _clean(im.group("subject")), "institution"

    # Current: instytucja może być jawnym podmiotem po czasowniku, także po
    # krótkich przysłówkach: „potwierdziła niezależnie teraz także Amnesty International”.
    org_tail = re.search(r"(?P<subject>[A-ZĄĆĘŁŃÓŚŹŻ][\w.-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][\w.-]+){1,4})\s*[.!?]?$", local)
    if org_tail:
        subject = _clean(org_tail.group("subject"))
        if any(token in subject.casefold() for token in ("international", "amnesty", "agencja", "fundacja", "stowarzyszenie", "komisja", "izba")):
            return subject.rstrip(".?!"), "institution"
    return "", ""


def _claim(before: str, after: str, mode: str, action: str = "") -> str:
    negation = ""
    if mode == "before":
        neg = re.search(r"\b(?P<neg>(?:(?:już|jeszcze|nigdy|wcale)\s+)?nie)\s*$", _clean(before), re.I)
        if neg:
            negation = _clean(neg.group("neg"))
    text = before if mode == "after" else after
    text = _clean(text).strip(" ,:;–—-")
    if mode == "before":
        # Następny skoordynowany akt mowy jest osobną relacją, a nie końcówką
        # pierwszej tezy: „powiedział ..., i dodał ...” / „...; Y podkreślił”.
        coordinated = re.search(
            r"[,;]\s*(?:i|oraz|a|następnie|ponadto|dodatkowo|po\s+czym)\s+"
            r"(?:" + "|".join(sorted(map(re.escape, ACTION_FORMS), key=len, reverse=True)) + r")\b",
            text,
            re.I,
        )
        named_clause = re.search(
            rf";\s*{CAP_TOKEN}(?:\s+{CAP_TOKEN}){{1,2}}\s+"
            r"(?:" + "|".join(sorted(map(re.escape, ACTION_FORMS), key=len, reverse=True)) + r")\b",
            text,
            re.I,
        )
        boundary = min(
            (m.start() for m in (coordinated, named_clause) if m is not None),
            default=-1,
        )
        if boundary >= 0:
            text = text[:boundary].rstrip(" ,;:–—-")
    # Okolicznik medium między czasownikiem i „że” nie jest treścią wypowiedzi:
    # „powiedziała w TVN24, że X” -> claim „X”.
    text = re.sub(r"^(?:w|we|na\s+antenie)\s+[^,]{1,100},\s*(?:że|iż)\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:(?:też|również|z kolei)\s*,?\s*)?(?:że|iż)\s+", "", text, flags=re.I)
    quotes = re.findall(r"[\"„]([^\"”]{4,700})[\"”]", text)
    claim = _clean(quotes[0] if quotes else text)
    # W szyku odwróconym „Wpis X skomentował Y” lewa strona jest obiektem
    # aktu mowy, nie pełnym zdaniem. Zachowujemy ją jako audytowalną tezę z
    # predykatem, zamiast odrzucać jako samotną nazwę własną.
    if mode == "after" and _clean(action).casefold() in {"skomentował", "skomentowała", "komentował", "komentowała"}:
        if 1 <= len(claim.split()) <= 12 and not re.search(
            r"\b(?:jest|są|był|była|było|będzie|ma|mają|może|mogą|musi|muszą|"
            r"zrobił|zrobiła|powiedział|powiedziała|napisał|napisała)\b", claim, re.I
        ):
            claim = f"{_clean(action)} {claim}"
    if negation and not re.match(r"^(?:(?:już|jeszcze|nigdy|wcale)\s+)?nie\b", claim, re.I):
        # Samo ``nie`` przed dopełnieniem jest niegramatyczne i słabo
        # audytowalne. Zachowujemy więc zanegowany predykat w treści tezy,
        # nawet jeśli ``speaker_action`` przechowuje go również osobno.
        claim = f"{negation} {_clean(action)} {claim}" if _clean(action) else f"{negation} {claim}"
    return _clean(claim)[:700]


def _claim_from_attribution(rest: str) -> str:
    text = _clean(rest).strip(" ,:;–—-")
    quotes = re.findall(r"[\"„]([^\"”]{4,700})[\"”]", text)
    # Cytat jest całą tezą tylko wtedy, gdy rzeczywiście rozpoczyna treść po
    # atrybucji. W ``Według TK Sejm ..., obradując \"w złym składzie\"``
    # cytat jest jedynie dopełnieniem i nie może wyciąć pełnego zdania.
    if quotes and re.match(r"^[\"„]", text):
        return _clean(quotes[0])[:700]
    # usuń dopowiedzenie typu „posła Koalicji Obywatelskiej,”
    if "," in text and re.match(
        r"^(?:pan\s+|pani\s+)?(?:poseł|posłanka|senator|senatorka|minister|"
        r"premier|prezydent|rzecznik|rzeczniczka|prokurator|mecenas)\b",
        text,
        re.I,
    ):
        text = text.split(",", 1)[1]
    text = re.sub(r"^(?:(?:też|również|z kolei)\s*,?\s*)?(?:że|iż)\s+", "", text, flags=re.I)
    return _clean(text)[:700]


def _target(sentence: str, speaker: str, claim: str) -> str:
    for source in (claim, sentence):
        m = TARGET_PREP_RE.search(source or "")
        if m:
            candidate = _clean(m.group("target")).strip(" ,:;–—-")
            if candidate and candidate.casefold() != speaker.casefold():
                return candidate[:140]
        bm = BEHAVIOR_TARGET_RE.search(source or "")
        if bm:
            candidate = _normalize_person(bm.group("target"))
            if candidate and candidate.casefold() != speaker.casefold():
                return candidate[:140]
    for raw in re.findall(rf"\b({CAP_TOKEN}\s+{CAP_TOKEN})\b", claim or ""):
        candidate = _normalize_person(raw)
        if candidate and candidate.casefold() != speaker.casefold() and candidate.split()[0] not in BAD_NAME_FIRST:
            return candidate[:140]
    return ""


def _empty() -> Dict[str, Any]:
    return {
        "stage": STAGE,
        "matched": False,
        "speaker": "",
        "speaker_kind": "",
        "source": "",
        "source_kind": "",
        "action": "",
        "attribution_marker": "",
        "claim": "",
        "target": "",
        "confidence": 0.0,
        "method": "none",
        "warnings": [],
        "sentence": "",
        "context_sentence": "",
    }


def _subject_from_attribution_body(body: str) -> Tuple[str, str, str]:
    raw = _clean(body).lstrip("\"„”'")
    titled_person = re.match(
        rf"(?:[a-ząćęłńóśźż-]+\s+){{0,3}}(?:ministra|premiera|prezydenta|rzecznika|"
        rf"prokuratora|posła|senatora|profesora|mecenasa)\s+"
        rf"(?P<subject>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)(?P<rest>.*)$",
        raw, re.I,
    )
    if titled_person:
        subject = _normalize_person(titled_person.group("subject"))
        if subject:
            return subject, "person", titled_person.group("rest")
    # Najpierw kontrolowane medium, np. „Według Gazety Wyborczej ...”.
    for form in ["GW", *MEDIA_FORMS]:
        if re.match(rf"^{re.escape(form)}(?=\s|,|:|$)", raw, re.I):
            subject = _known_medium(form) or form
            return subject, "medium", raw[len(form):]
    im = INSTITUTION_START_RE.match(raw)
    if im:
        subject = _clean(im.group("subject"))
        return subject, "institution", raw[im.end():]
    party = PARTY_START_RE.match(raw)
    if party:
        subject = _clean(party.group("subject"))
        return subject, "party", raw[party.end():]
    pm = re.match(rf"(?P<subject>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)(?P<rest>.*)$", raw)
    if pm:
        subject = _normalize_person(pm.group("subject"))
        if subject and subject.split()[0] not in BAD_NAME_FIRST:
            return subject, "person", pm.group("rest")
    return "", "", raw


def _attribution_prefix_candidate(sentence: str) -> Dict[str, Any] | None:
    match = ATTRIBUTION_PREFIX_RE.match(sentence)
    if not match:
        return None
    marker = _clean(match.group("marker")).casefold()
    subject, kind, rest = _subject_from_attribution_body(match.group("body"))
    if not subject:
        return None

    # Konstrukcja z jawnym źródłem i jawnym mówcą, np.
    # „Według TVN24 Patricia Nowak powiedziała, że ...”. Medium pozostaje
    # źródłem, a osoba jest mówcą. Stara logika gubiła osobę i traktowała
    # całe dalsze zdanie jako claim źródła.
    rest_clean = _clean(rest).lstrip(" ,:;–—-\"„”'")
    if kind in {"medium", "institution"}:
        for am in ACTION_RE.finditer(rest_clean):
            prefix, suffix = rest_clean[:am.start()], rest_clean[am.end():]
            embedded, embedded_kind = _subject_before(prefix)
            if embedded and embedded_kind == "person":
                claim = _claim(prefix, suffix, "before", am.group(1).casefold())
                if claim:
                    return {
                        **_empty(),
                        "matched": True,
                        "speaker": embedded,
                        "speaker_kind": "person",
                        "source": subject,
                        "source_kind": kind,
                        "action": am.group(1).casefold(),
                        "claim": claim,
                        "target": _target(sentence, embedded, claim),
                        "confidence": 0.99,
                        "method": "attribution_source_plus_explicit_speaker",
                    }

    claim = _claim_from_attribution(rest)
    if not claim:
        return None
    action = ""
    candidate = {**_empty(), "matched": True, "action": action, "attribution_marker": marker, "claim": claim, "confidence": 0.97,
                 "method": "attribution_prefix", "target": _target(sentence, subject if kind == "person" else "", claim)}
    if kind == "person":
        candidate.update({"speaker": subject, "speaker_kind": "person"})
    else:
        candidate.update({"source": subject, "source_kind": kind})
    return candidate


def _contextual_attribution_candidate(
    sentence: str,
    active_speaker: Dict[str, Any] | None,
    *,
    scope: str = "same_block",
) -> Dict[str, Any] | None:
    """Rozwiązuje jawne anafory do ostatniego jednoznacznego mówcy.

    Mówcą może być osoba, instytucja lub partia, ale koreferencja działa
    wyłącznie wewnątrz jednego bloku. Nowy akapit/śródtytuł zeruje stan.
    """
    # Kontrakt v2: koreferencja mówcy jest wyłącznie wewnątrz jednego bloku.
    # Wywołanie z innym zakresem ma zostać odrzucone, a nie osłabione scoringiem.
    if scope != "same_block":
        return None
    if not active_speaker or not _clean(active_speaker.get("speaker")):
        return None
    pronoun = PRONOUN_ATTRIBUTION_RE.match(sentence)
    role = ROLE_ONLY_ATTRIBUTION_RE.match(sentence)
    start_action = ANAPHORIC_START_RE.match(sentence)
    end_action = ANAPHORIC_END_RE.match(sentence)
    trailing_action = ANAPHORIC_TRAILING_RE.match(sentence)
    jak_action = ANAPHORIC_JAK_RE.match(sentence)
    role_continuation = ROLE_CONTINUATION_RE.match(sentence)
    role_action_continuation = ROLE_ACTION_CONTINUATION_RE.match(sentence)
    bare_passive_continuation = BARE_PASSIVE_ACTION_CONTINUATION_RE.match(sentence)
    role_descriptor_end = ROLE_DESCRIPTOR_END_RE.match(sentence)
    match = pronoun or role or start_action or end_action or trailing_action or jak_action or role_continuation or role_action_continuation or bare_passive_continuation or role_descriptor_end
    if not match:
        return None
    if start_action:
        claim_raw = sentence[start_action.end():]
        claim_raw = re.sub(r"^[,:;–—-]*\s*(?:że|iż)?\s*", "", claim_raw, flags=re.I)
    elif role_action_continuation:
        claim_raw = role_action_continuation.groupdict().get("claim") or ""
        claim_raw = re.sub(r"^[,:;–—-]*\s*(?:że|iż)?\s*", "", claim_raw, flags=re.I)
    elif bare_passive_continuation:
        claim_raw = bare_passive_continuation.groupdict().get("claim") or ""
        claim_raw = re.sub(r"^[,:;–—-]*\s*(?:że|iż)?\s*", "", claim_raw, flags=re.I)
    elif role_descriptor_end:
        claim_raw = role_descriptor_end.groupdict().get("claim") or ""
    else:
        claim_raw = match.groupdict().get("claim") or ""
    claim = _claim_from_attribution(claim_raw)
    if not claim:
        return None
    if start_action or end_action or trailing_action or jak_action or role_continuation or role_action_continuation or bare_passive_continuation or role_descriptor_end:
        action = _clean(match.group("action")).casefold()
        marker = ""
    else:
        marker = _clean(match.group("marker")).casefold()
        action = ""
    speaker_kind = _clean(active_speaker.get("speaker_kind")) or "person"

    # Deskryptor osoby („dodał były szef MS”) oznacza nową, choć czasem
    # nierozwiązaną osobę. Nie wolno przypisać takiej wypowiedzi poprzedniej
    # instytucji tylko dlatego, że jej nazwa ma zgodny rodzaj gramatyczny.
    if role_descriptor_end and speaker_kind != "person":
        return None

    # Current: jawna niezgodność rodzaju blokuje koreferencję. Nie jest to
    # model morfologiczny całego języka, tylko konserwatywna bramka dla form,
    # w których polski czas przeszły koduje rodzaj wprost.
    previous_gender = _action_gender(active_speaker.get("action"))
    current_gender = _action_gender(action)
    if previous_gender and current_gender and previous_gender != current_gender:
        return None

    method = "same_block_role_or_pronoun_attribution"
    warning = "speaker_resolved_from_previous_explicit_role"
    base_score = 0.84
    gender_agreement = bool(previous_gender and current_gender and previous_gender == current_gender)
    coreference_score = min(0.89, base_score + (0.05 if gender_agreement else 0.0))
    return {
        **_empty(),
        "matched": True,
        "speaker": _clean(active_speaker.get("speaker")),
        "speaker_kind": speaker_kind,
        "source": _clean(active_speaker.get("source")),
        "source_kind": _clean(active_speaker.get("source_kind")),
        "action": action,
        "attribution_marker": marker,
        "claim": claim,
        "target": _target(sentence, _clean(active_speaker.get("speaker")) if speaker_kind == "person" else "", claim),
        "confidence": coreference_score,
        "method": method,
        "warnings": [warning],
        "context_sentence": _clean(active_speaker.get("sentence") or active_speaker.get("context_sentence")),
        "coreference_scope": scope,
        "coreference_score": coreference_score,
        "coreference_gender_previous": previous_gender,
        "coreference_gender_current": current_gender,
        "coreference_gender_agreement": gender_agreement,
    }


def _speaker_context_candidate(sentence: str, aliases: Dict[str, str]) -> Dict[str, Any] | None:
    """Wysokiej pewności wprowadzenie osoby jako bieżącego mówcy.

    Zdarzenie jest tylko stanem kontekstowym i nie trafia do publicznych relacji.
    """
    local = _clean(sentence)
    testimony_context = re.search(
        rf"\bwypowiedzi\s+(?P<surname>{CAP_TOKEN})\s*,?\s*podczas\s+której\s+"
        r"(?:zeznał|zeznała|mówił|mówiła|wskazał|wskazała)\b",
        local, re.I,
    )
    if testimony_context:
        surname = _clean(testimony_context.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold():
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": "zeznał", "claim": "kontekst wypowiedzi",
                "target": "", "confidence": 0.97, "method": "speaker_context_introduction",
                "context_only": True,
            }
    authored_post = re.search(
        r"\b(?:opublikował|opublikowała|zamieścił|zamieściła)\b[^.!?]{0,320}?"
        r"(?:nagranie|wpis|oświadczenie|komunikat|post|film|materiał)\b",
        local, re.I,
    )
    if authored_post:
        raw, raw_kind = _subject_before(local[:authored_post.start()])
        raw = _valid_person_candidate(raw) if raw_kind == "person" else ""
        speaker = _expand_person_alias(raw, aliases) if raw else ""
        if speaker and len(speaker.split()) >= 2:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": "opublikował", "claim": "kontekst opublikowanej wypowiedzi",
                "target": "", "confidence": 0.97, "method": "speaker_context_introduction",
                "context_only": True,
            }
    professional_intro = re.search(
        rf"\b(?:mówił|mówiła|wypowiadał\s+się|wypowiadała\s+się)\b[^.!?]{{0,160}}?"
        rf"(?:profesor|prof\.|prawnik|ekspert|ekspertka)\s+(?P<speaker>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\b",
        local, re.I,
    )
    if professional_intro:
        raw = _valid_person_candidate(professional_intro.group("speaker"))
        speaker = _expand_person_alias(raw, aliases) if raw else ""
        if speaker and len(speaker.split()) >= 2:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": "wprowadzenie mówcy", "claim": "kontekst wypowiedzi",
                "target": "", "confidence": 0.985, "method": "speaker_context_introduction",
                "context_only": True,
            }
    match = SPEAKER_CONTEXT_INTRO_RE.match(local)
    if not match:
        return None
    raw = _valid_person_candidate(match.group("speaker"))
    speaker = _expand_person_alias(raw, aliases) if raw else ""
    if not speaker or len(speaker.split()) < 2:
        return None
    return {
        **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
        "action": "wprowadzenie mówcy", "claim": "kontekst wypowiedzi",
        "target": "", "confidence": 0.985, "method": "speaker_context_introduction",
        "context_only": True,
    }


ROLE_PERSON_ANCHOR_RE = re.compile(
    r"\b(?P<title>minister|wiceminister|premier|prezydent|rzecznik|prokurator|mecenas|europoseł|poseł|posłanka|senator|senatorka|prezes|szef|szefowa|przewodniczący|przewodnicząca|profesor|prawnik|ekspert|ekspertka|marszałek|wicemarszałek|lider|liderka)\b",
    re.I,
)


def _role_key(value: Any) -> str:
    key = _clean(value).casefold()
    return {"posłanka": "poseł", "senatorka": "senator", "szefowa": "szef", "przewodnicząca": "przewodniczący", "ekspertka": "ekspert", "liderka": "lider"}.get(key, key)


def _role_person_mentions(sentence: str, aliases: Dict[str, str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for match in ROLE_PERSON_ANCHOR_RE.finditer(sentence):
        window = sentence[match.end():match.end() + 120]
        for _pos, raw in _capital_name_candidates(window):
            person = _valid_person_candidate(raw)
            if not person:
                continue
            person = _expand_person_alias(person, aliases)
            if len(person.split()) >= 2:
                out.append((_role_key(match.group("title")), person))
                break
    return out


def _role_seed_candidate(sentence: str, role_context: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    match = ROLE_ACTION_CONTINUATION_RE.match(sentence) or ROLE_PASSIVE_ACTION_CONTINUATION_RE.match(sentence)
    if not match:
        return None
    seed = role_context.get(_role_key(match.group("title")))
    if not seed:
        return None
    if ROLE_PASSIVE_ACTION_CONTINUATION_RE.match(sentence):
        claim = _claim_from_attribution(match.group("claim"))
        if not claim:
            return None
        action = _clean(match.group("action")).casefold()
        return {
            **_empty(), "matched": True, "speaker": _clean(seed.get("speaker")),
            "speaker_kind": _clean(seed.get("speaker_kind")) or "person",
            "action": action, "claim": claim,
            "target": _target(sentence, _clean(seed.get("speaker")), claim),
            "confidence": 0.93, "method": "same_block_role_or_pronoun_attribution",
            "warnings": ["speaker_resolved_from_previous_explicit_role"],
            "context_sentence": _clean(seed.get("sentence")),
            "coreference_scope": "same_block", "coreference_score": 0.93,
        }
    return _contextual_attribution_candidate(sentence, seed, scope="same_block")


def _special_explicit_candidate(sentence: str, aliases: Dict[str, str]) -> Dict[str, Any] | None:
    """Obsługuje częste konstrukcje pomijane przez ogólny resolver."""
    # Atrybucja wtrącona w środek zdania: ``Takich osób, jak przekazał ...
    # Adam Bodnar, ma być więcej``. Treścią jest połączenie fragmentów po obu
    # stronach wtrącenia, a nie urwane ``Takich osób, jak``.
    parenthetical = re.match(
        rf"^(?P<before>.+?),\s*jak\s+"
        rf"(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\s+"
        rf"(?P<descriptor>[^.!?]{{0,220}}?)\s+"
        rf"(?P<speaker>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s*,\s*"
        rf"(?P<after>.+)$",
        sentence,
        re.I,
    )
    if parenthetical:
        raw_speaker = _valid_person_candidate(parenthetical.group("speaker"))
        speaker = _expand_person_alias(raw_speaker, aliases) if raw_speaker else ""
        before = _clean(parenthetical.group("before")).rstrip(" ,")
        after = _clean(parenthetical.group("after")).lstrip(" ,")
        claim = _clean(f"{before} {after}")
        if speaker and len(speaker.split()) >= 2 and claim:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": _clean(parenthetical.group("action")).casefold(), "claim": claim,
                "target": _target(sentence, speaker, claim), "confidence": 0.995,
                "method": "parenthetical_explicit_attribution",
            }

    # Nazwana funkcja + jednoznaczne nazwisko przed długim dopowiedzeniem:
    # „Przesłuchiwany prokurator Tietz, który ... z Funduszu ... zeznawał, że”.
    # Najbliższa instytucja w dopełnieniu nie może przejąć podmiotu zdania.
    titled_surname = re.match(
        rf"^[^.!?]{{0,180}}?\b(?:prokurator|sędzia|minister|wiceminister|poseł|posłanka|"
        rf"senator|senatorka|prezes|prezeska|rzecznik|rzeczniczka)\s+"
        rf"(?P<surname>{CAP_TOKEN})\s*,\s*(?:który|która|będący|będąca)\b"
        rf"(?P<middle>[^.!?]{{0,420}}?)\b(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\b"
        rf"(?P<claim>.*)$",
        sentence,
        re.I,
    )
    if titled_surname:
        surname = _clean(titled_surname.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        claim = _claim_from_attribution(titled_surname.group("claim"))
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold() and claim:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": _clean(titled_surname.group("action")).casefold(), "claim": claim,
                "target": _target(sentence, speaker, claim), "confidence": 0.992,
                "method": "leading_titled_surname_with_parenthetical",
            }

    # „Pytany ..., Kokot wyjaśnił ...”: nazwiska wewnątrz pytania są obiektami,
    # a jawnym podmiotem jest nazwisko po zamykającym przecinku.
    passive_surname = re.match(
        rf"^(?:pytany|pytana|zapytany|zapytana|proszony|proszona)\b.{{0,420}}?,\s*"
        rf"(?P<surname>{CAP_TOKEN})\s+(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\b(?P<claim>.*)$",
        sentence, re.I,
    )
    if passive_surname:
        surname = _clean(passive_surname.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold():
            claim = _claim_from_attribution(passive_surname.group("claim"))
            if claim:
                return {
                    **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                    "action": _clean(passive_surname.group("action")).casefold(), "claim": claim,
                    "target": _target(sentence, speaker, claim), "confidence": 0.992,
                    "method": "passive_question_trailing_surname",
                }

    trailing_surname_interview = re.match(
        rf"^(?P<claim>.+?)\s*[-–—]\s*(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\s+"
        rf"(?P<surname>{CAP_TOKEN})\s+(?:w\s+rozmowie\s+z|dla)\b.+$",
        sentence, re.I,
    )
    if trailing_surname_interview:
        surname = _clean(trailing_surname_interview.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        claim = _claim_from_attribution(trailing_surname_interview.group("claim"))
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold() and claim:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": _clean(trailing_surname_interview.group("action")).casefold(),
                "claim": claim, "target": _target(sentence, speaker, claim),
                "confidence": 0.995, "method": "trailing_surname_explicit_alias",
            }

    embedded = re.search(
        rf"(?P<dash1>[-–—]?\s*)\bjak\s+(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\s+"
        rf"(?:jej|jego)?\s*(?:przewodnicząca|przewodniczący|minister|wiceminister|premier|prezydent|rzecznik|rzeczniczka|prokurator|profesor|prawnik|ekspert|ekspertka)?\s*"
        rf"(?P<speaker>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s*(?P<dash2>[-–—]?)",
        sentence, re.I,
    )
    if embedded:
        raw = _valid_person_candidate(embedded.group("speaker"))
        speaker = _expand_person_alias(raw, aliases) if raw else ""
        if speaker and len(speaker.split()) >= 2:
            stripped = _clean((sentence[:embedded.start()] + " " + sentence[embedded.end():]).replace(" - - ", " "))
            claim = stripped.strip(" ,:;–—-")[:420]
            if claim:
                return {
                    **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                    "action": _clean(embedded.group("action")).casefold(), "claim": claim,
                    "target": _target(sentence, speaker, claim), "confidence": 0.995,
                    "method": "embedded_jak_explicit_speaker",
                }
    passive = PASSIVE_INTERVIEW_CONTEXT_RE.match(sentence)
    if passive:
        speaker = _valid_person_candidate(passive.group("speaker"))
        speaker = _expand_person_alias(speaker, aliases) if speaker else ""
        claim = _clean(passive.group("claim")).lstrip(" ,:;–—-") or "kontekst pytania"
        if speaker:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": "pytano", "claim": claim[:420], "target": _target(sentence, speaker, claim),
                "confidence": 0.94, "method": "passive_interview_context", "context_only": True,
            }

    # Current: ``Brejza: ...`` — pojedyncze nazwisko jest bezpieczne tylko
    # jako jednoznaczny alias pełnej osoby w tym samym dokumencie.
    cm = SURNAME_COLON_RE.match(sentence)
    if cm:
        surname = _clean(cm.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        claim = _claim_from_attribution(cm.group("claim"))
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold() and claim:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": "mówi", "claim": claim, "target": _target(sentence, speaker, claim),
                "confidence": 0.995, "method": "surname_colon_explicit_alias",
            }

    # Jednoznaczny alias nazwiska może być jawnym podmiotem na początku
    # zdania także z wtrąceniem źródłowym: „Ziobro w rozmowie z "Super
    # Expressem" ... poinformował ...”. Medium w środku nie staje się mówcą.
    lm = re.match(
        rf"^(?P<surname>{CAP_TOKEN})\b(?P<context>[^.!?]{{0,260}}?)\b"
        rf"(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\b(?P<claim>.+)$",
        sentence, re.I,
    )
    if lm:
        surname = _clean(lm.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        context = _clean(lm.group("context"))
        subject_context = _subject_scan_text(context)
        other_people = [
            _valid_person_candidate(raw) for _pos, raw in _capital_name_candidates(subject_context)
            if _valid_person_candidate(raw)
        ]
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold() and not other_people:
            claim = _claim_from_attribution(lm.group("claim"))
            if claim:
                return {
                    **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                    "action": _clean(lm.group("action")).casefold(), "claim": claim,
                    "target": _target(sentence, speaker, claim), "confidence": 0.985,
                    "method": "leading_surname_explicit_alias",
                }

    # Current: ``... — przypomniał Brejza``. Nazwisko po czasowniku nie może
    # zostać zgadnięte; wymagamy aliasu pełnej osoby w bieżącym dokumencie.
    tm = TRAILING_NAMED_SPEAKER_RE.match(sentence)
    if tm:
        surname = _clean(tm.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        claim = _claim_from_attribution(tm.group("claim"))
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold() and claim:
            return {
                **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                "action": _clean(tm.group("action")).casefold(), "claim": claim,
                "target": _target(sentence, speaker, claim), "confidence": 0.995,
                "method": "trailing_surname_explicit_alias",
            }


    jm = JAK_NAMED_ATTRIBUTION_RE.match(sentence)
    if jm:
        raw_speaker = _clean(jm.group("speaker"))
        speaker = _expand_person_alias(raw_speaker, aliases)
        # Jednotokenowe nazwisko jest dopuszczalne tylko wtedy, gdy dokument
        # pozwala rozwinąć je do pełnej osoby.
        if len(speaker.split()) >= 2:
            claim = _claim_from_attribution(jm.group("claim"))
            if claim:
                return {
                    **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                    "action": _clean(jm.group("action")).casefold(), "claim": claim,
                    "target": _target(sentence, speaker, claim), "confidence": 0.99,
                    "method": "jak_named_speaker_explicit",
                }

    # Current: jawne nazwisko po czasowniku może mieć kontrolowane dopełnienie,
    # np. „mówił Kropiwnicki do polityków PiS, że ...”. Nazwisko musi dać się
    # jednoznacznie rozwinąć z aliasów bieżącego dokumentu.
    scm = re.search(
        rf"\b(?P<action>{'|'.join(sorted(map(re.escape, PERSON_ACTIONS), key=len, reverse=True))})\s+"
        rf"(?P<surname>{CAP_TOKEN})\s+(?P<complement>(?:do|wobec|o|na\s+temat)\s+[^,.;:!?]{{1,90}})[,;:]\s*(?:że|iż)?\s*(?P<claim>.+)$",
        sentence, re.I,
    )
    if scm:
        surname = _clean(scm.group("surname"))
        speaker = _expand_person_alias(surname, aliases)
        if speaker and len(speaker.split()) >= 2 and speaker.casefold() != surname.casefold():
            claim = _claim_from_attribution(scm.group("claim"))
            if claim:
                return {
                    **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                    "action": _clean(scm.group("action")).casefold(), "claim": claim,
                    "target": _target(sentence, speaker, claim), "confidence": 0.985,
                    "method": "surname_after_action_with_complement",
                }

    qm = QUOTE_ROLE_PERSON_RE.match(sentence)
    if qm and re.search(r"(?:odnosząc|nawiązując|zwracając)\s+(?:się\s+)?do\b", _clean(qm.group("context")), re.I):
        qm = None
    if qm:
        raw_surface = _clean(qm.group("speaker"))
        context_surface = _clean(qm.group("context"))

        # V4.3.8 RELATION QUALITY: wtórne źródło nie może przejąć roli mówcy.
        # Przykład: „... przekazał ... dziennikarz Maciej Duda, powołując się
        # na informacje od rzecznika ... Przemysława Nowaka”. Mówcą bieżącej
        # relacji jest Maciej Duda; Nowak jest źródłem przywołanym.
        secondary_source_person = ""
        secondary_source_match = re.search(
            r"\b(?:powołując|powołujac)\s+się\s+na\b|\b(?:według|wg)\b",
            context_surface, re.I,
        )
        if secondary_source_match:
            primary_context = context_surface[:secondary_source_match.start()]
            primary_person = _named_person_in_signature(primary_context)
            if primary_person:
                secondary_source_person = primary_person

        # W podpisie „poseł PiS Tobiasz Bocheński” / „posłanka KO Joanna ...”
        # regex może uchwycić afiliację razem z osobą. Afiliacja jest opisem,
        # więc jeżeli po pełnym aliasie partii stoi poprawne Imię Nazwisko,
        # osoba ma bezwzględne pierwszeństwo.
        prefixed_person = ""
        trailing_named = _named_person_in_signature(context_surface + " " + raw_surface)
        if secondary_source_person:
            prefixed_person = secondary_source_person
        elif trailing_named:
            prefixed_person = trailing_named
        party_prefix = PARTY_START_RE.match(raw_surface)
        if party_prefix and not prefixed_person:
            tail = raw_surface[party_prefix.end():].strip()
            prefixed_person = _valid_person_candidate(tail)
        if prefixed_person:
            subject, subject_kind = prefixed_person, "person"
        else:
            subject, subject_kind = _subject_kind(raw_surface)
        claim = _clean(qm.group("claim")).strip(" \"\',:;–—-")[:420]
        if subject_kind == "person":
            speaker = _expand_person_alias(subject, aliases) if subject else ""
            if speaker and claim:
                return {
                    **_empty(), "matched": True, "speaker": speaker, "speaker_kind": "person",
                    "action": _clean(qm.group("action")).casefold(), "claim": claim,
                    "target": _target(sentence, speaker, claim), "confidence": 0.995,
                    "method": "quote_role_program_medium_explicit_speaker",
                }
        elif subject_kind in {"institution", "party"} and claim:
            return {
                **_empty(), "matched": True, "speaker": subject, "speaker_kind": subject_kind,
                "action": _clean(qm.group("action")).casefold(), "claim": claim,
                "target": _target(sentence, "", claim), "confidence": 0.995,
                "method": "quote_explicit_institutional_speaker",
            }
        elif subject_kind == "medium" and claim:
            return {
                **_empty(), "matched": True, "source": subject, "source_kind": "medium",
                "action": _clean(qm.group("action")).casefold(), "claim": claim,
                "target": _target(sentence, "", claim), "confidence": 0.995,
                "method": "quote_explicit_medium_source",
            }

    sm = SURNAME_ATTRIBUTION_RE.match(sentence)
    if sm:
        surname = _clean(sm.group("surname"))
        # „Według Anny Nowak …” nie jest atrybucją po samym nazwisku.
        # Dawny branch brał „Anny” za nazwisko, a „Nowak” doklejał do claimu.
        # Gdy pierwszy token jest rozpoznawalną formą imienia i po nim stoi
        # kolejny kapitalizowany token, zostawiamy zdanie pełnemu parserowi
        # attribution_prefix, który zachowuje całe imię+nazwisko.
        known_first_forms = {str(x).casefold() for x in COMMON_GIVEN_NAMES} | set(PERSON_TOKEN_NOMINATIVE) | {str(x).casefold() for x in PERSON_TOKEN_NOMINATIVE.values()}
        claim_tail = _clean(sm.group("claim"))
        if surname.casefold() in known_first_forms and re.match(rf"^{CAP_TOKEN}\b", claim_tail):
            sm = None
    if sm:
        surname = _clean(sm.group("surname"))
        full = _expand_person_alias(surname, aliases)
        if not full or full.casefold() == surname.casefold():
            folded = surname.casefold()
            stem = folded[:max(4, len(folded) - 2)]
            candidates = {value for key, value in aliases.items() if key.startswith(stem) or stem in key}
            if len(candidates) == 1:
                full = next(iter(candidates))
        if full and full.casefold() != surname.casefold():
            claim = _claim_from_attribution(sm.group("claim"))
            marker = _clean(sm.group("marker")).casefold()
            if claim:
                return {
                    **_empty(), "matched": True, "speaker": full, "speaker_kind": "person",
                    "action": "",
                    "attribution_marker": marker, "claim": claim,
                    "target": _target(sentence, full, claim), "confidence": 0.97,
                    "method": "surname_attribution_resolved_from_document_alias",
                }

    cm = re.search(r"\bCitizen\s+Lab\b(?P<claim>.+)$", sentence, re.I)
    if cm and sentence.casefold().startswith(("według informacji", "według analizy")):
        claim = _clean(cm.group("claim")).lstrip(" ,:;–—-")[:420]
        if claim:
            return {
                **_empty(), "matched": True, "source": "Citizen Lab", "source_kind": "institution",
                "action": "podało", "attribution_marker": "według analizy", "claim": claim,
                "target": _target(sentence, "", claim), "confidence": 0.94,
                "method": "citizen_lab_reported_fact",
            }
    return None


def _explicit_candidate(sentence: str) -> Dict[str, Any] | None:
    empty = _empty()
    best: Dict[str, Any] | None = _attribution_prefix_candidate(sentence)

    cm = COLON_RE.search(sentence)
    if cm and not META_RE.search(cm.group("subject")):
        # Dwukropek nie jest dowodem osoby sam w sobie (np. ``KO: ...``).
        # Wymagamy pełnej, wiarygodnej nazwy osoby; nazwisko-jednotokenowe
        # obsługuje osobna ścieżka aliasowa.
        subject = _valid_person_candidate(cm.group("subject"))
        first = subject.split()[0].casefold() if subject else ""
        known_given = {str(x).casefold() for x in COMMON_GIVEN_NAMES} | {
            str(x).casefold() for x in PERSON_TOKEN_NOMINATIVE.values()
        } | set(PERSON_TOKEN_NOMINATIVE)
        claim = _clean(cm.group("claim"))[:700]
        # Nagłówki, kategorie i wyliczenia liczbowe bardzo często mają formę
        # ``Eurofighter Typhoon: 12...``. Dwukropek publikujemy jako wypowiedź
        # tylko dla pełnego nazwiska zaczynającego się rozpoznawalnym imieniem
        # i nienumerycznej treści. Jednotokenowe nazwiska obsługuje ścieżka
        # aliasowa oparta na dowodzie z całego dokumentu.
        numeric_or_heading = bool(re.match(r"^(?:[\d%€$£]|ponad\s+\d|około\s+\d|ok\.\s*\d)", claim, re.I))
        if subject and first in known_given and not numeric_or_heading:
            candidate = {**empty, "matched": True, "speaker": subject, "speaker_kind": "person",
                         "action": "mówi", "claim": claim, "target": _target(sentence, subject, claim),
                         "confidence": 0.88, "method": "colon_attribution"}
            if best is None or candidate["confidence"] > best["confidence"]:
                best = candidate

    for am in ACTION_RE.finditer(sentence):
        action = am.group(1).casefold()
        prefix, suffix = sentence[:am.start()], sentence[am.end():]

        # „pisał scenariusze/ustawy/teksty” opisuje czynność, nie akt mowy.
        # Zachowujemy jedynie jawną konstrukcję raportującą „pisał, że ...” lub
        # podpis po cytacie „... — pisał X”.
        if action in {"pisał", "pisała"} and not (
            re.match(r"^\s*[,;:]?\s*(?:że|iż)\b", suffix, re.I)
            or re.search(r"[-–—]\s*$", prefix)
        ):
            continue

        # Fizyczne/urzędowe przekazanie dokumentu do odbiorcy nie jest
        # wypowiedzią odbiorcy ani relacją cytowania. Konstrukcje z „że” oraz
        # podpisy po cytacie nadal są obsługiwane.
        if action in {"przekazał", "przekazała", "przekazało"} and (
            re.match(r"^\s+(?:do|dla|wobec|przeciwko|od|u)\b", suffix, re.I)
            and not re.search(r"\b(?:że|iż)\b|[\"„]", suffix, re.I)
            and not re.search(r"[-–—]\s*$", prefix)
        ):
            continue

        # „podał się do dymisji” nie jest aktem mowy. Ten sam leksem „podał”
        # pozostaje dozwolony w konstrukcji źródłowej „podał, że / podał dziennik”.
        if action in {"podał", "podała", "podaje"} and re.match(r"^\s+się\b", suffix, re.I):
            continue

        # Current: korpus prasowy bywa uszkodzony tak, że między funkcją i kolejnym
        # czasownikiem znika imię i nazwisko: „szef KPRM Zaznaczył, że...”.
        # Nie wolno wtedy brać wcześniejszej osoby z cytatu jako mówcy nowego
        # czasownika. Taka atrybucja pozostaje nierozwiązana.
        malformed_missing_name = bool(re.search(
            r"(?:szef(?:owa)?|rzecznik(?:czka)?|minister|premier|prezydent|prokurator)\s+[A-ZĄĆĘŁŃÓŚŹŻ]{2,10}\s*$",
            prefix,
        ))
        if malformed_missing_name:
            continue

        # aktywny kontrakt: dla czasowników źródłowych jawne medium po czasowniku ma
        # pierwszeństwo przed osobą występującą wcześniej w opisywanym fakcie.
        # Zapobiega relacji „Jacek Karnowski → napisała → Gazeta Wyborcza”.
        source_after = _reporting_medium_after_verb(suffix) if action in SOURCE_ACTIONS else ""
        if source_after:
            claim = _claim(prefix, suffix, "after")
            candidate = {**empty, "matched": True, "action": action, "claim": claim,
                         "source": source_after, "source_kind": "medium",
                         "target": _target(sentence, "", claim), "confidence": 0.996,
                         "method": "explicit_source_after_reporting_verb"}
            if best is None or candidate["confidence"] > best["confidence"]:
                best = candidate

        after_subject, after_kind = _subject_after(suffix)
        immediate_person_after = bool(
            after_subject and after_kind == "person"
            and re.match(rf"^\s*{re.escape(after_subject)}(?=\s|[,.;:!?]|$)", suffix, re.I)
        )
        immediate_named_after = bool(
            after_subject and re.match(rf"^\s*{re.escape(after_subject)}(?=\s|[,.;:!?]|$)", suffix, re.I)
        )
        explicit_after = bool(after_subject and (
            immediate_person_after
            or (after_kind in {"institution", "party", "medium"} and immediate_named_after)
            or re.search(r"[-–—,]\s*$", prefix)
            or (after_kind == "person" and TITLE_TOKEN_RE.search(suffix[:180]))
            or len(after_subject.split()) == 1
        ))
        if explicit_after:
            claim = _claim(prefix, suffix, "after", action)
            candidate = {**empty, "matched": True, "action": action, "claim": claim,
                         "target": _target(sentence, after_subject if after_kind == "person" else "", claim),
                         "confidence": 0.995 if after_kind == "person" and re.search(r"[-–—]\s*$", prefix) else 0.975,
                         "method": "explicit_subject_after_verb"}
            if after_kind in {"person", "institution", "party"}:
                candidate.update({"speaker": after_subject, "speaker_kind": after_kind})
            else:
                candidate.update({"source": after_subject, "source_kind": after_kind})
            if best is None or candidate["confidence"] > best["confidence"]:
                best = candidate

        subject_prefix = _subject_scan_text(prefix)
        relative_person = _relative_antecedent(subject_prefix)
        subject, kind = (relative_person, "person") if relative_person else _subject_before(subject_prefix)
        # „lider Suwerennej Polski odparł” / „szef CBA powiedział” opisuje
        # nienazwaną osobę pełniącą funkcję. Organizacja nie jest podmiotem
        # gramatycznym osobowej formy czasownika. Bez jawnej osoby lub
        # bezpiecznej koreferencji w tym samym bloku nie tworzymy relacji.
        role_organization_only = bool(
            kind in {"party", "institution"}
            and action in PERSON_ACTIONS
            and re.search(
                rf"(?:lider|liderka|szef|szefowa|prezes|prezeska|przewodniczący|przewodnicząca|"
                rf"rzecznik|rzeczniczka|poseł|posłanka|europoseł|europosłanka)\s+"
                rf"{re.escape(subject)}\s*$",
                subject_prefix, re.I,
            )
        )
        if role_organization_only:
            subject, kind = "", ""
        # Jawny podpis po czasowniku w konstrukcji cytat — powiedział X ma
        # pierwszeństwo przed przypadkową instytucją znalezioną w treści cytatu.
        # Current: w układzie „CLAIM — powiedział ...” osoba znajdująca się
        # wewnątrz CLAIM-u nigdy nie jest zapasowym mówcą. Albo podpis po
        # czasowniku jest jawny, albo używamy kontrolowanej anafory, albo
        # relację odrzucamy.
        quote_signature_without_subject = bool(re.search(r"[-–—]\s*$", prefix)) and not explicit_after
        if not explicit_after and not source_after and subject and not quote_signature_without_subject:
            claim = _claim(prefix, suffix, "before", action)
            claim = re.sub(r"^jako\s+", "", claim, flags=re.I)
            role_linked_main_clause = bool(re.search(
                r"(?:^|[,;])\s*(?:pani\s+|pan\s+)?(?:przewodnicząca|przewodniczący|"
                r"wiceministra|wiceminister|ministra|minister|rzeczniczka|rzecznik|"
                r"szefowa|szef|posłanka|poseł|europosłanka|europoseł)\b",
                prefix, re.I,
            ))
            candidate = {**empty, "matched": True, "action": action, "claim": claim,
                         "target": _target(sentence, subject if kind == "person" else "", claim),
                         "confidence": 0.985 if kind == "person" and role_linked_main_clause else (0.97 if kind in {"medium", "institution"} else 0.94),
                         "method": "explicit_role_referent_before_verb" if kind == "person" and role_linked_main_clause else "explicit_subject_before_verb"}
            if kind in {"person", "institution", "party"}:
                candidate.update({"speaker": subject, "speaker_kind": kind})
            else:
                candidate.update({"source": subject, "source_kind": kind})
            if best is None or candidate["confidence"] > best["confidence"]:
                best = candidate
    return best


def _coordinated_followup_candidates(sentence: str, primary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Odzyskuje dalsze jawne akty mowy z tego samego zdania.

    Główny resolver celowo wybiera jednego najlepszego kandydata. Artykuły
    często mają jednak konstrukcję ``X powiedział ..., i dodał ...`` albo
    ``X powiedział ...; Y podkreślił ...``. Ta wąska ścieżka dopuszcza tylko
    koordynację albo pełny podmiot po granicy klauzy, więc nie awansuje
    czasownika z wnętrza zwykłej treści ``X powiedział, że Y zrobił``.
    """
    matches = list(ACTION_RE.finditer(sentence))
    if len(matches) < 2:
        return []
    primary_speaker = _clean(primary.get("speaker"))
    primary_kind = _clean(primary.get("speaker_kind"))
    primary_source = _clean(primary.get("source"))
    primary_source_kind = _clean(primary.get("source_kind"))
    if not primary_speaker and not primary_source:
        return []

    out: List[Dict[str, Any]] = []
    primary_signature = (
        primary_speaker.casefold(), _clean(primary.get("action")).casefold(),
        _clean(primary.get("claim")).casefold(),
    )
    skipped_primary_action = False
    for index, match in enumerate(matches):
        action = _clean(match.group(1)).casefold()
        if not skipped_primary_action and action == _clean(primary.get("action")).casefold():
            skipped_primary_action = True
            continue
        left = sentence[:match.start()]
        # Cudzysłów otwarty przed czasownikiem oznacza zwykle treść cytatu,
        # nie drugi akt atrybucji w zdaniu redakcyjnym.
        if (left.count('"') + left.count('„') - left.count('”')) % 2:
            continue

        coordinated = bool(re.search(
            r"(?:[,;]\s*(?:i|oraz|a|następnie|ponadto|dodatkowo|po\s+czym)\s*|\bi\s*)$",
            left,
            re.I,
        ))
        clause_boundary = max(left.rfind(";"), left.rfind("."), left.rfind("!"), left.rfind("?"))
        clause_prefix = left[clause_boundary + 1:].strip(" ,:;–—-")
        # Jeżeli kolejny czasownik leży wewnątrz treści wprowadzonej przez
        # ``że/czy/gdyby``, wcześniejszy mówca nie może zostać odziedziczony.
        # Podmiot musi być jawny w samej klauzie podrzędnej. Zachowujemy
        # prawdziwą koordynację ``..., i dodał ...``.
        subordinate_markers = list(re.finditer(r"\b(?:że|iż|czy|gdyby|aby|żeby)\b", clause_prefix, re.I))
        inside_subordinate = bool(subordinate_markers) and not coordinated
        if inside_subordinate:
            clause_prefix = clause_prefix[subordinate_markers[-1].end():].strip(" ,:;–—-")
        clause_prefix = re.sub(r"^(?:a|i|natomiast|z\s+kolei|tymczasem)\s+", "", clause_prefix, flags=re.I)
        explicit_subject, explicit_kind = _subject_before(clause_prefix) if clause_prefix else ("", "")

        if inside_subordinate and not explicit_subject:
            continue

        if explicit_subject:
            speaker, kind = explicit_subject, explicit_kind
            source, source_kind = "", ""
            if kind == "medium":
                source, source_kind, speaker, kind = speaker, "medium", "", ""
        elif coordinated:
            speaker, kind = primary_speaker, primary_kind
            source, source_kind = primary_source, primary_source_kind
        else:
            continue

        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(sentence)
        claim_raw = sentence[match.end():next_start]
        claim = _claim_from_attribution(claim_raw)
        if len(claim.split()) < 2:
            continue
        signature = (speaker.casefold(), action, claim.casefold())
        if signature == primary_signature:
            continue
        previous_gender = _action_gender(primary.get("action"))
        current_gender = _action_gender(action)
        if not explicit_subject and previous_gender and current_gender and previous_gender != current_gender:
            continue
        item = {
            **_empty(), "matched": True, "speaker": speaker, "speaker_kind": kind,
            "source": source, "source_kind": source_kind, "action": action,
            "claim": claim, "target": _target(sentence, speaker if kind == "person" else "", claim),
            "confidence": 0.93 if explicit_subject else 0.89,
            "method": "coordinated_explicit_attribution" if explicit_subject else "coordinated_same_speaker_attribution",
            "warnings": [] if explicit_subject else ["speaker_resolved_from_coordinated_clause"],
        }
        if not any(
            _clean(row.get("speaker")).casefold() == speaker.casefold()
            and _clean(row.get("action")).casefold() == action
            and _clean(row.get("claim")).casefold() == claim.casefold()
            for row in out
        ):
            out.append(item)
    return out


INTRODUCTORY_CLAIM_RE = re.compile(
    r'^(?:w|we)\s+(?:["„][^"”]+["”]\s+)?(?:programie|audycji|studiu)?\s*(?:o\s+sprawie|sprawę|informacje\s+o|o\s+inwigilacji|o\s+Pegasusie|w\s+TVN24)?$',
    re.I,
)


def _is_introductory_claim(claim: str) -> bool:
    value = _clean(claim).strip(" .,:;–—-")
    if not value:
        return True
    if INTRODUCTORY_CLAIM_RE.match(value):
        return True
    low = value.casefold()
    return low.startswith("w programie o sprawie") or low.startswith("w programie informacje o") or low in {"faktach po faktach", "w faktach po faktach"}


def _focus_score(sentence: str, focus_phrase: str) -> float:
    if not focus_phrase:
        return 0.0
    s, f = sentence.casefold(), _clean(focus_phrase).casefold()
    if not f:
        return 0.0
    if f in s:
        return 4.0
    words = [w for w in re.findall(r"\w+", f) if len(w) > 3]
    if not words:
        return 0.0
    return sum(1 for w in words if w in s) / max(1, len(words)) * 3.0


def _lookahead_trailing_person(
    sentences: List[str], start_index: int, aliases: Dict[str, str], *, max_ahead: int = 2
) -> Dict[str, Any] | None:
    """Szuka podpisu mówcy na końcu krótkiego, wielozdaniowego cytatu.

    Korpus prasowy często ma układ „- zdanie. Drugie zdanie. Trzecie - mówił X”.
    Nie wolno wtedy odziedziczyć poprzedniego rozmówcy. Patrzymy najwyżej dwa
    zdania naprzód i wymagamy jawnego, nazwanego podpisu osoby.
    """
    stop = min(len(sentences), start_index + max_ahead + 1)
    for idx in range(start_index + 1, stop):
        future = sentences[idx]
        candidate = _special_explicit_candidate(future, aliases)
        if (
            candidate
            and _clean(candidate.get("speaker"))
            and _clean(candidate.get("speaker_kind")) == "person"
            and _clean(candidate.get("method")) in {
                "trailing_surname_explicit_alias",
                "quote_role_program_medium_explicit_speaker",
            }
        ):
            return candidate
        # Jawna, lecz nierozwiązana atrybucja po drodze zamyka bezpieczny lookahead.
        if ATTRIBUTION_SIGNAL_RE.search(future):
            break
    return None


def resolve_structural_relation_bundle(*parts: Any, segments: List[Dict[str, Any]] | None = None) -> Dict[str, List[Dict[str, Any]]]:
    text = "\n".join(str(p or "") for p in parts if str(p or "").strip())
    if not _clean(text):
        return {"relations": [], "rejections": []}

    relations: List[Dict[str, Any]] = []
    rejections: List[Dict[str, Any]] = []
    blocks = _blocks_from_segments(segments) if segments is not None else list(_blocks(text))
    document_texts: Dict[str, str] = {}
    for doc_id, _doc_index, _bi, doc_sentences in blocks:
        document_texts[doc_id] = (document_texts.get(doc_id, "") + " " + " ".join(doc_sentences)).strip()
    aliases_by_document = {doc_id: _person_aliases(doc_text) for doc_id, doc_text in document_texts.items()}

    for document_id, document_index, bi, sentences in blocks:
        aliases = aliases_by_document.get(document_id, {})
        # Granica akapitu/bloku jest twardą barierą koreferencji mówcy.
        # Nie przenosimy osoby, roli ani quote-state do następnego akapitu.
        # Źródło redakcyjne również nie jest używane do wymuszania mówcy.
        active_speaker: Dict[str, Any] | None = None
        active_speaker_index = -99
        last_speaker_context: Dict[str, Any] | None = None
        last_speaker_index = -99
        last_person_speaker_context: Dict[str, Any] | None = None
        last_person_speaker_index = -99
        last_unresolved_attribution_index = -99
        active_source = ""
        active_source_kind = ""
        active_source_sentence = ""
        active_source_index = -99
        source_quote_active = False
        role_person_context: Dict[str, Dict[str, Any]] = {}
        # Quote-state jest lokalny dla jednego akapitu. Dzięki temu ``Wrzosek:``
        # może objąć kolejne zdania tej samej wypowiedzi, ale stan nie przecieka
        # do innego akapitu ani dokumentu.
        quote_speaker: Dict[str, Any] | None = None
        quote_budget = 3

        for si, sentence in enumerate(sentences):
            scope = "same_block"
            role_seed = _role_seed_candidate(sentence, role_person_context)
            if role_seed is not None and (active_speaker is None or active_speaker_index < 0):
                contextual = role_seed
            else:
                contextual = _contextual_attribution_candidate(sentence, active_speaker, scope=scope)
            if contextual is None and role_seed is not None:
                contextual = role_seed
            if contextual is None and last_speaker_context and si - last_speaker_index <= 8:
                is_anaphoric = bool(
                    ANAPHORIC_START_RE.match(sentence) or ANAPHORIC_END_RE.match(sentence)
                    or ANAPHORIC_TRAILING_RE.match(sentence) or PRONOUN_ATTRIBUTION_RE.match(sentence)
                    or ROLE_ONLY_ATTRIBUTION_RE.match(sentence) or ANAPHORIC_JAK_RE.match(sentence)
                    or BARE_PASSIVE_ACTION_CONTINUATION_RE.match(sentence) or ROLE_DESCRIPTOR_END_RE.match(sentence)
                )
                if is_anaphoric and last_unresolved_attribution_index <= last_speaker_index:
                    contextual = _contextual_attribution_candidate(sentence, last_speaker_context, scope=scope)
            if contextual is None and last_person_speaker_context and si - last_person_speaker_index <= 8:
                is_anaphoric = bool(
                    ANAPHORIC_START_RE.match(sentence) or ANAPHORIC_END_RE.match(sentence)
                    or ANAPHORIC_TRAILING_RE.match(sentence) or ROLE_DESCRIPTOR_END_RE.match(sentence)
                    or PRONOUN_ATTRIBUTION_RE.match(sentence) or ROLE_ONLY_ATTRIBUTION_RE.match(sentence)
                    or ANAPHORIC_JAK_RE.match(sentence) or BARE_PASSIVE_ACTION_CONTINUATION_RE.match(sentence)
                )
                if is_anaphoric:
                    contextual = _contextual_attribution_candidate(sentence, last_person_speaker_context, scope=scope)
            # Jawny sygnał zmiany tury: „Sroka przerwała”, po którym następuje
            # cytat zakończony żeńskim/męskim czasownikiem. To dowód lokalny,
            # nie przypadkowa wzmianka o osobie.
            if si > 0 and (ANAPHORIC_END_RE.match(sentence) or ANAPHORIC_TRAILING_RE.match(sentence)):
                turn = re.search(r"\b(?:przerwał|przerwała|odpowiedział|odpowiedziała)\b", sentences[si - 1], re.I)
                if turn:
                    names_before_turn = re.findall(rf"\b({CAP_TOKEN})\b", sentences[si - 1][:turn.start()])
                    surname = _clean(names_before_turn[-1]) if names_before_turn else ""
                    person = _expand_person_alias(surname, aliases)
                    if person and len(person.split()) >= 2 and person.casefold() != surname.casefold():
                        seed = {"speaker": person, "speaker_kind": "person", "source": "", "source_kind": "", "sentence": sentences[si - 1], "action": _clean(turn.group(0)).casefold()}
                        contextual = _contextual_attribution_candidate(sentence, seed, scope="same_block")
            # Deskryptor końcowy („powiedział były dyrektor”) może wrócić do
            # jedynej osoby będącej jawnym podmiotem bezpośrednio poprzedniego
            # zdania. Ta wąska reguła nie obejmuje zwykłego „- wskazywał” i nie
            # przyjmuje osób z dopełnień typu „przez X” / „pod rządami X”.
            if contextual is None and ROLE_DESCRIPTOR_END_RE.match(sentence) and si > 0:
                prev = sentences[si - 1]
                subject_match = re.match(rf"^(?P<person>{CAP_TOKEN}\s+{CAP_TOKEN}(?:\s+{CAP_TOKEN})?)\s+\w+", prev)
                if subject_match:
                    prev_person = _valid_person_candidate(subject_match.group("person"))
                    if prev_person:
                        seed = {"speaker": _expand_person_alias(prev_person, aliases), "speaker_kind": "person", "source": "", "source_kind": "", "sentence": prev, "action": ""}
                        contextual = _contextual_attribution_candidate(sentence, seed, scope="same_block")
            # Sama obecność jednej osoby w poprzednim zdaniu nie jest dowodem,
            # że ta osoba wypowiada następne zdanie. Speaker-state może pochodzić
            # wyłącznie z wcześniejszej jawnej atrybucji/roli/quote-state.

            continuation = bool(
                contextual and (
                    ANAPHORIC_START_RE.match(sentence)
                    or ANAPHORIC_END_RE.match(sentence)
                    or ANAPHORIC_TRAILING_RE.match(sentence)
                    or ROLE_CONTINUATION_RE.match(sentence)
                    or ROLE_ACTION_CONTINUATION_RE.match(sentence)
                    or BARE_PASSIVE_ACTION_CONTINUATION_RE.match(sentence)
                    or PRONOUN_ATTRIBUTION_RE.match(sentence)
                    or ROLE_ONLY_ATTRIBUTION_RE.match(sentence)
                    or ANAPHORIC_JAK_RE.match(sentence)
                    or ROLE_DESCRIPTOR_END_RE.match(sentence)
                )
            )
            special = _special_explicit_candidate(sentence, aliases)
            context_intro = _speaker_context_candidate(sentence, aliases)
            generic_explicit = _explicit_candidate(sentence)
            # Najpierw ustalamy jawny podmiot gramatyczny bieżącego zdania.
            # Dziedziczenie jest wyłącznie fallbackiem i nigdy nie może wygrać
            # z nową osobą / jawnym podmiotem w tym samym zdaniu.
            trailing_local_attribution = bool(
                contextual and (ANAPHORIC_END_RE.match(sentence) or ANAPHORIC_TRAILING_RE.match(sentence))
            )
            # Gdy zdanie kończy się lokalnym podpisem typu „- stwierdziła / - dodał”,
            # ten podpis opisuje autora całej wypowiedzi. Podmiot wewnętrznej
            # klauzy („Amnesty International potwierdziło, że ... - stwierdziła”)
            # jest źródłem przywołanym w treści, a nie głównym mówcą. Jawny
            # podpis z nazwiskiem nadal ma pierwszeństwo przez ``special``.
            if trailing_local_attribution and special is None:
                explicit = contextual
            else:
                explicit = special or context_intro or generic_explicit or (contextual if continuation else None) or contextual

            # Current quote-state: po jawnym ``Nazwisko:`` jedno kolejne zdanie
            # bez nowej atrybucji pozostaje częścią tego samego cytatu. Stan
            # nigdy nie przechodzi przez granicę dokumentu i jest kasowany
            # przez nową jawną atrybucję.
            quote_like_continuation = bool(
                # Myślnik dialogowy, ale nie zwykłe dopowiedzenie typu
                # „- właściciela agencji …”. Nagłówki zaczynające się cudzysłowem
                # również nie są automatycznie wypowiedzią poprzedniego mówcy.
                re.match(r'^[\s]*[-–—]\s*(?:[A-ZĄĆĘŁŃÓŚŹŻ]|[„"“])', sentence)
                or re.match(
                    r'^(?:Ja|My|Nie|To|Tak|Do|Uważam|Sądzę|Chcę|Mam|Moim|Naszym|'
                    r'Zobaczymy|Czyli|Będziemy|Jesteśmy|Wiemy|Proszę)\b',
                    sentence, re.I,
                )
            )
            inherited_explicit = _clean((explicit or {}).get("method")) in {
                "same_block_role_or_pronoun_attribution", "same_block_previous_explicit_speaker"
            }
            forward_speaker = (
                _lookahead_trailing_person(sentences, si, aliases)
                if (explicit is None or inherited_explicit) and quote_like_continuation and not ATTRIBUTION_SIGNAL_RE.search(sentence)
                else None
            )
            if (explicit is None or inherited_explicit) and forward_speaker is not None:
                bare_claim = _claim_from_attribution(sentence)
                if bare_claim and len(bare_claim.split()) >= 3:
                    explicit = {
                        **_empty(), "matched": True, "speaker": _clean(forward_speaker.get("speaker")),
                        "speaker_kind": "person", "source": _clean(forward_speaker.get("source")),
                        "source_kind": _clean(forward_speaker.get("source_kind")), "action": "",
                        "attribution_marker": "podpis w następnym zdaniu", "claim": bare_claim,
                        "target": _target(sentence, _clean(forward_speaker.get("speaker")), bare_claim),
                        "confidence": 0.92, "method": "forward_quote_signature_attribution",
                        "warnings": ["speaker_resolved_from_following_explicit_signature"],
                        "coreference_scope": "same_block", "coreference_score": 0.92,
                    }

            # Cytat medium może obejmować wiele zdań. Gdy jawne źródło
            # rozpoczęło cytowany akapit, kolejne zdania pozostają relacją
            # źródłową i nie dziedziczą ostatniej osoby wspomnianej w tekście.
            begins_source_quote = bool(re.match(r'^[\s]*["„“]', sentence))
            inherited_explicit = _clean((explicit or {}).get("method")) in {
                "same_block_role_or_pronoun_attribution", "same_block_previous_explicit_speaker"
            }
            if active_source and si - active_source_index <= 8 and (source_quote_active or begins_source_quote) and (
                explicit is None or inherited_explicit or (begins_source_quote and _clean((explicit or {}).get("source")) != active_source)
            ):
                bare_claim = _claim_from_attribution(sentence)
                if bare_claim and len(bare_claim.split()) >= 3:
                    explicit = {
                        **_empty(), "matched": True, "speaker": "", "speaker_kind": "",
                        "source": active_source, "source_kind": active_source_kind,
                        "action": "", "attribution_marker": "kontynuacja cytatu źródła",
                        "claim": bare_claim, "target": _target(sentence, "", bare_claim),
                        "confidence": 0.91, "method": "source_quote_continuation",
                        "warnings": ["source_continuation_same_block"],
                    }
                    source_quote_active = True

            if (
                explicit is None and quote_speaker and quote_budget > 0
                and quote_like_continuation and not ATTRIBUTION_SIGNAL_RE.search(sentence)
                and not ACTION_RE.search(sentence)
            ):
                bare_claim = _claim_from_attribution(sentence)
                if bare_claim and len(bare_claim.split()) >= 3:
                    explicit = {
                        **_empty(), "matched": True, "speaker": _clean(quote_speaker.get("speaker")),
                        "speaker_kind": _clean(quote_speaker.get("speaker_kind")) or "person",
                        "source": _clean(quote_speaker.get("source")), "source_kind": _clean(quote_speaker.get("source_kind")),
                        "action": "", "attribution_marker": "kontynuacja cytatu", "claim": bare_claim,
                        "target": _target(sentence, _clean(quote_speaker.get("speaker")), bare_claim),
                        "confidence": 0.90, "method": "same_block_role_or_pronoun_attribution",
                        "warnings": ["speaker_inherited_from_previous_sentence"],
                        "coreference_scope": "same_block", "coreference_score": 0.90,
                    }
                    quote_budget -= 1
            if explicit:
                item = dict(explicit)
                if item.get("speaker") and _clean(item.get("speaker_kind")) == "person":
                    item["speaker"] = _expand_person_alias(_clean(item.get("speaker")), aliases)
                if item.get("target"):
                    item["target"] = _expand_person_alias(_clean(item.get("target")), aliases)

                if item.get("source"):
                    active_source = _clean(item.get("source"))
                    active_source_kind = _clean(item.get("source_kind"))
                    active_source_sentence = sentence
                    active_source_index = si
                    # Jawne źródło otwiera nowy stan dyskursu i wygasza osobę,
                    # która była mówcą wcześniejszego fragmentu.
                    if not item.get("speaker"):
                        active_speaker = None
                        quote_speaker = None
                        quote_budget = 0
                elif item.get("speaker") and active_source and si - active_source_index <= 1:
                    item["source"] = active_source
                    item["source_kind"] = active_source_kind
                    item["context_sentence"] = active_source_sentence

                if item.get("speaker") and active_speaker and _clean(active_speaker.get("speaker")).casefold() == _clean(item.get("speaker")).casefold():
                    if not item.get("context_sentence"):
                        item["context_sentence"] = _clean(active_speaker.get("context_sentence") or active_speaker.get("sentence"))
                item.update({"sentence": sentence, "document_id": document_id, "document_index": document_index, "block_index": bi, "sentence_index": si})
                if not item.get("claim"):
                    rejections.append({"sentence": sentence, "reason": "empty_claim", "method": item.get("method", "")})
                elif not item.get("speaker") and not item.get("source"):
                    rejections.append({"sentence": sentence, "reason": "unresolved_attribution_source", "method": item.get("method", "")})
                elif item.get("speaker") and (item.get("context_only") or _is_introductory_claim(_clean(item.get("claim")))):
                    item["context_only"] = True
                    item["context_sentence"] = sentence
                    active_speaker = item
                    active_speaker_index = si
                    last_speaker_context = item
                    last_speaker_index = si
                    if _clean(item.get("speaker_kind")) == "person":
                        last_person_speaker_context = item
                        last_person_speaker_index = si
                    quote_speaker = dict(item)
                    quote_budget = 6
                else:
                    if item.get("speaker") and _clean(item.get("speaker_kind")) in {"person", "institution", "party"}:
                        active_speaker = item
                        active_speaker_index = si
                        last_speaker_context = item
                        last_speaker_index = si
                        if _clean(item.get("speaker_kind")) == "person":
                            last_person_speaker_context = item
                            last_person_speaker_index = si
                        method_name = _clean(item.get("method"))
                        inherited_methods = {"same_block_role_or_pronoun_attribution"}
                        # Silna jawna atrybucja osoby rozpoczyna lokalny stan wypowiedzi.
                        # Dzięki temu kolejne zdania dialogu bez podpisu (np. po „Zembaczyński
                        # mówił…”) nie dziedziczą wcześniejszego rozmówcy. Stan pozostaje
                        # ograniczony do bieżącego bloku i przepuszcza tylko formy cytatowe.
                        opens_quote_state = not bool(re.match(r"^Autor(?:ka)?\s+publikacji\b", sentence, re.I))
                        if method_name not in inherited_methods and opens_quote_state:
                            quote_speaker = dict(item)
                            quote_budget = 6
                        elif quote_speaker and _clean(quote_speaker.get("speaker")).casefold() == _clean(item.get("speaker")).casefold():
                            quote_budget = max(quote_budget, 4)
                    relations.append(item)
                    for extra in _coordinated_followup_candidates(sentence, item):
                        extra.update({
                            "sentence": sentence,
                            "document_id": document_id,
                            "document_index": document_index,
                            "block_index": bi,
                            "sentence_index": si,
                        })
                        if not any(
                            _clean(row.get("speaker")).casefold() == _clean(extra.get("speaker")).casefold()
                            and _clean(row.get("source")).casefold() == _clean(extra.get("source")).casefold()
                            and _clean(row.get("action")).casefold() == _clean(extra.get("action")).casefold()
                            and _clean(row.get("claim")).casefold() == _clean(extra.get("claim")).casefold()
                            for row in relations
                        ):
                            relations.append(extra)
                    if source_quote_active and re.search(r'["”]\s*(?:[-–—].*)?[.!?]*$', sentence):
                        source_quote_active = False
            elif ATTRIBUTION_SIGNAL_RE.search(sentence):
                last_unresolved_attribution_index = si
                rejections.append({"sentence": sentence, "reason": "unresolved_attribution", "method": "signal_without_relation"})

            for _role, _person in _role_person_mentions(sentence, aliases):
                role_person_context[_role] = {
                    "speaker": _person, "speaker_kind": "person", "source": "", "source_kind": "",
                    "sentence": sentence, "action": "", "document_id": document_id,
                    "block_index": bi, "sentence_index": si,
                }

            # W tym samym akapicie pamięć podstawowa pozostaje krótka. Stan
            # dokumentowy na następny akapit jest zapisywany osobno niżej.
            # Current: stan mówcy żyje dłużej wewnątrz jednego bloku, ale jest
            # używany wyłącznie przy jawnej anaforze/czasowniku raportującym.
            # Dzięki temu wielozdaniowy cytat nie traci autora, a zwykła wzmianka
            # o innej osobie nie przejmuje stanu.
            if active_speaker and active_speaker_index >= 0 and si - active_speaker_index > 8:
                active_speaker = None

    return {"relations": relations, "rejections": rejections}


def resolve_structural_relations(*parts: Any) -> List[Dict[str, Any]]:
    return resolve_structural_relation_bundle(*parts)["relations"]


def resolve_structural_relation(*parts: Any, focus_phrase: str = "") -> Dict[str, Any]:
    bundle = resolve_structural_relation_bundle(*parts)
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for item in bundle["relations"]:
        score = float(item.get("confidence") or 0.0) + _focus_score(_clean(item.get("sentence")), focus_phrase)
        candidates.append((score, item))
    if focus_phrase:
        candidates = [row for row in candidates if _focus_score(_clean(row[1].get("sentence")), focus_phrase) >= 0.75]
    if not candidates:
        return _empty()
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][1]
