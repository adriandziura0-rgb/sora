from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class TextSegment:
    kind: str
    start: int
    end: int
    text: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["length"] = max(0, self.end - self.start)
        return d


INTRO_RX = re.compile(
    r"^\s*(?:pewnie|jasne|okej|ok|oczywi[śs]cie|poni[żz]ej|oto)\b[^\n]{0,220}(?:\n+|$)",
    re.I,
)
TASK_HEADER_RX = re.compile(
    r"(?im)^\s*(?:propozycje\s+zada[ńn]\s+analitycznych|mo[żz]esz\s+na\s+nim\s+testowa[ćc]|zadania\s+analityczne|do\s+analizy\s+mo[żz]esz\s+u[żz]y[ćc])\b.*$"
)
ANALYTIC_LIST_RX = re.compile(
    r"(?im)^\s*(?:[-*•]\s*)?(?:rozpoznawanie\s+nazw\s+w[łl]asnych|framing|retoryka\s+i\s+manipulacja|analiza\s+emocji|analiza\s+narracji|analiza\s+w[łl]adzy|presupozycje|propaganda|ner )\b.*$"
)
PROMPTY_LINE_RX = re.compile(
    r"(?im)^\s*(?:tekst\s+do\s+analizy|polecenie|prompt|instrukcja|komentarz\s+do\s+tekstu)\s*[:\-].*$"
)


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return start, end


def detect_metatext_segments(text: str) -> List[TextSegment]:
    """Wykrywa prompt/instrukcje/metakomentarz, który nie powinien zasilać P0-P5.

    Funkcja jest konserwatywna: wycina krótkie wprowadzenia na początku oraz
    jawne nagłówki/listy zadań analitycznych. Nie wycina zwykłego zdania tylko
    dlatego, że zawiera słowo „analiza”.
    """
    text = text or ""
    segments: List[TextSegment] = []

    m = INTRO_RX.search(text)
    if m and m.start() == 0 and len(m.group(0).strip()) <= 260:
        segments.append(TextSegment("intro_prompt", m.start(), m.end(), m.group(0), "krótkie wprowadzenie/prompt przed tekstem właściwym"))

    for rx, kind, reason in [
        (TASK_HEADER_RX, "analytic_task_header", "nagłówek listy zadań analitycznych"),
        (ANALYTIC_LIST_RX, "analytic_task_line", "pozycja listy instrukcji analitycznych"),
        (PROMPTY_LINE_RX, "prompt_line", "jawna linia promptu/instrukcji"),
    ]:
        for match in rx.finditer(text):
            start, end = match.start(), match.end()
            # Jeżeli regex nie objął całej linii, rozszerz ostrożnie do granic linii.
            if start == end:
                start, end = _line_bounds(text, match.start())
            segments.append(TextSegment(kind, start, end, text[start:end], reason))

    # Scal nakładające się segmenty.
    if not segments:
        return []
    segments = sorted(segments, key=lambda s: (s.start, s.end))
    merged: List[TextSegment] = []
    cur = segments[0]
    for seg in segments[1:]:
        if seg.start <= cur.end + 1:
            cur = TextSegment(
                kind=cur.kind if cur.kind == seg.kind else "mixed_metatext",
                start=cur.start,
                end=max(cur.end, seg.end),
                text=text[cur.start:max(cur.end, seg.end)],
                reason=(cur.reason if cur.reason == seg.reason else cur.reason + "; " + seg.reason),
            )
        else:
            merged.append(cur)
            cur = seg
    merged.append(cur)
    return merged


def split_source_and_meta(text: str) -> Dict[str, Any]:
    text = text or ""
    segments = detect_metatext_segments(text)
    if not segments:
        return {
            "source_text": text.strip(),
            "metatext_segments": [],
            "removed_characters": 0,
            "metatext_detected": False,
        }
    keep_parts: List[str] = []
    cursor = 0
    for seg in segments:
        keep_parts.append(text[cursor:seg.start])
        cursor = seg.end
    keep_parts.append(text[cursor:])
    cleaned = re.sub(r"\n{3,}", "\n\n", "".join(keep_parts)).strip()
    return {
        "source_text": cleaned,
        "metatext_segments": [s.to_dict() for s in segments],
        "removed_characters": sum(max(0, s.end - s.start) for s in segments),
        "metatext_detected": True,
    }


