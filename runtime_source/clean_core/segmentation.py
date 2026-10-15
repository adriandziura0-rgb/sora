from __future__ import annotations

"""Aktywna segmentacja: segmentacja dokumentu na bloki, zdania, cytaty i metadane.

Moduł oddziela treść analityczną od nagłówków, podpisów zdjęć, źródeł,
autorów, tagów i linków redakcyjnych. Resolver relacji dostaje wyłącznie
segmenty typu ``body`` i ``quote`` oraz nie dziedziczy mówcy między blokami.
"""

from dataclasses import dataclass, asdict
import hashlib
import re
from typing import Dict, Iterable, List, Tuple


_ABBR = ("dr", "prof", "mec", "gen", "płk", "ppłk", "insp", "nadkom", "st", "mł", "św", "al", "ds", "ws", "np", "m.in", "fot")
_META_LINE_RE = re.compile(
    r"^(?:źródło(?:\s+zdjęcia(?:\s+głównego)?)?|autorka?/autor|autor(?:ka)?|tagi|podziel\s+się|"
    r"link\s+skopiowany|czytaj\s+więcej|dowiedz\s+się\s+więcej)\s*:", re.I
)
_PHOTO_RE = re.compile(r"^(?:źródło\s+zdjęcia(?:\s+głównego)?\s*:|fot\.?\s+(?:Adobe\s+Stock|Shutterstock|Getty\s+Images|PAP)\s*$)", re.I)
_BYLINE_RE = re.compile(r"^(?:autorka?/autor|autor(?:ka)?)\s*:", re.I)
_TAG_RE = re.compile(r"^tagi\s*:", re.I)
_LINK_RE = re.compile(r"^(?:link\s+skopiowany\s+do\s+schowka|czytaj\s+więcej|dowiedz\s+się\s+więcej|oglądaj\s+całą|tvn24\s+na\s+żywo)\b", re.I)
_SOURCE_RE = re.compile(r"^źródło\s*:", re.I)
_INLINE_META_RE = re.compile(
    r"\s+(?:Źródło\s+zdjęcia(?:\s+głównego)?|Autorka?/Autor|Autor(?:ka)?|TAGI|Podziel\s+się)\s*:.*$",
    re.I,
)
_INLINE_SOURCE_RE = re.compile(r"\s+Źródło\s*:\s*[^.?!]{1,100}(?=(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+\s+(?:powiedział|stwierdził|ocenił|dodał|przekazał))|$)", re.I)
_LEADING_PHOTO_CREDIT_RE = re.compile(
    r"^(?:(?:Fot\.?\s+)?(?:Adobe\s+Stock|Shutterstock|Getty\s+Images|PAP))\s+"
    r"(?=(?:Firma|Spółka|Koncern|Grupa)\b)",
    re.I,
)

DOCUMENT_BOUNDARY = "=== DROGOWSKAZY_DOCUMENT_BOUNDARY ==="
_DOCUMENT_BOUNDARY_RE = re.compile(r"^\s*===\s*DROGOWSKAZY_DOCUMENT_BOUNDARY\s*===\s*$", re.I)
_FILE_BOUNDARY_RE = re.compile(r"^\s*---\s*WCZYTANY\s+PLIK\s*:\s*.+?\s*---\s*$", re.I)


@dataclass(frozen=True)
class Segment:
    document_id: str
    document_index: int
    block_index: int
    segment_index: int
    kind: str
    text: str
    analyzable: bool
    quote: bool = False

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()



def _document_label(line: str) -> str:
    match = _FILE_BOUNDARY_RE.match(_clean(line))
    if not match:
        return "input"
    body = re.sub(r"^\s*---\s*WCZYTANY\s+PLIK\s*:\s*", "", _clean(line), flags=re.I)
    body = re.sub(r"\s*---\s*$", "", body).strip()
    return body or "input"


def make_document_id(document_index: int, label: str = "input") -> str:
    """Deterministyczny identyfikator dokumentu w obrębie jednego wejścia."""
    normalized = _clean(label).casefold() or "input"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    return f"doc_{document_index + 1:04d}_{digest}"

def split_sentences(text: str) -> List[str]:
    """Dzieli tekst na zdania, chroniąc najczęstsze polskie skróty i inicjały."""
    safe = str(text or "")
    safe = re.sub(r"\b(" + "|".join(_ABBR) + r")\.", lambda m: m.group(1) + "<DOT>", safe, flags=re.I)
    # Inicjały anonimowych nazwisk (np. „Anna W. powiedziała…”) nie mogą
    # kończyć zdania tylko dlatego, że po kropce stoi mała litera. Chronimy
    # pojedynczą wielką literę przed dowolnym dalszym tokenem literowym.
    safe = re.sub(r"\b([A-ZĄĆĘŁŃÓŚŹŻ])\.(?=\s*[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])", r"\1<DOT>", safe)
    parts = re.split(r"(?<=[.!?])\s+(?=(?:[A-ZĄĆĘŁŃÓŚŹŻ„\"'\-–—]|(?:premier|prezydent|minister|wiceminister|poseł|posłanka|senator|senatorka|prokurator|rzecznik|dziennikarz|reporter)\b))|\n+", safe, flags=re.I)
    return [_clean(p.replace("<DOT>", ".")) for p in parts if _clean(p)]




