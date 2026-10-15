from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .semantic_entity_filter import filter_entity_dicts, validate_entity_candidate
from .entity_role_policy import is_public_entity_name, strip_person_title

CAP_WORD = r"[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż’\'-]+"
PERSON_RE = re.compile(rf"\b({CAP_WORD}\s+{CAP_WORD}(?:\s+{CAP_WORD})?)\b")
PERSON_2_OVERLAP_RE = re.compile(rf"(?=(\b{CAP_WORD}\s+{CAP_WORD}\b))")
PERSON_3_OVERLAP_RE = re.compile(rf"(?=(\b{CAP_WORD}\s+{CAP_WORD}\s+{CAP_WORD}\b))")
INITIAL_PERSON_RE = re.compile(
    rf"\b(?P<name>{CAP_WORD}\s+[A-ZĄĆĘŁŃÓŚŹŻ]\.)"
    rf"(?=\s+(?:powied\w*|stwierdz\w*|ocen\w*|zaprzecz\w*|odpowiedz\w*|"
    rf"przekaz\w*|dod\w*|zaznacz\w*|przyzn\w*|wyjaśn\w*|poinform\w*|"
    rf"oświadcz\w*|mówi\w*|zezn\w*|zatrzym\w*|oskarż\w*|areszt\w*))",
    re.I,
)
REVERSED_INITIAL_PERSON_RE = re.compile(
    rf"\b(?P<name>[A-ZĄĆĘŁŃÓŚŹŻ]\.\s+{CAP_WORD})"
    rf"(?=\s+(?:powied\w*|stwierdz\w*|ocen\w*|zaprzecz\w*|odpowiedz\w*|"
    rf"przekaz\w*|dod\w*|zaznacz\w*|przyzn\w*|wyjaśn\w*|poinform\w*|"
    rf"oświadcz\w*|mówi\w*|zezn\w*|zatrzym\w*|oskarż\w*|areszt\w*))",
    re.I,
)
EDITORIAL_SPLIT_PERSON_RE = re.compile(
    rf"\([^)]*?\b(?P<given>{CAP_WORD}(?:\s+{CAP_WORD}){{1,2}})\s*[-–—]\s*red\.?(?:[^)]*)\)\s*(?P<surname>{CAP_WORD})",
    re.I,
)

TITLE_WORDS = {
    "mecenas", "minister", "ministra", "wiceminister", "wiceministra", "poseł", "posłanka",
    "senator", "senatorka", "prezydent", "premier", "szef", "szefowa", "rzecznik",
    "rzeczniczka", "przewodniczący", "przewodnicząca", "wiceprzewodniczący",
    "wiceprzewodnicząca", "reporter", "reporterka", "dziennikarz", "dziennikarka",
    "redaktor", "redaktorka", "prokurator", "prokuratorka", "sędzia", "sędzina",
    "pan", "pani", "przedstawiciel", "przedstawicielka",
    "marszałek", "wicemarszałek", "lider", "liderka", "prezes", "prezeska",
}
BAD_PERSON_FIRST = {
    "Biały", "Białego", "Białym", "New", "Gazeta", "Europejski", "Trybunał",
    "Ministerstwo", "Ministerstwie", "Ministerstwa", "Prokuratura", "Prokuraturze",
    "Najwyższa", "Fakty", "Inwigilacja", "Źródło", "Autorka", "Autor", "Telefon",
    "Zdaniem", "Według", "Dane", "Agenci", "Potwierdzają", "Ewidentnie", "Miało",
    "Nie", "Link", "Rządowa", "Spółki", "Biuro", "Biura", "Komisja", "Komisji",
    "Agencja", "Agencji", "Sąd", "Sądu", "Kancelaria", "Kancelarii", "Urząd", "Urzędu",
    "Zachowanie", "Postępowanie", "Sprawa", "Wniosek", "Wydarzenia",
    "Fundusz", "Funduszu", "Uniwersytet", "Uniwersytecie", "To", "Wtedy", "Ma", "Najpierw", "Raz",
    "Platformy", "Obywatelskiej", "Koalicji", "Prawa", "Unii", "Europejskiej", "Belkę",
    "Europie", "Europa", "Zachodniej", "Pan", "Pani", "Przedstawiciel",
    "Przedstawicielka", "Nowej", "Lewicy", "Instytut", "Instytucie", "Instytutu",
    "Zakład", "Zakładu", "Kryminologii", "Karnego", "Suwerennej", "Polski",
    "Stanach", "Zjednoczonych", "Skarbu", "Centralna", "Pałac",
    "Wicemarszałek", "Marszałek", "Lider", "Security", "Amnesty", "Poczta",
    "Rada", "Rady", "Pakt", "Paktu", "Amber", "Stowarzyszenie", "Stowarzyszenia", "Fundacja", "Fundacji",
}
INSTITUTION_PREFIX_RE = re.compile(
    r"^(?:ministerstw\w*|agencj\w*|biur\w*|spółk\w*|sad\w*|sąd\w*|komisj\w*|"
    r"urz\w*|kancelari\w*|trybunał\w*|prokuratur\w*|sejm\w*|senat\w*|fundusz\w*|stowarzysz\w*|fundacj\w*|związk\w*|uniwersytet\w*|pałac\w*|rada\w*|poczt\w*)$",
    re.I,
)
DYNAMIC_INSTITUTION_RE = re.compile(
    rf"\b(?P<name>(?:Biuro|Biura|Agencja|Agencji|Komisja|Komisji|Kancelaria|Kancelarii|"
    rf"Urząd|Urzędu|Sąd|Sądu|Spółka|Spółki|Ministerstwo|Ministerstwie|Prokuratura|Prokuraturze|Fundusz|Funduszu|Stowarzyszenie|Stowarzyszenia|Fundacja|Fundacji|Związek|Związku|Uniwersytet|Uniwersytecie|Rada|Rady|Poczta)"
    rf"(?:\s+(?:{CAP_WORD}|i|oraz|ds\.)){{1,5}}"
    rf"(?:\s+do\s+spraw(?:\s+[a-ząćęłńóśźż-]+){{1,8}})?)\b"
)