# Current — wspólny dekoder plików tekstowych i naprawa najczęstszych
# uszkodzeń polskich znaków. Ta sama funkcja jest używana przez endpoint.
_MOJIBAKE_TRANSLATION = str.maketrans({
    "å": "ć", "Å": "Ć", "ê": "ł", "Ê": "Ł", "Ñ": "ą", "ñ": "ą",
    "®": "ę", "©": "ę", "¥": "ż", "¿": "ż", "¯": "Ż",
    "õ": "ń", "Õ": "Ń", "ÿ": "ś", "Ÿ": "Ś",
    "\ufffe": "-", "\uffff": "-",
})


def repair_polish_mojibake(value: str) -> str:
    text = str(value or "").translate(_MOJIBAKE_TRANSLATION)
    return text.replace("\u0000", "")


def _decode_score(value: str) -> int:
    text = str(value or "")
    bad = text.count("�") * 30
    bad += sum(text.count(ch) for ch in "åÅêÊÑñ®¥©õÕ¿¯ÿŸ") * 6
    bad += sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t") * 10
    bad += text.count("\ufffe") * 20 + text.count("\uffff") * 20
    return bad


def decode_text_bytes(raw: bytes) -> tuple[str, str]:
    candidates: List[tuple[int, str, str]] = []
    for encoding in ("utf-8-sig", "cp1250", "iso-8859-2"):
        try:
            decoded = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        repaired = repair_polish_mojibake(decoded)
        candidates.append((_decode_score(repaired), encoding, repaired))
    if not candidates:
        repaired = repair_polish_mojibake(raw.decode("utf-8-sig", errors="replace"))
        return repaired, "utf-8-sig-replace"
    candidates.sort(key=lambda row: (row[0], 0 if row[1] == "utf-8-sig" else 1))
    _, encoding, text = candidates[0]
    return text, encoding



# V4.3.10 — strukturalne eksporty scrapera TVN24/TVN Meteo.
# Nowszy scraper zapisuje metadane w osobnych liniach (TYTUŁ/URL/AUTOR/LEAD/TREŚĆ),
# ale zawartość TREŚĆ nadal zawiera sklejone widgety i podpisy multimediów.
_TVN_STRUCTURED_LEAD_RX = re.compile(r"(?im)^\s*LEAD\s*:\s*$")
_TVN_STRUCTURED_BODY_RX = re.compile(r"(?im)^\s*TREŚĆ\s*:\s*$")
_TVN_RELATED_CATEGORIES = (
    "Najnowsze", "Polska", "Świat", "BIZNES", "Biznes", "Trójmiasto", "Warszawa",
    "TVN24", "KONKRET24", "Sport", "Zdrowie", "Technologia", "Meteo", "Opinie i wydarzenia",
)

def _extract_header_field(text: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text)
    return m.group(1).strip() if m else ""

def _collect_inline_media_sources(text: str) -> List[str]:
    values: List[str] = []
    # Tu granice są stabilne, bo po źródle wideo w eksportach występuje następna
    # etykieta widgetu. Nie traktujemy tych wartości jako źródła dokumentu —
    # służą wyłącznie do bezpiecznego odcięcia podpisu multimediów.
    for m in re.finditer(
        r"Źródło\s+wideo\s*:\s*(.{1,100}?)(?=Źródło\s+zdj\.|Posłuchaj\s+artykułu|Czyta\s+lektor|Wykup\s+subskrypcję|$)",
        text,
        re.I | re.S,
    ):
        candidate = re.sub(r"\s+", " ", m.group(1)).strip(" ,;:-")
        if candidate:
            values.append(candidate)
            # Wartość typu „Wojciech Sidorowicz/Fakty po Południu TVN24” nie
            # jest dobrym terminatorem podpisu, ale końcowy token TVN24 już tak.
            for token in re.findall(r"(?:TVN24|Ventusky|tvnmeteo\.pl|tvn24\.pl|PAP)", candidate, re.I):
                values.append(token)
    header_source = _extract_header_field(text, "ŹRÓDŁO")
    if header_source:
        values.append(header_source)
    values.extend(["TVN24", "Ventusky", "tvn24.pl", "tvnmeteo.pl", "PAP"])
    out: List[str] = []
    seen = set()
    for value in values:
        value = value.strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return sorted(out, key=len, reverse=True)

