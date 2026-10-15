from __future__ import annotations

"""Current — jedyny parser metadanych wejściowych.

Źródło dokumentu może pochodzić wyłącznie z jawnej linii ``Źródło:`` / ``Źródła:``
albo z pierwszej, nieopisowej listy kontrolowanych nazw źródeł. Zdanie artykułu,
tytuł lub lead nigdy nie staje się źródłem. Źródła zdjęć są osobnym polem.
"""

from dataclasses import dataclass
import re
from typing import Iterable, List

from .entity_registry import ENTITY_SPECS


@dataclass(frozen=True)
class InputMetadata:
    document_sources: List[str]
    image_sources: List[str]
    consumed_lines: List[int]

    @property
    def document_source(self) -> str:
        return ", ".join(self.document_sources)


_SOURCE_LABEL_RE = re.compile(r"^\s*źr[oó]d(?:ło|ła)\s*(?:materiału|tekstu|artykułu)?\s*:\s*(.*)$", re.I)
_IMAGE_LABEL_RE = re.compile(r"^\s*źr[oó]d(?:ło|ła)\s+zdjęci(?:a|e)(?:\s+głównego)?\s*:\s*(.*)$", re.I)
_SPLIT_RE = re.compile(r"\s*(?:,|;|\||\s+/\s+)\s*")
_SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
_WORD_RE = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9.-]+")
_URL_LINE_RE = re.compile(r"^\s*URL\s*:\s*(https?://\S+)\s*$", re.I)
_INLINE_IMAGE_SOURCE_RE = re.compile(r"Źródło\s+zdj\.\s*gł\.\s*:\s*(.{1,80}?)(?=Posłuchaj\s+artykułu|Czyta\s+lektor|Wykup\s+subskrypcję|Udostępnij|$)", re.I | re.S)
_INLINE_ARTICLE_SOURCE_RE = re.compile(r"Źródło\s*:\s*(.{1,60}?)(?=ZOBACZ\s+TAKŻE:|Czytaj\s+także:|Udostępnij:|$)", re.I | re.S)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n,;:–—-")


def _unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        value = _clean(value).strip('"„”\'')
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _known_source_forms() -> dict[str, str]:
    forms: dict[str, str] = {}
    for spec in ENTITY_SPECS:
        if spec.get("type") != "medium":
            continue
        canonical = _clean(spec.get("canonical"))
        if not canonical:
            continue
        forms[canonical.casefold()] = canonical
        for alias in spec.get("aliases", ()):
            alias = _clean(alias)
            if alias:
                forms[alias.casefold()] = canonical
    # Agencje i media występujące w materiałach kontrolnych, które nie były
    # wcześniej w rejestrze. To kontrolowana lista, nie heurystyczny fallback.
    for canonical in ("Reuters", "Haaretz", "Kalkalist", "Calcalist", "PAP", "AFP", "AP", "TVN24", "TVN Meteo"):
        forms[canonical.casefold()] = "Kalkalist" if canonical == "Calcalist" else canonical
    forms["tvn24.pl"] = "TVN24"
    forms["www.tvn24.pl"] = "TVN24"
    forms["tvnmeteo.pl"] = "TVN Meteo"
    forms["www.tvnmeteo.pl"] = "TVN Meteo"
    return forms


KNOWN_SOURCE_FORMS = _known_source_forms()


def _split(value: str) -> List[str]:
    return _unique(part for part in _SPLIT_RE.split(_clean(value)) if _clean(part))


def _canonical_source(value: str) -> str:
    return KNOWN_SOURCE_FORMS.get(_clean(value).casefold(), "")


def _strict_source_list(value: str) -> List[str]:
    """Akceptuje tylko listę składającą się w całości z kontrolowanych źródeł."""
    value = _clean(value)
    if not value or len(value) > 160 or _SENTENCE_RE.search(value):
        return []
    parts = _split(value)
    if len(parts) < 1:
        return []
    canonical: List[str] = []
    for part in parts:
        words = _WORD_RE.findall(part)
        if not words or len(words) > 5:
            return []
        resolved = _canonical_source(part)
        if not resolved:
            return []
        canonical.append(resolved)
    return _unique(canonical)


def _explicit_sources(value: str) -> List[str]:
    out: List[str] = []
    for part in _split(value):
        resolved = _canonical_source(part)
        # Przy jawnej etykiecie zachowujemy również nieznane krótkie nazwy własne,
        # ale nigdy pełne zdania.
        if resolved:
            out.append(resolved)
        elif 1 <= len(_WORD_RE.findall(part)) <= 5 and len(part) <= 60 and not _SENTENCE_RE.search(part):
            out.append(part)
    return _unique(out)