# Organizacje, których nazwa własna nie zaczyna się słowem typu „Urząd”,
# ale ma jednoznaczną głowę organizacyjną na końcu. Rejestrujemy je jako
# institution, żeby nie mogły wejść do rejestru PERSON tylko przez wielkie litery.
DYNAMIC_ORGANIZATION_RE = re.compile(
    rf"\b(?P<name>{CAP_WORD}(?:\s+{CAP_WORD}){{0,4}}\s+(?:Holding|Group|Lab|Laboratory|International|Foundation|Association|Institute))\b"
)

# Current: lokalizacja nie może być domyślnie osobą tylko dlatego, że składa się
# z dwóch słów zapisanych wielką literą. Rejestrujemy jawny lokalny span po
# przyimku lokatywnym jako PLACE i maskujemy go przed skanerem PERSON.
DYNAMIC_PLACE_RE = re.compile(
    rf"\b(?i:w|we|na|przy|pod|nad)\s+(?P<name>{CAP_WORD}(?:\s+{CAP_WORD}){{0,3}})\b"
)

# Nazwy mediów spoza statycznego słownika są wiarygodne, gdy występują po
# jawnym deskryptorze typu „dziennik”, „portal”, „serwis”. Dzięki temu tytuł
# medium nie może wejść do rejestru osób.
DYNAMIC_MEDIA_RE = re.compile(
    rf"\b(?:dziennik(?:a|u)?|gazet(?:a|y|ą)|portal(?:u|em)?|serwis(?:u|em)?|radio|radiu|telewizj(?:a|i)|tygodnik(?:a|u)?|miesięcznik(?:a|u)?)\s+"
    rf"[\"„]?(?P<name>{CAP_WORD}(?:\s+{CAP_WORD}){{0,4}})[\"”]?",
    re.I,
)

# Kontrolowane encje. Skróty są aliasami pełnej nazwy, nigdy osobnym kanonem.
ENTITY_SPECS: tuple[dict[str, Any], ...] = (
    # media
    {"type": "medium", "canonical": "New York Times", "aliases": ()},
    {"type": "medium", "canonical": "Gazeta Wyborcza", "aliases": ("Gazecie Wyborczej", "Gazety Wyborczej", "Wyborcza", "Wyborczej", "GW")},
    {"type": "medium", "canonical": "TVN24", "aliases": ()},
    {"type": "medium", "canonical": "PAP", "aliases": ()},
    {"type": "medium", "canonical": "Associated Press", "aliases": ("AP",)},
    {"type": "medium", "canonical": "RMF FM", "aliases": ()},
    {"type": "medium", "canonical": "Radio ZET", "aliases": ("Radiu ZET", "Radiu Zet")},
    {"type": "medium", "canonical": "Program Pierwszy Polskiego Radia", "aliases": ("Programie Pierwszym Polskiego Radia", "Program Pierwszy PR", "Jedynka")},
    {"type": "medium", "canonical": "Polsat", "aliases": ()},
    {"type": "medium", "canonical": "Onet", "aliases": ()},
    {"type": "medium", "canonical": "Interia", "aliases": ("Interii", "Interią")},
    {"type": "medium", "canonical": "Super Express", "aliases": ("Super Expressem", "Super Expressowi")},
    {"type": "medium", "canonical": "Gazeta Polska Codziennie", "aliases": ("Gazety Polskiej Codziennie", "Gazecie Polskiej Codziennie", "Polskiej Codziennie")},
    {"type": "medium", "canonical": "TV Republika", "aliases": ("Telewizja Republika", "Republika")},
    {"type": "medium", "canonical": "TVN", "aliases": ()},
    {"type": "medium", "canonical": "Reuters", "aliases": ()},
    {"type": "medium", "canonical": "Haaretz", "aliases": ("Haarec",)},
    {"type": "medium", "canonical": "Kalkalist", "aliases": ("Calcalist", "Kalkalista")},
    # instytucje
    {"type": "institution", "canonical": "Biały Dom", "aliases": ()},
    {"type": "institution", "canonical": "Europejski Trybunał Praw Człowieka", "aliases": ()},
    {"type": "institution", "canonical": "Europejska Konwencja Praw Człowieka", "aliases": ("Europejskiej Konwencji Praw Człowieka", "Konwencji Praw Człowieka")},
    {"type": "institution", "canonical": "Trybunał Konstytucyjny", "aliases": ("TK", "Trybunału Konstytucyjnego", "Trybunał Konstytucyjny Julii Przyłębskiej", "Trybunału Konstytucyjnego Julii Przyłębskiej")},
    {"type": "institution", "canonical": "Ministerstwo Sprawiedliwości", "aliases": ("Ministerstwa Sprawiedliwości", "Ministerstwie Sprawiedliwości")},
    {"type": "institution", "canonical": "Ministerstwo Finansów", "aliases": ("Ministerstwa Finansów", "Ministerstwie Finansów", "resort finansów")},
    {"type": "institution", "canonical": "Fundusz Sprawiedliwości", "aliases": ("Funduszu Sprawiedliwości",)},
    {"type": "institution", "canonical": "Fundusz Pomocy Pokrzywdzonym", "aliases": ("Funduszu Pomocy Pokrzywdzonym",)},
    {"type": "institution", "canonical": "Komisja Finansów Publicznych", "aliases": ("Komisji Finansów Publicznych",)},
    {"type": "institution", "canonical": "Ministerstwo Spraw Zagranicznych", "aliases": ()},
    {"type": "institution", "canonical": "Ministerstwo Spraw Wewnętrznych i Administracji", "aliases": ()},
    {"type": "institution", "canonical": "Rządowa Agencja Rezerw Strategicznych", "aliases": ("RARS",)},
    {"type": "institution", "canonical": "Spółki Skarbu Państwa", "aliases": ()},
    {"type": "institution", "canonical": "Najwyższa Izba Kontroli", "aliases": ("NIK", "Najwyższej Izby Kontroli")},
    {"type": "institution", "canonical": "Prokuratura Krajowa", "aliases": ("Prokuratury Krajowej", "Prokuraturze Krajowej")},
    {"type": "institution", "canonical": "Prokuratura Okręgowa", "aliases": ()},
    {"type": "institution", "canonical": "Sejm", "aliases": ()},
    {"type": "institution", "canonical": "Senat", "aliases": ()},
    {"type": "institution", "canonical": "Komisja Europejska", "aliases": ("KE",)},
    {"type": "institution", "canonical": "Unia Europejska", "aliases": ("UE", "Unii Europejskiej")},
    {"type": "institution", "canonical": "FBI", "aliases": ()},
    {"type": "institution", "canonical": "ABW", "aliases": ("Agencja Bezpieczeństwa Wewnętrznego", "Agencji Bezpieczeństwa Wewnętrznego")},
    {"type": "institution", "canonical": "CBA", "aliases": ()},
    {"type": "institution", "canonical": "Citizen Lab", "aliases": ()},
    {"type": "institution", "canonical": "Amnesty International", "aliases": ("Amnesty International Security Lab",)},
    {"type": "institution", "canonical": "Poczta Polska", "aliases": ()},
    {"type": "institution", "canonical": "Rada Ministrów", "aliases": ("Rady Ministrów",)},
    {"type": "institution", "canonical": "Amber Gold", "aliases": ()},
    {"type": "institution", "canonical": "Kulczyk Holding", "aliases": ()},
    {"type": "institution", "canonical": "NSO Group", "aliases": ()},
    {"type": "institution", "canonical": "OpenAI", "aliases": ()},
    {"type": "institution", "canonical": "Orlen", "aliases": ("ORLEN",)},
    # partie
    {"type": "party", "canonical": "Prawo i Sprawiedliwość", "aliases": ("PiS",)},
    {"type": "party", "canonical": "Platforma Obywatelska", "aliases": ("PO",)},
    {"type": "party", "canonical": "Polskie Stronnictwo Ludowe", "aliases": ("PSL",)},
    {"type": "party", "canonical": "Koalicja Obywatelska", "aliases": ("KO",)},
    {"type": "party", "canonical": "Nowa Lewica", "aliases": ("Lewica", "Nowej Lewicy")},
    {"type": "party", "canonical": "Konfederacja", "aliases": ()},
    {"type": "party", "canonical": "Solidarna Polska", "aliases": ()},
    {"type": "party", "canonical": "Suwerenna Polska", "aliases": ("Suwerennej Polski",)},
    {"type": "party", "canonical": "Trzecia Droga", "aliases": ("TD", "PSL-TD", "PSL-Trzecia Droga", "PSL-Trzeciej Drogi")},
    {"type": "party", "canonical": "Sojusz Lewicy Demokratycznej", "aliases": ("SLD", "Sojuszu Lewicy Demokratycznej")},
    # produkty
    {"type": "product", "canonical": "Pegasus", "aliases": ()},
    {"type": "product", "canonical": "Phantom", "aliases": ()},
)