_CONTINUATION_START_RE = re.compile(
    r"^(?:[,.;:!?…)]|[a-ząćęłńóśźż]|(?i:(?:powiedzia[łła]|stwierdzi[łła]|oceni[łła]|doda[łła]|"
    r"zapowiedzia[łła]|potwierdzi[łła]|napisa[łła]|poinformowa[łła]|przyzna[łła]|"
    r"powoła[łła]|zatrzymali|przyznało|napisało|potwierdziło|ma\s|jest\s|są\s|jako\s|w\s+wyniku\s)))"
)

_EDITORIAL_BARRIER_RE = re.compile(
    r"^(?:MATERIAŁ\b|OBEJRZYJ\b|OGLĄDAJ\b|CZYTAJ\b|DOWIEDZ\b|ROZWIŃ\b)",
    re.I,
)


def _is_editorial_barrier(line: str) -> bool:
    return bool(_EDITORIAL_BARRIER_RE.match(_clean(line)))


def _is_hard_noncontent_kind(kind: str) -> bool:
    return kind in {
        "document_boundary", "photo_credit", "byline", "tags", "source_metadata",
        "editorial_link", "metadata",
    }


def _looks_inline_entity(line: str) -> bool:
    """Czy krótka linia może być nazwą wyłamaną ze środka zdania przez HTML."""
    s = _clean(line)
    if not s or len(s) > 90 or re.search(r"[.!?]$", s):
        return False
    if re.match(r"^(?:Źródło|TAGI|Autorka?/Autor|Podziel się|Czytaj|Dowiedz)\b", s, re.I):
        return False
    tokens = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9-]+", s)
    if not tokens or len(tokens) > 8:
        return False
    uppercaseish = sum(1 for t in tokens if t[:1].isupper() or t.isupper())
    return uppercaseish >= 1 and uppercaseish >= max(1, len(tokens) // 2)


def _starts_continuation(line: str) -> bool:
    return bool(_CONTINUATION_START_RE.match(_clean(line)))


def _ends_open(line: str) -> bool:
    s = _clean(line)
    return bool(s) and not bool(re.search(r"[.!?…][\"”’)]*$", s))


def _soft_wrap_boundary(lines: List[str], idx: int) -> bool:
    """Rozpoznaje fizyczny newline w środku jednego zdania."""
    if idx < 0 or idx + 1 >= len(lines):
        return False
    left, right = _clean(lines[idx]), _clean(lines[idx + 1])
    if not left or not right:
        return False
    lk, rk = _line_kind(left), _line_kind(right)
    if _is_hard_noncontent_kind(lk) or _is_hard_noncontent_kind(rk):
        return False
    if _is_editorial_barrier(left) or _is_editorial_barrier(right):
        return False

    if _looks_inline_entity(left) and _starts_continuation(right):
        return True

    if _ends_open(left) and _looks_inline_entity(right):
        if idx + 2 < len(lines):
            after = _clean(lines[idx + 2])
            ak = _line_kind(after) if after else "empty"
            if after and not _is_hard_noncontent_kind(ak) and (
                _starts_continuation(after) or re.match(r"^[-–—]\s*", after)
            ):
                return True
        if re.search(r"(?:\b(?:i|oraz|za|przez|organizacja|senator|premier|prezes|minister|rząd|z|ze|do|od|w|we)\s*)$", left, re.I):
            return True

    if _ends_open(left) and _starts_continuation(right):
        return True
    if _ends_open(left) and re.match(r"^[-–—]\s*", right) and lk == "content" and len(left) > 90:
        return True
    return False


def _join_soft_wrap(left: str, right: str) -> str:
    a, b = _clean(left), _clean(right)
    if not a:
        return b
    if not b:
        return a
    if b[:1] in ",.;:!?…)]" or a[-1:] in "([„\"":
        return a + b
    return a + " " + b


def _stitch_soft_wrapped_lines(lines: List[str]) -> List[str]:
    if not lines:
        return []
    work = [_clean(x) for x in lines if _clean(x)]
    out: List[str] = []
    i = 0
    while i < len(work):
        current = work[i]
        while i + 1 < len(work) and _soft_wrap_boundary(work, i):
            current = _join_soft_wrap(current, work[i + 1])
            work[i + 1] = current
            i += 1
        out.append(current)
        i += 1
    return out

def _line_kind(line: str) -> str:
    s = _clean(line)
    if not s:
        return "empty"
    if _DOCUMENT_BOUNDARY_RE.match(s) or _FILE_BOUNDARY_RE.match(s):
        return "document_boundary"
    if _PHOTO_RE.match(s):
        return "photo_credit"
    if _BYLINE_RE.match(s):
        return "byline"
    if _TAG_RE.match(s):
        return "tags"
    if _SOURCE_RE.match(s):
        return "source_metadata"
    if _LINK_RE.match(s) or re.fullmatch(r"[A-ZĄĆĘŁŃÓŚŹŻ0-9 /:–—-]{8,}", s):
        return "editorial_link"
    if _META_LINE_RE.match(s):
        return "metadata"
    # Nagłówek musi wyglądać jak samodzielny tytuł. Nie wolno odcinać
    # krótkich fragmentów zdań tylko dlatego, że nie kończą się kropką.
    if (
        len(s) <= 120
        and not re.search(r"[.!?,;:]$", s)
        and not re.match(r"^[,;:)\]–—-]", s)
        and not re.search(r"\b(?:powiedział|powiedziała|stwierdził|stwierdziła|dodał|dodała|ocenił|oceniła|przekazał|przekazała|mówił|mówiła|był|była|jest|są)\b", s, re.I)
        and (s.isupper() or (len(s.split()) <= 12 and s[:1].isupper()))
    ):
        return "heading"
    return "content"


def clean_analyzable_text(text: str) -> str:
    """Usuwa doczepione metadane bez naruszania właściwej treści zdania."""
    s = _clean(text)
    # Eksporty HTML potrafią skleić podpis zdjęcia z pierwszym zdaniem
    # (``Adobe Stock Firma OpenAI poinformowała...``). Podpis nie może wejść
    # do podmiotu relacji, ale usuwamy go tylko przed jawnym deskryptorem firmy.
    s = _LEADING_PHOTO_CREDIT_RE.sub("", s)
    s = _INLINE_META_RE.sub("", s)
    s = _INLINE_SOURCE_RE.sub("", s)
    return _clean(s)


def segment_document(text: str) -> List[Segment]:
    """Dzieli wejście na dokumenty i *logiczne linie/akapity*.

    Pusta linia pozostaje twardą granicą kontekstu. Pojedynczy ``\\n`` przed
    jawną kontynuacją typu „Dodał…” / „Podkreśliła…” zachowuje jednak ten sam
    blok, bo eksport HTML często rozcina w tym miejscu jedną turę wypowiedzi.
    Pozostałe linie nadal rozpoczynają nowy blok.
    """
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    segments: List[Segment] = []
    block_index = -1
    segment_index = 0
    document_index = 0
    document_label = "input"
    document_id = make_document_id(document_index, document_label)
    document_has_payload = False

    raw = re.sub(
        r"(?m)^\s*===\s*DROGOWSKAZY_DOCUMENT_BOUNDARY\s*===\s*$",
        f"\n{DOCUMENT_BOUNDARY}\n",
        raw,
    )

    # Puste linie są naturalną granicą. W obrębie każdego fragmentu pojedyncze
    # linie pozostają osobnymi blokami, chyba że _stitch_soft_wrapped_lines
    # udowodni, że newline przeciął jedno niedomknięte zdanie.
    chunks = re.split(r"\n\s*\n+", raw)
    for chunk in chunks:
        raw_lines = [_clean(x) for x in chunk.split("\n") if _clean(x)]
        lines = _stitch_soft_wrapped_lines(raw_lines)
        if not lines:
            continue

        previous_content_in_chunk = False
        for line in lines:
            kind = _line_kind(line)
            continuation_line = bool(
                kind == "content" and previous_content_in_chunk and _starts_continuation(line)
            )
            if not continuation_line:
                block_index += 1

            if kind == "document_boundary":
                if document_has_payload:
                    document_index += 1
                document_label = _document_label(line)
                document_id = make_document_id(document_index, document_label)
                document_has_payload = False
                segments.append(Segment(
                    document_id, document_index, block_index, segment_index,
                    "document_boundary", line, False, False,
                ))
                segment_index += 1
                previous_content_in_chunk = False
                continue

            if kind != "content":
                segments.append(Segment(
                    document_id, document_index, block_index, segment_index,
                    kind, line, False, False,
                ))
                segment_index += 1
                previous_content_in_chunk = False
                continue

            cleaned_line = clean_analyzable_text(line)
            if not cleaned_line:
                continue
            for sentence in split_sentences(cleaned_line):
                sentence = clean_analyzable_text(sentence)
                if len(sentence) < 4:
                    continue
                is_quote = bool(
                    re.match(r'^[\-–—„"]', sentence)
                    or re.search(r'[„"].+[”"]', sentence)
                )
                segments.append(Segment(
                    document_id, document_index, block_index, segment_index,
                    "quote" if is_quote else "body", sentence, True, is_quote,
                ))
                segment_index += 1
                document_has_payload = True
            previous_content_in_chunk = True

    if not segments and _clean(raw):
        for sentence in split_sentences(clean_analyzable_text(raw)):
            segments.append(Segment(document_id, document_index, 0, segment_index, "body", sentence, True, False))
            segment_index += 1
    return segments

def analyzable_blocks(text: str) -> List[List[Dict[str, object]]]:
    """Zwraca analizowalne zdania pogrupowane według document_id i block_index."""
    grouped: Dict[Tuple[str, int], List[Dict[str, object]]] = {}
    for seg in segment_document(text):
        if seg.analyzable:
            grouped.setdefault((seg.document_id, seg.block_index), []).append(seg.to_dict())
    return [grouped[k] for k in sorted(grouped, key=lambda x: (x[0], x[1]))]