def parse_input_metadata(text: str) -> InputMetadata:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "TYTUŁ:" in raw_text[:500] and "\\nURL:" in raw_text[:800]:
        raw_text = raw_text.replace("\\n", "\n")
    lines = raw_text.split("\n")
    document_sources: List[str] = []
    image_sources: List[str] = []
    consumed: set[int] = set()

    # V4.3.10: jawna linia ŹRÓDŁO w strukturalnym eksporcie jest dokładniejsza
    # niż domena nadrzędna. Dzięki temu tvnmeteo.pl daje „TVN Meteo”, a nie
    # ogólne „TVN24”. URL jest fallbackiem dla eksportów bez tej linii.
    explicit_header_source = False
    for index, raw in enumerate(lines[:12]):
        label_line = re.sub(r"\s+", " ", str(raw or "")).strip()
        source_match = _SOURCE_LABEL_RE.match(label_line)
        if not source_match or _IMAGE_LABEL_RE.match(label_line):
            continue
        value = _clean(source_match.group(1))
        if value and not _SENTENCE_RE.search(value):
            parsed = _explicit_sources(value)
            if parsed:
                document_sources.extend(parsed)
                consumed.add(index)
                explicit_header_source = True
                break

    if not explicit_header_source:
        for index, raw_line in enumerate(lines[:12]):
            url_match = _URL_LINE_RE.match(str(raw_line or "").strip())
            if not url_match:
                continue
            url = url_match.group(1).casefold()
            if "tvnmeteo" in url:
                document_sources.append("TVN Meteo")
                consumed.add(index)
                break
            if "tvn24.pl/" in url or "tvnwarszawa.pl/" in url:
                document_sources.append("TVN24")
                consumed.add(index)
                break

    inline_image = _INLINE_IMAGE_SOURCE_RE.search(raw_text)
    if inline_image:
        image_sources.extend(_split(_clean(inline_image.group(1))))

    # Dokumentowe „Źródło:” jest zwykle ostatnią etykietą przed ZOBACZ TAKŻE.
    # Szukamy OSTATNIEGO wystąpienia, aby nie pomylić go z podpisem wykresu
    # lub wideo typu „Źródło: Ventusky”.
    for tail_marker in ("ZOBACZ TAKŻE:", "Czytaj także:", "Udostępnij:"):
        search_from = 0
        while True:
            tail = raw_text.find(tail_marker, search_from)
            if tail < 0:
                break
            before = raw_text[max(0, tail - 180):tail]
            rel = before.rfind("Źródło:")
            if rel >= 0:
                value = _clean(before[rel + len("Źródło:"):])
                if value:
                    document_sources.extend(_explicit_sources(value))
            search_from = tail + len(tail_marker)

    for index, raw in enumerate(lines):
        label_line = re.sub(r"\s+", " ", str(raw or "")).strip()
        line = _clean(raw)
        if not line:
            continue
        image_match = _IMAGE_LABEL_RE.match(label_line)
        if image_match:
            value = _clean(image_match.group(1))
            if not value:
                for following in range(index + 1, min(len(lines), index + 4)):
                    value = _clean(lines[following])
                    if value:
                        consumed.add(following)
                        break
            if value and not _SENTENCE_RE.search(value):
                image_sources.extend(_split(value))
            consumed.add(index)
            continue

        source_match = _SOURCE_LABEL_RE.match(label_line)
        if source_match and not _IMAGE_LABEL_RE.match(label_line):
            # V4.4.3: pusta linia `ŹRÓDŁO:` jest naprawdę pusta.
            # Nie wolno pobierać następnego wiersza (np. `LEAD:`) jako nazwy redakcji.
            value = _clean(source_match.group(1))
            if value and not _SENTENCE_RE.search(value):
                document_sources.extend(_explicit_sources(value))
            consumed.add(index)

    # Nieopisane źródła są dozwolone tylko jako pierwszy krótki nagłówek,
    # którego KAŻDY element jest znanym źródłem.
    nonempty = [(i, _clean(line)) for i, line in enumerate(lines) if _clean(line)]
    for index, line in nonempty[:8]:
        if index in consumed or _SOURCE_LABEL_RE.match(line) or _IMAGE_LABEL_RE.match(line):
            continue
        strict = _strict_source_list(line)
        if strict:
            document_sources.extend(strict)
            consumed.add(index)
            break

    return InputMetadata(
        document_sources=_unique(document_sources),
        image_sources=_unique(image_sources),
        consumed_lines=sorted(consumed),
    )