KNOWN_MEDIA = tuple(spec["canonical"] for spec in ENTITY_SPECS if spec["type"] == "medium")
KNOWN_INSTITUTIONS = tuple(spec["canonical"] for spec in ENTITY_SPECS if spec["type"] == "institution")
KNOWN_PARTIES = tuple(spec["canonical"] for spec in ENTITY_SPECS if spec["type"] == "party")
KNOWN_PRODUCTS = tuple(spec["canonical"] for spec in ENTITY_SPECS if spec["type"] == "product")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip(" ,:;–—-"))


def _ascii(value: str) -> str:
    value = value.translate(str.maketrans({"ł": "l", "Ł": "L"}))
    return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)).lower()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _ascii(value)).strip("_")


def _stem_token(token: str) -> str:
    t = _ascii(token)
    for suffix in ("owego", "owej", "emu", "owi", "ami", "ach", "ego", "iej", "ym", "im", "a", "u", "em", "ie", "y", "i"):
        if len(t) > len(suffix) + 3 and t.endswith(suffix):
            return t[:-len(suffix)]
    return t


def _signature(value: str) -> str:
    return " ".join(_stem_token(x) for x in re.findall(r"[\wąćęłńóśźż-]+", value, re.I))




def _person_token_stem(token: str) -> str:
    value = _ascii(token)
    # Najpierw końcówki przypadków, potem pojedyncza samogłoska końcowa.
    for suffix in ("owego", "owej", "emu", "owi", "ego", "ami", "ach", "ie", "em"):
        if len(value) > len(suffix) + 3 and value.endswith(suffix):
            value = value[:-len(suffix)]
            break
    if len(value) > 4 and value.endswith(("a", "y", "i", "u", "o")):
        value = value[:-1]
    return value


FIRST_NAME_CASE_MAP = {
    "jana": "jan", "michala": "michal", "jaroslawa": "jaroslaw", "pawla": "pawel",
    "zbigniewa": "zbigniew", "krzysztofa": "krzysztof", "przemyslawa": "przemyslaw",
    "wojciecha": "wojciech", "mateusza": "mateusz", "beniamina": "beniamin",
    "ernesta": "ernest", "witolda": "witold", "marcina": "marcin", "marka": "marek", "adama": "adam",
    "roberta": "robert", "piotra": "piotr", "tomasza": "tomasz", "andrzeja": "andrzej",
    "mariusza": "mariusz", "macieja": "maciej", "grzegorza": "grzegorz", "rafalem": "rafal",
    "anny": "anna", "katarzyny": "katarzyna", "joanny": "joanna", "ewy": "ewa",
}