def _remove_related_promo_islands(text: str) -> str:
    value = str(text or "")
    marker = "DOWIEDZ SIĘ WIĘCEJ:"
    guard = 0
    while marker in value and guard < 20:
        guard += 1
        start = value.find(marker)
        window = value[start + len(marker): start + len(marker) + 320]
        cut = None
        used_category = False
        for category in _TVN_RELATED_CATEGORIES:
            idx = window.find(category)
            if idx >= 0:
                end = idx + len(category)
                if cut is None or end < cut:
                    cut = end
                    used_category = True
        if cut is None:
            m = re.search(r"[?!](?=[A-ZĄĆĘŁŃÓŚŹŻ„\"-])|\.(?=[A-ZĄĆĘŁŃÓŚŹŻ„\"-])", window)
            if m:
                cut = m.end()
        if cut is None:
            cut = min(len(window), 140)
        rest = value[start + len(marker) + cut:]
        # Po etykiecie kategorii scraper często dokleja jeszcze śródtytuł,
        # a dopiero potem właściwy akapit: „...TrójmiastoŻurek: ... realneTego...”.
        # Usuwamy tylko krótki śródtytuł, jeśli jego koniec jest jednoznacznie
        # widoczny jako sklejenie małaLitera+WielkaLitera.
        if used_category:
            boundary = re.search(r"(?<=[a-ząćęłńóśźż])(?=[A-ZĄĆĘŁŃÓŚŹŻ](?:[a-ząćęłńóśźż]|\s))", rest[:150])
            if boundary:
                rest = rest[boundary.start():]
        value = value[:start] + " " + rest
    return value

def _strip_leading_media_caption(line: str, sources: List[str]) -> str:
    value = str(line or "").strip()
    pos = value.find("Źródło:")
    if pos <= 0 or pos > 220:
        return value
    prefix = value[:pos]
    # Jeżeli przed etykietą źródła jest normalne zdanie, to jest to końcowa
    # metadana artykułu, a nie podpis multimediów. Nie wolno usuwać treści.
    if re.search(r"[.!?]", prefix):
        return value
    after = value[pos + len("Źródło:"):].lstrip()
    for source in sources:
        if after.casefold().startswith(source.casefold()):
            rest = after[len(source):].lstrip(" ,;:-")
            # Podpis multimediów + jego źródło są metadanymi prezentacji.
            # Zostawiamy wyłącznie ciąg dalszy artykułu po źródle.
            return rest
    return value

def _sanitize_tvn_structured_export(raw: str) -> Dict[str, Any] | None:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    if not _TVN_URL_LINE_RX.search(text):
        return None
    lead_match = _TVN_STRUCTURED_LEAD_RX.search(text)
    body_match = _TVN_STRUCTURED_BODY_RX.search(text)
    if not lead_match or not body_match or body_match.start() <= lead_match.end():
        return None

    lead = text[lead_match.end():body_match.start()].strip()
    body = text[body_match.end():].strip()
    if not body:
        return None

    # Nowszy eksport powtarza lead po widgetach. To najlepsza, odporna kotwica
    # początku treści — nie musimy zgadywać po nazwie serwisu ani długości menu.
    if lead and lead in body:
        body = body[body.find(lead):]
    else:
        for marker in _TVN_START_MARKERS:
            idx = body.find(marker)
            if idx >= 0:
                body = body[idx + len(marker):]
                break

    sources = _collect_inline_media_sources(text)
    chunks: List[str] = []
    tail_removed = False
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"(?i)^Zobacz cały materiał", line):
            continue
        # Rekomendacje/tagi są końcem artykułu, nie jego treścią.
        tail_positions = [p for p in (line.find("ZOBACZ TAKŻE:"), line.find("Czytaj także:"), line.find("Udostępnij:")) if p >= 0]
        if tail_positions:
            line = line[:min(tail_positions)].rstrip()
            tail_removed = True
        # OGLĄDAJ w tym eksporcie jest kartą promocyjną doklejoną do końca linii.
        ogl = line.find("OGLĄDAJ:")
        if ogl >= 0:
            line = line[:ogl].rstrip()
        line = _strip_leading_media_caption(line, sources)
        if line.startswith("Źródło:"):
            # Samodzielna linia źródłowa jest metadanymi, parser źródeł czyta ją z raw.
            line = ""
        line = _remove_related_promo_islands(line)
        # Końcowe „Źródło: domena” nie należy do treści analitycznej.
        line = re.sub(r"\s*Źródło\s*:\s*[A-Za-z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ._/-]+(?:\s*,\s*[A-Za-z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ._/-]+){0,3}\s*$", "", line, flags=re.I)
        if line:
            chunks.append(line)
        if tail_removed:
            break

    article = "\n\n".join(chunks).strip()
    article = _restore_joined_sentence_boundaries(article)
    # Techniczne frazy subskrypcji mogą pozostać tylko, gdy lead nie był powtórzony.
    article = re.sub(r"(?is)^.{0,1200}?Posłuchaj\s+artykułu.*?Dodaj nas do listy preferowanych źródeł w Google, aby nasze materiały częściej pojawiały się w Twoich wynikach wyszukiwania\.", "", article).strip()
    article = re.sub(r"[ \t]{2,}", " ", article)
    article = re.sub(r"\n{3,}", "\n\n", article).strip()
    if not article:
        return None
    return {
        "source_text": article,
        "publisher_dump": "tvn24_structured_text_v2",
        "publisher_dump_detected": True,
        "publisher_dump_removed_characters": max(0, len(text) - len(article)),
        "publisher_dump_start_marker": "LEAD/TREŚĆ" if lead and lead in text else "TREŚĆ",
        "publisher_dump_tail_removed": tail_removed,
        "structured_export_detected": True,
    }


