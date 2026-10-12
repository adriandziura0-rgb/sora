"""Wspólne fragmenty i różnice: odczyt bez zmian bazy ani klasyfikatora.

Dopasowanie tekstowe to nie dowód cytowania, plagiatu, błędu ani pominięcia.
Wyniki pochodzą wyłącznie z zapisanych, ukończonych artykułów.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import PurePosixPath
import re

from .editorial_compare import comparison_group, VALID_MODES, MAX_COMPARE_GROUPS
from .document_kind import is_article_document

_WORDS = re.compile(r"(?u)[^\W_]+")
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_STOP = set("oraz jednak przez poniewaz zatem ktore ktora ktory ktorych kiedy gdzie tego tej tego jako jest byly jestesmy maja maja sie nie to ta ten tych dla nad pod bez ale lub oraz czyli nawet jeszcze mozna bardzo bylo tylko jest".split())
_LIMIT_DOCS = 900
_LIMIT_WORDS = 1000
_MAX_RESULTS = 20


def _tokens(text):
    return [word.casefold() for word in _WORDS.findall(str(text or ""))]


def _important(words):
    return {w for w in words if len(w) >= 5 and w not in _STOP}


def _title(document):
    text = str(document.get("_text_content") or "")
    header = re.search(r"(?im)^\s*TYTUŁ\s*:\s*(.+)$", text[:3000])
    if header:
        return header.group(1).strip()[:200]
    path = str(document.get("relative_path") or document.get("filename") or "").replace("\\", "/")
    parts = [item for item in path.split("/") if item]
    name = PurePosixPath(parts[-1] if parts else "nieznany").stem
    if name.casefold() in {"artykul", "artykuł", "article"} and len(parts) >= 2:
        name = re.sub(r"^\d{1,6}_", "", parts[-2])
        name = re.sub(r"_[0-9a-f]{8,40}$", "", name, flags=re.I)
    return re.sub(r"[_-]+", " ", name)[:200]


def _body(document):
    text = str(document.get("_text_content") or "")
    # Eksporty w postaci TYTUŁ / LEAD / TREŚĆ: nie porównujemy metadanych jak tekstu artykułu.
    content = re.search(r"(?im)^\s*TREŚĆ\s*:\s*", text[:12000])
    return text[content.end():] if content else text


def _snippets(text, alternative_words, *, max_items=2):
    """Fragmenty bez oczywistego odpowiednika słownego w drugim artykule.

    To NIE jest dowód, że drugi artykuł pominął podaną informację.
    """
    found = []
    for raw in _SENTENCES.split(text):
        sentence = " ".join(raw.split())
        words = _important(_tokens(sentence))
        if len(sentence) < 55 or len(words) < 5:
            continue
        novelty = len(words - alternative_words) / len(words)
        if novelty < 0.52:
            continue
        if len(sentence) > 280:
            sentence = sentence[:277].rsplit(" ", 1)[0] + "…"
        found.append((novelty, len(words), sentence))
    found.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [s for _, _, s in found[:max_items]]


def _exact_matches(a, b):
    # Ochrona pracy telefonu: nie skanujemy całych bardzo długich publikacji
    # kwadratowym algorytmem przy wielu podobnych powtarzających się słowach.
    matcher = SequenceMatcher(None, a["tokens"][:900], b["tokens"][:900], autojunk=True)
    matched = []
    for block in matcher.get_matching_blocks():
        if block.size < 8:
            continue
        phrase = " ".join(a["tokens"][block.a:block.a + block.size])
        if len(_important(a["tokens"][block.a:block.a + block.size])) < 3:
            continue
        matched.append((block.size, phrase[:420]))
    matched.sort(reverse=True)
    output = []
    for count, phrase in matched:
        if not any(phrase in already["text"] for already in output):
            output.append({"words": count, "text": phrase})
        if len(output) == 3:
            break
    return output


def _summary(document):
    return {
        "id": document["id"], "title": document["title"],
        "folder": document["folder"], "publisher": document["publisher"],
        "group": document["group"], "relative_path": document["relative_path"],
    }


def compare_shared_content(rows, *, mode, groups):
    mode = str(mode or "").casefold().strip()
    if mode not in VALID_MODES:
        raise ValueError("Wybierz foldery albo redakcje.")
    unique = []
    for raw in groups:
        name = str(raw).strip()
        if name and name.casefold() not in {v.casefold() for v in unique}:
            unique.append(name)
    if not 2 <= len(unique) <= MAX_COMPARE_GROUPS:
        raise ValueError("Zaznacz od 2 do 10 różnych folderów lub redakcji.")
    wanted = {name.casefold() for name in unique}

    docs = []
    count_selected = 0
    overflow = 0
    for document, analysis in rows:
        if not is_article_document(document):
            continue
        group = comparison_group(document, analysis, mode)
        if group.casefold() not in wanted:
            continue
        count_selected += 1
        if len(docs) >= _LIMIT_DOCS:
            overflow += 1
            continue
        body = _body(document)
        tokens = _tokens(body)[:_LIMIT_WORDS]
        if len(tokens) < 25:
            continue
        path = str(document.get("relative_path") or document.get("filename") or "")
        entry = {
            "id": int(document["id"]), "group": group,
            "title": _title(document), "folder": path.split("/")[0] if "/" in path else "(bez folderu)",
            "publisher": comparison_group(document, analysis, "publisher"),
            "relative_path": path, "text": body[:16000],
            "tokens": tokens, "title_words": _important(_tokens(_title(document))),
        }
        docs.append(entry)

    # Indeks sześciowyrazowych odcinków. Zbyt częste odcinki (stopki,
    # formuły redakcyjne) ignorujemy, aby nie scalać różnych wiadomości.
    # Hasze pełnych sześcioelementowych odcinków zmniejszają pamięć
    # względem przechowywania kilkuset tysięcy krotek napisów.
    # Pozycje o dużej częstotliwości oznaczamy jako szum redakcyjny.
    postings = {}
    for index, doc in enumerate(docs):
        words = doc["tokens"]
        seen = set()
        for i in range(len(words) - 5):
            window = words[i:i+6]
            if len(_important(window)) < 2:
                continue
            key = hash(tuple(window))
            if key in seen:
                continue
            seen.add(key)
            entries = postings.get(key)
            if entries is None and key in postings:
                continue
            if entries is None:
                postings[key] = [index]
            elif len(entries) >= 10:
                postings[key] = None
            else:
                entries.append(index)
    pairs = Counter()
    for participants in postings.values():
        if not participants or len(participants) < 2:
            continue
        for left, right in combinations(participants, 2):
            if docs[left]["group"].casefold() != docs[right]["group"].casefold():
                pairs[(left, right)] += 1

    # Gdy teksty zostały sparafrazowane, podobne tytuły mogą wskazać
    # artykuły o tym samym temacie. Nie nazywamy ich wspólnym cytatem.
    # Indeks tytułów zamiast O(n²) porównań wszystkich artykułów.
    title_index = defaultdict(set)
    for index, doc in enumerate(docs):
        for word in doc["title_words"]:
            title_index[word].add(index)
    title_pairs = Counter()
    for indexes in title_index.values():
        if len(indexes) > 24:
            continue
        for left, right in combinations(sorted(indexes), 2):
            if docs[left]["group"].casefold() != docs[right]["group"].casefold():
                title_pairs[(left,right)] += 1
    for (left,right), common_words in title_pairs.items():
        if common_words < 3:
            continue
        union = docs[left]["title_words"] | docs[right]["title_words"]
        if common_words / max(1,len(union)) >= .48:
            pairs[(left,right)] += 5

    matched = []
    for (left, right), score in pairs.most_common(100):
        a, b = docs[left], docs[right]
        title_intersection = a["title_words"] & b["title_words"]
        title_union = a["title_words"] | b["title_words"]
        title_sim = len(title_intersection)/len(title_union) if title_union else 0.0
        if score < 3 and title_sim < 0.48:
            continue
        common = _exact_matches(a, b) if score >= 3 else []
        if not common and title_sim < .48:
            continue
        novelty_a = _snippets(a["text"], _important(b["tokens"]))
        novelty_b = _snippets(b["text"], _important(a["tokens"]))
        if not common and not (novelty_a or novelty_b):
            continue
        matched.append({
            "left": _summary(a), "right": _summary(b),
            "match_kind": "wspólny fragment" if common else "zbliżony temat",
            "shared": common, "only_left": novelty_a, "only_right": novelty_b,
            "matching_words": max((v["words"] for v in common), default=0),
            "title_overlap_percent": round(100*title_sim),
        })
        if len(matched) >= _MAX_RESULTS:
            break
    return {
        "ok": True, "read_only": True, "schema": "sora_shared_content_v1",
        "mode": mode, "selected_groups": unique,
        "selected_articles": count_selected, "examined_articles": len(docs),
        "excluded_after_limit": overflow, "compared_words_per_article": _LIMIT_WORDS,
        "matches": matched,
        "description": "Dosłowne powtarzające się fragmenty i tekstowe podobieństwo tytułów. "
                       "Różnice są fragmentami bez znalezionego zbliżonego odpowiednika "
                       "słownego, nie dowodem pominięcia, plagiatu ani manipulacji.",
    }