# Konserwatywna normalizacja najczęstszych form osobowych pojawiających się
# w materiale publicystycznym. Nie stosujemy ogólnego „obcinania końcówek”,
# bo dla polskich nazwisk dawałoby ono fałszywe kanony. Forma z tekstu nadal
# zostaje aliasem/surface_form.
PERSON_TOKEN_NOMINATIVE = {
    "jana": "Jan", "michala": "Michał", "jaroslawa": "Jarosław", "pawla": "Paweł",
    "zbigniewa": "Zbigniew", "krzysztofa": "Krzysztof", "przemyslawa": "Przemysław",
    "wojciecha": "Wojciech", "mateusza": "Mateusz", "beniamina": "Beniamin",
    "ernesta": "Ernest", "witolda": "Witold", "marcina": "Marcin", "marka": "Marek", "adama": "Adam",
    "roberta": "Robert", "piotra": "Piotr", "tomasza": "Tomasz", "andrzeja": "Andrzej", "jacka": "Jacek",
    "mariusza": "Mariusz", "macieja": "Maciej", "grzegorza": "Grzegorz", "michalem": "Michał", "rafalem": "Rafał", "anite": "Anita",
    "marii": "Maria", "magdalene": "Magdalena", "magdaleny": "Magdalena", "arlete": "Arleta", "arlety": "Arleta", "beate": "Beata",
    "anny": "Anna", "katarzyny": "Katarzyna", "joanny": "Joanna", "ewy": "Ewa",
    "sebastiana": "Sebastian", "slawomira": "Sławomir", "tobiasza": "Tobiasz", "dariusza": "Dariusz", "donalda": "Donald", "jacka": "Jacek",
}
COMMON_GIVEN_NAMES = {
    "Adam", "Andrzej", "Anna", "Anita", "Arleta", "Beata", "Dariusz", "Donald", "Elżbieta",
    "Grażyna", "Grzegorz", "Jacek", "Jan", "Jarosław", "Krzysztof", "Magdalena", "Marcin",
    "Marek", "Marian", "Mariusz", "Mateusz", "Michał", "Mikołaj", "Monika", "Paweł", "Piotr", "Ryszard", "Tomasz", "Jakub",
    "Witold", "Wojciech", "Zbigniew", "Katarzyna", "Joanna", "Ewa", "Agnieszka", "Izabela",
    "Tobiasz", "Sławomir", "Włodzimierz", "Urszula", "Barbara", "Sebastian", "Robert", "Patricia", "Pere",
    # Imiona występujące w polskich i zagranicznych depeszach. Lista służy
    # wyłącznie do walidacji pełnego układu Imię + Nazwisko, nigdy do
    # tworzenia osoby z samego pojedynczego tokenu.
    "Aleksandr", "Ali", "Christian", "Karol", "Miłosz", "Przemysław", "Radosław", "Rafał",
    "Rumen", "Ulrich", "Waldemar",
}

SURNAME_TOKEN_NOMINATIVE = {
    "szczerby": "Szczerba", "ziobry": "Ziobro", "brejzy": "Brejza", "karnowskiego": "Karnowski",
    "kaczynskiego": "Kaczyński", "czuchnowskiego": "Czuchnowski",
    "kowalskiego": "Kowalski", "jackowskiego": "Jackowski",
    "zembaczynskiego": "Zembaczyński", "morawieckiego": "Morawiecki",
    "bejde": "Bejda", "sroke": "Sroka", "sroki": "Sroka", "zalewska": "Zalewska", "zalewskiej": "Zalewska",
    "kowala": "Kowal", "wiplera": "Wipler",
    "ziobre": "Ziobro", "romanowskiego": "Romanowski", "kwiatkowskiego": "Kwiatkowski",
    "tuska": "Tusk",
    "wojcikiem": "Wójcik", "wisniewskiej": "Wiśniewska", "dery": "Dera", "kalety": "Kaleta", "julkego": "Julke",
}


def _nominative_person_surface(value: str) -> str:
    parts = _clean(value).split()
    if len(parts) < 2:
        return _clean(value)

    # aktywny kontrakt: deskryptor roli/miejsca przed pełnym imieniem i nazwiskiem nie jest
    # częścią osoby. Przykład z audytu: „Prezydent Sopotu Jacek Karnowski”
    # może dać powierzchnię „Sopotu Jacek Karnowski”; kanonem pozostaje
    # „Jacek Karnowski”. Reguła jest konserwatywna: drugi token musi być
    # rozpoznawalnym imieniem, więc nie obcinamy legalnych nazw 3-członowych.
    structural_prefixes = {
        "kontroli", "konfederacji", "koalicji", "lewicy", "partii", "klubu",
        "ministerstwa", "prokuratury", "biura", "urzędu", "urzedu", "senatu",
        "sejmu", "sądu", "sadu", "trybunału", "trybunalu", "izby", "kancelarii",
        "agencji", "komisji", "resortu",
    }
    if len(parts) >= 3 and (
        (parts[1] in COMMON_GIVEN_NAMES and parts[0] not in COMMON_GIVEN_NAMES)
        or _ascii(parts[-3]) in {_ascii(x) for x in structural_prefixes}
    ):
        parts = parts[-2:]

    normalized = list(parts)
    for index, token in enumerate(parts[:-1]):
        replacement = PERSON_TOKEN_NOMINATIVE.get(_ascii(token))
        if replacement:
            normalized[index] = replacement
    surname = SURNAME_TOKEN_NOMINATIVE.get(_ascii(parts[-1]))
    if surname:
        normalized[-1] = surname
    else:
        surname_ascii = _ascii(parts[-1])
        given_was_inflected = _ascii(parts[0]) in PERSON_TOKEN_NOMINATIVE
        if given_was_inflected and surname_ascii.endswith("osia") and len(parts[-1]) > 4:
            # Michała Wosia -> Michał Woś; analogicznie Łosia -> Łoś.
            # Stosujemy tylko wtedy, gdy imię samo niesie sygnał przypadku.
            normalized[-1] = parts[-1][:-3] + "ś"
        elif surname_ascii.endswith(("skiego", "ckiego")):
            # Kowalskiego → Kowalski, Nowackiego → Nowacki.
            normalized[-1] = parts[-1][:-4] + "i"
        elif surname_ascii.endswith("kiem") and len(parts[-1]) > 5:
            # Wójcikiem → Wójcik. Konserwatywna reguła narzędnika dla nazwisk -k.
            normalized[-1] = parts[-1][:-3]
        elif surname_ascii.endswith(("skim", "ckim")) and len(parts[-1]) > 5:
            # Kowalskim → Kowalski, Nowackim → Nowacki.
            normalized[-1] = parts[-1][:-2] + "i"
        elif surname_ascii.endswith("skiej") and len(parts[-1]) > 6:
            # Kluzik-Rostkowskiej → Kluzik-Rostkowska.
            normalized[-1] = parts[-1][:-5] + "ska"
        elif surname_ascii.endswith("ckiej") and len(parts[-1]) > 6:
            normalized[-1] = parts[-1][:-5] + "cka"
        elif surname_ascii.endswith("dzkiej") and len(parts[-1]) > 7:
            normalized[-1] = parts[-1][:-6] + "dzka"
    return " ".join(normalized)