# V4.3.9 — sanitizer dla surowych eksportów stron TVN24 / TVN Warszawa.
# Część scraperów zapisuje do TXT cały tekst DOM bez separatorów między
# komponentami. W takim wejściu menu, widgety, polecane materiały i tagi
# stają się pozorną treścią artykułu. Ta warstwa działa wyłącznie wtedy, gdy
# wejście ma jawny URL tvn24.pl/tvnwarszawa i charakterystyczne sygnały UI.
_TVN_URL_LINE_RX = re.compile(r"(?im)^\s*URL\s*:\s*https?://(?:www\.)?tvn24\.pl/\S+\s*$")
_TVN_RAW_UI_SIGNALS = (
    "SUBSKRYBUJ",
    "TVN24 na żywo",
    "Posłuchaj artykułu",
    "Dodaj do preferowanych źródeł w Google",
    "ZOBACZ TAKŻE:",
)
_TVN_START_MARKERS = (
    "Dodaj nas do listy preferowanych źródeł w Google, aby nasze materiały częściej pojawiały się w Twoich wynikach wyszukiwania.",
    "Dodaj nas do listy preferowanych źródeł w Google aby nasze materiały częściej pojawiały się w Twoich wynikach wyszukiwania.",
)

def _restore_joined_sentence_boundaries(value: str) -> str:
    text = str(value or "")
    # DOM-text eksporty często sklejają koniec zdania z początkiem następnego.
    text = re.sub(r'(?<=[.!?])(?=[A-ZĄĆĘŁŃÓŚŹŻ„"“])', ' ', text)
    # Śródtytuł bywa doklejony bez separatora bezpośrednio do zdania
    # rozpoczynającego się nazwiskiem + czasownikiem atrybucji. Nowa linia
    # pozwala segmentacji potraktować śródtytuł jako nieanalityczny heading.
    text = re.sub(
        r'(?<=[a-ząćęłńóśźż])(?=[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+\s+(?:przekazał|przekazała|poinformował|poinformowała|powiedział|powiedziała|dodał|dodała|mówił|mówiła|wyjaśnił|wyjaśniła|podkreślił|podkreśliła|zaznaczył|zaznaczyła)\b)',
        '\n',
        text,
    )
    # Sąsiednie cudzysłowy zwykle oznaczają koniec śródtytułu i początek cytatu.
    text = re.sub(r'""(?=[A-ZĄĆĘŁŃÓŚŹŻ„])', '"\n"', text)
    return text