def normalize_person_surface(value: str) -> str:
    """Jedyna publiczna normalizacja powierzchni osoby.

    Resolver nie utrzymuje już własnej, równoległej morfologii. Funkcja jest
    konserwatywna: poprawia tylko dobrze udokumentowane formy, a ostateczny
    wybór kanonu wykonuje rejestr na podstawie wszystkich form z dokumentu.
    """
    return _nominative_person_surface(strip_person_title(_clean(value)))


def _person_surface_quality(value: str, document_text: str) -> tuple[int, int, int, int, int]:
    """Ocena formy reprezentacyjnej osoby bez zasady „dłuższy wygrywa”.

    Najmocniejszym dowodem jest forma rzeczywiście występująca w dokumencie z
    imieniem w mianowniku. Dzięki temu ``Tomasz Trela`` wygrywa z wygenerowanym
    ``Tomasz Treli``, a forma dopełniaczowa pozostaje aliasem.
    """
    raw = _clean(value)
    parts = raw.split()
    if len(parts) < 2:
        return (-99, 0, 0, 0, 0)
    first_ascii = _ascii(parts[0])
    given_nom = {_ascii(x) for x in COMMON_GIVEN_NAMES}
    given_inflected = set(PERSON_TOKEN_NOMINATIVE)
    exact_given = 1 if first_ascii in given_nom else 0
    inflected_given = 1 if first_ascii in given_inflected else 0
    # Liczymy literalną formę w surowym dokumencie. Wygenerowany kanon, którego
    # tekst nigdy nie zawierał, nie może pokonać poprawnej powierzchni źródłowej.
    observed = len(re.findall(_exact_pattern(raw), document_text or "", flags=0))
    surname_ascii = _ascii(parts[-1])
    case_penalty = 1 if surname_ascii.endswith(("skiego", "ckiego", "skiej", "ckiej", "dzkiej", "owi", "iem", "em")) else 0
    # Preferuj 2–3 tokeny i unikaj przypadkowych rozbudowanych deskryptorów.
    compact = 1 if 2 <= len(parts) <= 3 else 0
    return (exact_given, observed, -case_penalty, compact, -len(raw))


def _person_key(value: str) -> tuple[str, ...]:
    tokens = _clean(value).split()
    out = []
    for index, token in enumerate(tokens):
        raw = _ascii(token)
        if index == 0 and raw in FIRST_NAME_CASE_MAP:
            out.append(FIRST_NAME_CASE_MAP[raw])
        else:
            out.append(_person_token_stem(token))
    return tuple(out)

def _is_short_abbreviation(value: str) -> bool:
    compact = re.sub(r"\W", "", value, flags=re.UNICODE)
    return bool(compact) and len(compact) <= 5 and " " not in value and any(ch.isupper() for ch in value)


def _exact_pattern(value: str) -> str:
    return rf"(?<!\w){re.escape(value)}(?!\w)"


def _flex_pattern(name: str) -> str:
    if _is_short_abbreviation(name):
        return _exact_pattern(name)
    parts: list[str] = []
    for word in name.split():
        if word.casefold() in {"i", "oraz", "w", "z", "im"}:
            parts.append(re.escape(word))
        elif len(word) <= 4:
            parts.append(re.escape(word) + r"[\wąćęłńóśźż-]*")
        else:
            parts.append(re.escape(word[:-1]) + r"[\wąćęłńóśźż-]*")
    return r"\b" + r"\s+".join(parts) + r"\b"


def strip_leading_known_medium(value: Any) -> str:
    """Usuwa pełny span medium z początku wartości osoby, a nie tylko pierwszy token."""
    text = _clean(value)
    text = re.sub(r"^(?:w|we)\s+", "", text, flags=re.I)
    for spec in ENTITY_SPECS:
        if spec["type"] != "medium":
            continue
        for form in (spec["canonical"], *spec.get("aliases", ())):
            m = re.match(_exact_pattern(form) + r"\s+", text)
            if m:
                return text[m.end():].strip()
    return text