def _sanitize_tvn_raw_dump(raw: str) -> Dict[str, Any] | None:
    text = str(raw or "")
    # Część prostych scraperów zapisuje separator linii dosłownie jako dwa
    # znaki ``\\n``. Naprawiamy to tylko dla rozpoznanego nagłówka eksportu.
    if "TYTUŁ:" in text[:500] and "\\nURL:" in text[:800]:
        text = text.replace("\\n", "\n")
    url_match = _TVN_URL_LINE_RX.search(text)
    if not url_match or sum(1 for marker in _TVN_RAW_UI_SIGNALS if marker in text) < 3:
        return None

    body = text[url_match.end():].lstrip("\n \t")
    start_index = -1
    start_marker = ""
    for marker in _TVN_START_MARKERS:
        idx = body.find(marker)
        if idx >= 0:
            candidate = idx + len(marker)
            if start_index < 0 or candidate < start_index:
                start_index = candidate
                start_marker = marker
    if start_index < 0:
        # Fallback jest celowo ostrożny: bez stabilnego końca widgetu nie
        # zgadujemy, gdzie zaczyna się artykuł. W takim przypadku zwykły
        # sanitizer przejmie wejście bez agresywnego cięcia.
        return None

    article = body[start_index:].strip()
    tail_markers = [m for m in (article.find("ZOBACZ TAKŻE:"), article.find("Czytaj także:")) if m >= 0]
    tail_index = min(tail_markers) if tail_markers else -1
    if tail_index >= 0:
        article = article[:tail_index].rstrip()

    # Wstawki redakcyjne pojawiają się w środku tekstu jako:
    # DOWIEDZ SIĘ WIĘCEJ:<tytuł>Najnowsze<ciąg dalszy artykułu>.
    article = re.sub(r"DOWIEDZ\s+SIĘ\s+WIĘCEJ:.{1,300}?Najnowsze", " ", article, flags=re.I | re.S)
    article = _restore_joined_sentence_boundaries(article)
    article = re.sub(r"(?i)(?<!\n)(Źródło\s*:\s*[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .&/-]{1,50})$", r"\n\1", article)
    article = re.sub(r"[ \t]{2,}", " ", article)
    article = re.sub(r"\n{3,}", "\n\n", article).strip()

    title_match = re.search(r"(?im)^\s*TYTUŁ\s*:\s*(.+?)\s*$", text[:url_match.start()])
    title = title_match.group(1).strip() if title_match else ""
    prefix = f"TYTUŁ: {title}\n" if title else ""
    clean = (prefix + article).strip()
    return {
        "source_text": clean,
        "publisher_dump": "tvn24_raw_text_v1",
        "publisher_dump_detected": True,
        "publisher_dump_removed_characters": max(0, len(text) - len(clean)),
        "publisher_dump_start_marker": start_marker,
        "publisher_dump_tail_removed": tail_index >= 0,
    }

# Current — centralna sanityzacja wejścia przed segmentacją/NLP.
_HTML_BLOCK_RX = re.compile(r"(?is)<(?:script|style|svg|noscript)\b[^>]*>.*?</(?:script|style|svg|noscript)\s*>")
_HTML_TAG_RX = re.compile(r"(?s)<[^>]+>")
_URL_RX = re.compile(r"https?://\S+", re.I)
_TECH_LINE_RX = re.compile(r"(?i)(?:poster16x9|application/json|\.m3u8\b|\.mp4\b|cloudfront|playerConfig|videoPlayer|data-testid|__NEXT_DATA__|webpack|asset(?:s)?\b)")
_JSONISH_RX = re.compile(r'^\s*[\[{].*(?:"(?:poster|src|url|hls|mp4|asset|player)[^"]*"\s*:).*[\]}]\s*$', re.I)

def sanitize_document(text: str) -> Dict[str, Any]:
    import html as _html
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    # Eksportery TXT czasem zapisują separatory nagłówka jako dosłowne \n.
    # Naprawiamy ten format przed usuwaniem URL, inaczej regex adresu mógłby
    # połknąć także początek artykułu.
    if "TYTUŁ:" in raw[:500] and "\\nURL:" in raw[:800]:
        raw = raw.replace("\\n", "\n")
    publisher_stats: Dict[str, Any] = {}
    publisher_clean = _sanitize_tvn_structured_export(raw) or _sanitize_tvn_raw_dump(raw)
    if publisher_clean:
        publisher_stats = {k: v for k, v in publisher_clean.items() if k != "source_text"}
        raw_for_cleaning = str(publisher_clean.get("source_text") or "")
    else:
        raw_for_cleaning = raw
    removed = []
    def _drop_block(m):
        removed.append((m.start(), m.end()))
        return "\n"
    cleaned = _HTML_BLOCK_RX.sub(_drop_block, raw_for_cleaning)
    cleaned = re.sub(r"(?i)<br\s*/?>|</p\s*>|</div\s*>|</article\s*>|</section\s*>|</li\s*>|</h[1-6]\s*>", "\n", cleaned)
    cleaned = _HTML_TAG_RX.sub(" ", cleaned)
    cleaned = _html.unescape(cleaned)
    out, dropped_lines = [], 0
    for line in cleaned.splitlines():
        s = re.sub(r"\s+", " ", line).strip()
        if not s:
            out.append(""); continue
        if _TECH_LINE_RX.search(s) or _JSONISH_RX.match(s):
            dropped_lines += 1; continue
        s = _URL_RX.sub("", s).strip()
        if s: out.append(s)
    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return {"source_text": clean, "sanitized_text": clean, "removed_technical_blocks": len(removed), "removed_technical_lines": dropped_lines, "removed_characters_approx": max(0, len(raw)-len(clean)), "sanitizer": "central-sanitizer-v2", **publisher_stats}