def _mask_spans(text: str, spans: Sequence[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(max(0, start), min(len(chars), end)):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


@dataclass
class Entity:
    entity_id: str
    canonical_name: str
    entity_type: str
    surface_forms: List[str] = field(default_factory=list)
    fixed_canonical: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "surface_forms": sorted(set(self.surface_forms), key=lambda x: (len(x), x.lower())),
        }


class EntityRegistry:
    """Jedyny rejestr encji dokumentu: jeden byt, jeden kanon i jeden entity_id."""

    def __init__(self, document_text: str = "") -> None:
        self.document_text = document_text or ""
        self._entities: Dict[str, Entity] = {}
        self._alias_index: Dict[str, str] = {}
        self._exact_alias_index: Dict[str, str] = {}
        self.rejected_candidates: List[Dict[str, str]] = []
        self._scan_document()

    def _lookup_id(self, value: str) -> str:
        raw = _clean(value)
        if raw in self._exact_alias_index:
            return self._exact_alias_index[raw]
        return self._alias_index.get(_signature(raw)) or self._alias_index.get(_ascii(raw)) or ""

    def _index_alias(self, entity: Entity, alias: str) -> None:
        alias = _clean(alias)
        if not alias:
            return
        if alias not in entity.surface_forms:
            entity.surface_forms.append(alias)
        if _is_short_abbreviation(alias):
            previous = self._exact_alias_index.get(alias)
            if not previous or previous == entity.entity_id:
                self._exact_alias_index[alias] = entity.entity_id
            return
        for key in (_signature(alias), _ascii(alias)):
            previous = self._alias_index.get(key)
            if not previous or previous == entity.entity_id:
                self._alias_index[key] = entity.entity_id

    def _register(
        self,
        canonical: str,
        entity_type: str,
        aliases: Iterable[str] = (),
        *,
        known: bool = False,
        entity_id: str = "",
        fixed_canonical: bool = False,
    ) -> Optional[Entity]:
        canonical = _clean(canonical)
        original_canonical = canonical
        aliases = list(aliases)
        if entity_type == "person":
            canonical = strip_person_title(canonical)
            nominative = _nominative_person_surface(canonical)
            if nominative != canonical:
                aliases.append(canonical)
                canonical = nominative
        if not is_public_entity_name(canonical):
            self.rejected_candidates.append({"candidate": original_canonical, "entity_type": entity_type, "reason": "technical_or_group_label"})
            return None
        initial_person = entity_type == "person" and bool(re.fullmatch(
            rf"(?:{CAP_WORD}\s+[A-ZĄĆĘŁŃÓŚŹŻ]\.|[A-ZĄĆĘŁŃÓŚŹŻ]\.\s+{CAP_WORD})",
            canonical,
        ))
        verdict = validate_entity_candidate(canonical, entity_type, known=known)
        if not verdict.accepted:
            self.rejected_candidates.append({"candidate": canonical, "entity_type": entity_type, "reason": verdict.reason})
            return None
        canonical = canonical if initial_person else verdict.cleaned
        eid = entity_id or self._lookup_id(canonical) or f"{entity_type}:{_slug(canonical)}"
        entity = self._entities.get(eid)
        if entity is None:
            entity = Entity(eid, canonical, entity_type, [], fixed_canonical=fixed_canonical)
            self._entities[eid] = entity
        elif entity.entity_type != entity_type:
            self.rejected_candidates.append({"candidate": canonical, "entity_type": entity_type, "reason": "entity_type_conflict"})
            return None

        if not entity.fixed_canonical and not fixed_canonical:
            # Current: nie wybieramy kanonu według długości napisu. Forma musi być
            # wsparta dokumentem i mianownikiem imienia. Ostateczna konsolidacja
            # następuje jeszcze raz po pełnym skanie dokumentu.
            if entity_type == "person":
                if _person_surface_quality(canonical, self.document_text) > _person_surface_quality(entity.canonical_name, self.document_text):
                    entity.canonical_name = canonical
            elif len(canonical) > len(entity.canonical_name):
                entity.canonical_name = canonical
        elif fixed_canonical:
            entity.canonical_name = canonical
            entity.fixed_canonical = True

        self._index_alias(entity, canonical)
        for alias in aliases:
            self._index_alias(entity, alias)
        return entity

    def _scan_known(self, text: str) -> list[tuple[int, int]]:
        occupied: list[tuple[int, int]] = []
        for spec in ENTITY_SPECS:
            detected: list[str] = []
            for form in (spec["canonical"], *spec.get("aliases", ())):
                # Samotne „Wyborcza/Wyborczej” jest nazwą medium tylko przy
                # zachowanej wielkiej literze. Małe „kampanii wyborczej” nie może
                # aktywować Gazety Wyborczej jako źródła.
                case_sensitive_media_alias = spec.get("type") == "medium" and form in {"Wyborcza", "Wyborczej"}
                pattern = _exact_pattern(form) if (_is_short_abbreviation(form) or case_sensitive_media_alias) else _flex_pattern(form)
                flags = 0 if (_is_short_abbreviation(form) or case_sensitive_media_alias) else re.I
                for match in re.finditer(pattern, text, flags):
                    detected.append(match.group(0))
                    occupied.append(match.span())
            if detected:
                canonical = spec["canonical"]
                self._register(
                    canonical,
                    spec["type"],
                    detected,
                    known=True,
                    entity_id=f"{spec['type']}:{_slug(canonical)}",
                    fixed_canonical=True,
                )
        return occupied

    def _scan_dynamic_institutions(self, text: str, occupied: list[tuple[int, int]]) -> None:
        masked = _mask_spans(text, occupied)
        for match in DYNAMIC_INSTITUTION_RE.finditer(masked):
            surface = _clean(text[match.start():match.end()])
            if not surface:
                continue
            self._register(surface, "institution", [surface], known=True)
            occupied.append(match.span())

    def _scan_dynamic_organizations(self, text: str, occupied: list[tuple[int, int]]) -> None:
        masked = _mask_spans(text, occupied)
        for match in DYNAMIC_ORGANIZATION_RE.finditer(masked):
            start, end = match.start("name"), match.end("name")
            surface = _clean(text[start:end])
            if not surface or self._lookup_id(surface):
                continue
            self._register(surface, "institution", [surface], known=True)
            occupied.append((start, end))

    def _scan_dynamic_media(self, text: str, occupied: list[tuple[int, int]]) -> None:
        masked = _mask_spans(text, occupied)
        for match in DYNAMIC_MEDIA_RE.finditer(masked):
            start, end = match.start("name"), match.end("name")
            surface = _clean(text[start:end]).strip('"„”')
            if not surface or self._lookup_id(surface):
                continue
            self._register(surface, "medium", [surface], known=True)
            occupied.append((start, end))

    def _scan_dynamic_places(self, text: str, occupied: list[tuple[int, int]]) -> None:
        # Skanujemy oryginał, nie tekst zamaskowany. Inaczej po zamaskowaniu
        # medium w konstrukcji ``W TVN24 Jan Kowalski`` pozostałoby ``W ... Jan
        # Kowalski`` i osoba zostałaby błędnie uznana za lokalizację.
        for match in DYNAMIC_PLACE_RE.finditer(text):
            start, end = match.start("name"), match.end("name")
            if any(start < occ_end and end > occ_start for occ_start, occ_end in occupied):
                continue
            surface = _clean(text[start:end])
            if not surface or self._lookup_id(surface):
                continue
            verdict = validate_entity_candidate(surface, "place")
            if not verdict.accepted:
                continue
            self._register(verdict.cleaned, "place", [surface], known=True)
            occupied.append((start, end))

    @staticmethod
    def _looks_institutional(value: str) -> bool:
        first = _ascii(value.split()[0]) if value.split() else ""
        return bool(INSTITUTION_PREFIX_RE.match(first))

    def _matching_person_id(self, canonical: str) -> str:
        key = _person_key(canonical)
        if len(key) < 2:
            return ""
        matches = [
            entity.entity_id
            for entity in self._entities.values()
            if entity.entity_type == "person" and _person_key(entity.canonical_name) == key
        ]
        return matches[0] if len(matches) == 1 else ""

    def _register_person_surface(self, surface: str, *, allow_surname_alias: bool = True) -> None:
        surface = strip_person_title(surface)
        parts = _clean(surface).split()
        while parts and parts[0].casefold() in TITLE_WORDS:
            parts.pop(0)
        if len(parts) < 2 or parts[0] in BAD_PERSON_FIRST:
            return
        # ETAP A: nie sklejaj sąsiadujących osób przez nakładające się okno regexu.
        # Przykład: „Arlety Zalewskiej Magdalena Sroka” nie jest trzyczłonowym nazwiskiem.
        a0 = _ascii(parts[0])
        a1 = _ascii(parts[1]) if len(parts) > 1 else ""
        known_first_forms = set(PERSON_TOKEN_NOMINATIVE) | {_ascii(v) for v in PERSON_TOKEN_NOMINATIVE.values()} | {_ascii(v) for v in COMMON_GIVEN_NAMES}
        known_surname_forms = set(SURNAME_TOKEN_NOMINATIVE) | {_ascii(v) for v in SURNAME_TOKEN_NOMINATIVE.values()}
        institutional_tail = {"kontroli", "komisji", "ministerstwa", "prokuratury", "biura", "urzedu", "senatu", "sejmu", "sadu", "trybunalu", "izby", "kancelarii", "agencji"}
        if len(parts) >= 3 and (
            (_ascii(parts[0]) not in known_first_forms and _ascii(parts[-2]) in known_first_forms)
            or _ascii(parts[-3]) in institutional_tail
        ):
            parts = parts[-2:]
            original_surface = " ".join(parts)
            a0 = _ascii(parts[0])
            a1 = _ascii(parts[1])
        # Deskryptor + imię (np. „Sopotu Jacek”) nie jest osobą. Pełne
        # „Sopotu Jacek Karnowski” zostanie niezależnie sprowadzone do
        # „Jacek Karnowski”, więc odrzucenie tego krótszego okna nie traci danych.
        if len(parts) == 2 and a1 in known_first_forms and a0 not in known_first_forms:
            return
        if len(parts) >= 3 and a0 in known_first_forms and a1 in known_surname_forms:
            return
        # Odrzuć odwrócony fragment dwóch sąsiadujących osób: „Zalewskiej Magdalena”.
        if a0 in known_surname_forms and a1 in known_first_forms:
            return
        original_surface = " ".join(parts)
        canonical = _nominative_person_surface(original_surface)
        if self._looks_institutional(canonical):
            return
        existing_id = self._lookup_id(canonical)
        if existing_id and self._entities[existing_id].entity_type != "person":
            return
        verdict = validate_entity_candidate(canonical, "person")
        if not verdict.accepted:
            return
        aliases: list[str] = []
        if original_surface != canonical:
            aliases.append(original_surface)
        if allow_surname_alias and not parts[-1].endswith("."):
            aliases.append(parts[-1])
        matched_id = self._matching_person_id(canonical)
        self._register(canonical, "person", aliases, entity_id=matched_id)

    @staticmethod
    def _person_positive_evidence(surface: str, start: int, end: int, text: str) -> bool:
        parts = _clean(surface).split()
        if len(parts) < 2:
            return False
        first = _ascii(parts[0])
        known_first_forms = set(PERSON_TOKEN_NOMINATIVE) | {_ascii(v) for v in PERSON_TOKEN_NOMINATIVE.values()} | {_ascii(v) for v in COMMON_GIVEN_NAMES}
        if first in known_first_forms:
            return True
        before = text[max(0, start - 70):start]
        after = text[end:min(len(text), end + 70)]
        if re.search(r"(?:^|\s)(?:" + "|".join(sorted(map(re.escape, TITLE_WORDS), key=len, reverse=True)) + r")\s+(?:[^,.;:!?]{0,45}\s+)?$", before, re.I):
            return True
        if re.match(r"\s*(?:,\s*)?(?:powied\w*|stwierdz\w*|ocen\w*|zaprzecz\w*|odpowiedz\w*|przekaz\w*|dod\w*|zaznacz\w*|przyzn\w*|wyjaśn\w*|poinform\w*|oświadcz\w*|mówi\w*|napisa\w*|przypomnia\w*)\b", after, re.I):
            return True
        return False

    def _scan_people(self, text: str, occupied: list[tuple[int, int]]) -> None:
        masked = _mask_spans(text, occupied)
        initial_spans: list[tuple[int, int]] = []

        # Pełne nazwisko może być rozdzielone dopowiedzeniem redakcyjnym:
        # ``(Jan Krzysztof - red.) Ardanowski``. Rejestrujemy pełną osobę
        # i maskujemy wtrącenie, aby nie utworzyć osobnej encji ``Jan Krzysztof``.
        for match in EDITORIAL_SPLIT_PERSON_RE.finditer(masked):
            full = f"{match.group('given')} {match.group('surname')}"
            self._register_person_surface(full)
            initial_spans.append(match.span())
        masked = _mask_spans(masked, initial_spans)

        for regex in (INITIAL_PERSON_RE, REVERSED_INITIAL_PERSON_RE):
            for match in regex.finditer(masked):
                surface = _clean(text[match.start("name"):match.end("name")])
                self._register_person_surface(surface, allow_surname_alias=False)
                initial_spans.append((match.start("name"), match.end("name")))
        masked = _mask_spans(masked, initial_spans)
        seen_spans: set[tuple[int, int]] = set()
        for regex in (PERSON_3_OVERLAP_RE, PERSON_2_OVERLAP_RE):
            for match in regex.finditer(masked):
                start, end = match.start(1), match.end(1)
                if (start, end) in seen_spans:
                    continue
                seen_spans.add((start, end))
                surface = _clean(text[start:end])
                parts = surface.split()
                if parts and parts[0] in BAD_PERSON_FIRST:
                    if len(parts) == 3:
                        tail = " ".join(parts[-2:])
                        tail_start = end - len(tail)
                        if self._person_positive_evidence(tail, tail_start, end, text):
                            self._register_person_surface(tail)
                    continue
                if not self._person_positive_evidence(surface, start, end, text):
                    self.rejected_candidates.append({"candidate": surface, "entity_type": "person", "reason": "no_positive_person_evidence"})
                    continue
                self._register_person_surface(surface)

    def _choose_person_canonical(self, entity: Entity) -> str:
        candidates = [entity.canonical_name, *entity.surface_forms]
        best = entity.canonical_name
        best_score = _person_surface_quality(best, self.document_text)
        for candidate in candidates:
            normalized = normalize_person_surface(candidate)
            # Ocenę „czy występuje w dokumencie” bierzemy z oryginalnej formy,
            # a publikowaną nazwę z jej bezpiecznie znormalizowanej wersji.
            score = _person_surface_quality(candidate, self.document_text)
            if score > best_score:
                best, best_score = normalized, score
        return normalize_person_surface(best)

    def _canonicalize_person_ids(self) -> None:
        remap: Dict[str, str] = {}
        rebuilt: Dict[str, Entity] = {}
        for old_id, entity in list(self._entities.items()):
            if entity.entity_type == "person" and not entity.fixed_canonical:
                entity.canonical_name = self._choose_person_canonical(entity)
            desired = f"person:{_slug(entity.canonical_name)}" if entity.entity_type == "person" else old_id
            remap[old_id] = desired
            entity.entity_id = desired
            if desired in rebuilt:
                existing = rebuilt[desired]
                existing.surface_forms = sorted(set(existing.surface_forms) | set(entity.surface_forms))
            else:
                rebuilt[desired] = entity
        self._entities = rebuilt
        self._alias_index = {key: remap.get(value, value) for key, value in self._alias_index.items()}
        self._exact_alias_index = {key: remap.get(value, value) for key, value in self._exact_alias_index.items()}

    def _scan_document(self) -> None:
        occupied = self._scan_known(self.document_text)
        self._scan_dynamic_institutions(self.document_text, occupied)
        self._scan_dynamic_organizations(self.document_text, occupied)
        self._scan_dynamic_media(self.document_text, occupied)
        self._scan_dynamic_places(self.document_text, occupied)
        self._scan_people(self.document_text, occupied)
        self._canonicalize_person_ids()

    @staticmethod
    def _flex_pattern(name: str) -> str:
        return _flex_pattern(name)

    def resolve(self, value: Any, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        raw = _clean(value)
        if not raw:
            return None
        if expected_type == "person":
            raw = strip_person_title(strip_leading_known_medium(raw))
        if not is_public_entity_name(raw):
            return None

        eid = self._lookup_id(raw)
        if eid:
            entity = self._entities[eid]
            if expected_type and entity.entity_type != expected_type:
                return None
            self._index_alias(entity, raw)
            return entity.as_dict()

        verdict = validate_entity_candidate(raw, expected_type)
        if not verdict.accepted:
            return None
        raw = verdict.cleaned
        if len(raw.split()) == 1:
            sig = _signature(raw)
            matches = [
                entity for entity in self._entities.values()
                if entity.entity_type == "person" and _signature(entity.canonical_name.split()[-1]) == sig
            ]
            if len(matches) == 1 and (not expected_type or expected_type == "person"):
                self._index_alias(matches[0], raw)
                return matches[0].as_dict()
        if expected_type == "person":
            # Current: expected_type nie jest pozwoleniem na utworzenie osoby.
            # Mówca musi już istnieć w rejestrze dokumentu albo rozwiązać się
            # przez unikalne nazwisko/alias. Zapobiega to encjom „Nowej Lewicy”
            # i „Pan Romanowski”.
            self.rejected_candidates.append({
                "candidate": raw,
                "entity_type": "person",
                "reason": "unconfirmed_person_candidate",
            })
            return None
        if expected_type in {"institution", "medium", "product", "party"}:
            entity = self._register(raw, expected_type)
            return entity.as_dict() if entity else None
        return None

    def resolve_confirmed_person(self, value: Any) -> Optional[Dict[str, Any]]:
        """Rejestruje osobę tylko po potwierdzeniu roli przez resolver.

        To nie jest drugi NER. Wywołuje tę metodę wyłącznie CanonicalEntityBuilder
        dla mówcy, którego aktywny resolver udowodnił lokalną konstrukcją
        atrybucji. Dzięki temu rzadkie imiona (np. Mikołaj) nie wymagają ręcznej
        listy, a ``expected_type=person`` nadal samo w sobie nie tworzy osoby.
        """
        raw = strip_person_title(strip_leading_known_medium(_clean(value)))
        if not raw or self._lookup_id(raw):
            return self.resolve(raw, "person") if raw else None
        verdict = validate_entity_candidate(raw, "person")
        if not verdict.accepted:
            return None
        self._register_person_surface(verdict.cleaned)
        self._canonicalize_person_ids()
        return self.resolve(verdict.cleaned, "person")

    def all(self) -> List[Dict[str, Any]]:
        entities = [entity.as_dict() for entity in sorted(self._entities.values(), key=lambda item: (item.entity_type, item.canonical_name.lower()))]
        return filter_entity_dicts(entities)
