from __future__ import annotations

"""Dopasowywanie artykułów opisujących tę samą sprawę.

Moduł jest celowo lokalny i deterministyczny: nie korzysta z sieci ani modeli
zewnętrznych. Porównuje tytuł, lead/początek tekstu, rzadkie tokeny i datę.
Wynik ma wspierać porównania redakcji na podobnym materiale, a nie wydawać
werdykt o linii redakcyjnej.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha1
import math
import re
import unicodedata
from typing import Any, Dict, Iterable

from .editorial_compare import comparison_group, build_group_comparison, build_multi_group_comparison, MAX_COMPARE_GROUPS
from .version import APP_VERSION
from .document_kind import is_article_document

TOPIC_SCHEMA = "database_same_story_topics_v1"
TOPIC_COMPARE_SCHEMA = "database_same_story_compare_v1"

_WORD_RE = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9-]{3,}")
_META_RE = {
    "title": re.compile(r"(?im)^\s*TYTUŁ\s*:\s*(.+?)\s*$"),
    "url": re.compile(r"(?im)^\s*URL\s*:\s*(https?://\S+)\s*$"),
    "date": re.compile(r"(?im)^\s*DATA\s+PUBLIKACJI\s*:\s*(.+?)\s*$"),
    "lead": re.compile(r"(?is)\bLEAD\s*:\s*(.+?)(?=\n\s*TREŚĆ\s*:|$)"),
}

_STOP = {
    "oraz","który","która","które","których","którym","którego","której","tego","tej","ten","tym","jest","był","była","było","będzie","mają","miał","miała","mieli",
    "dla","przez","przy","nad","pod","bez","jak","ale","już","jeszcze","także","tak","nie","się","jego","jej","ich","swoje","swoim","swojej","po","do","od","na","w","we","z","ze","i","a","o","u","za","to","co","czy","gdy","kiedy","którym","między","m.in","min","artykul","artykuł","wiadomości","wiadomosci","polska","polsce","nowy","nowa","nowe","sprawie","sprawa","informuje","poinformował","poinformowala","przekazał","przekazala","powiedział","powiedziala",
    "rok","roku","dnia","dzień","dzien","stycznia","lutego","marca","kwietnia","maja","czerwca","lipca","sierpnia","września","wrzesnia","października","pazdziernika","listopada","grudnia",
}


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return value.casefold()


# Tokenizacja pracuje już na tekście bez polskich znaków. Lista stop-słów
# musi być normalizowana tym samym sposobem; inaczej np. „się” -> „sie”
# przestawało być stop-słowem i mogło sztucznie łączyć niezależne historie.
_STOP_FOLDED = {_fold(token) for token in _STOP}


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in _WORD_RE.findall(_fold(text)):
        token = raw.strip("-")
        if len(token) < 3 or token in _STOP_FOLDED or token.isdigit():
            continue
        out.append(token)
    return out


def _extract_metadata(document: Dict[str, Any]) -> Dict[str, Any]:
    text = str(document.get("_text_content") or "")
    title = ""
    url = ""
    date = ""
    lead = ""
    if text:
        match = _META_RE["title"].search(text[:8000])
        if match:
            title = " ".join(match.group(1).split())
        match = _META_RE["url"].search(text[:8000])
        if match:
            url = match.group(1).strip()
        match = _META_RE["date"].search(text[:8000])
        if match:
            date = " ".join(match.group(1).split())
        match = _META_RE["lead"].search(text[:12000])
        if match:
            lead = " ".join(match.group(1).split())
    if not title:
        path = str(document.get("relative_path") or document.get("filename") or "").replace("\\", "/").strip("/")
        parts = [part for part in path.split("/") if part]
        basename = parts[-1] if parts else str(document.get("filename") or "")
        stem = basename.rsplit(".", 1)[0]
        # Eksporty kolektora zapisują właściwy tekst jako `artykul.txt`, a tytuł
        # kodują w nazwie katalogu nadrzędnego: 0001_Tytuł_..._<hash>.
        if stem.casefold() in {"artykul", "artykuł", "article"} and len(parts) >= 2:
            parent = parts[-2]
            parent = re.sub(r"^\d{1,6}_", "", parent)
            parent = re.sub(r"_[0-9a-f]{8,40}$", "", parent, flags=re.I)
            title = parent.replace("_", " ")
        else:
            title = stem.replace("_", " ")
    return {"title": " ".join(title.split()).strip(), "url": url, "date": date, "lead": lead}


def _parse_date(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    candidates = [value.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    match = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", value)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
        except ValueError:
            return None
    return None




def _story_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in re.findall(r"[a-z0-9-]{2,}", _fold(text)):
        token = raw.strip("-")
        if not token or token in _STOP_FOLDED or token.isdigit():
            continue
        # Lekki stem odporny na polską fleksję: zamach/zamachu, zatrzymał/zatrzymany.
        # Nie jest to analizator morfologiczny; służy wyłącznie do łączenia opisów tej samej sprawy.
        if len(token) > 7:
            token = token[:7]
        out.add(token)
    return out


def _plain_jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0

# V4.4.3: sygnały fazy/podzdarzenia. Ten profil nie mówi „o czym redakcja myśli”,
# tylko chroni matcher przed łączeniem różnych etapów tej samej szerokiej sprawy.
_EVENT_MARKERS = {
    "poll": ("sondaz", "badanie poparcia", "poparcie w sondazu", "ankieta"),
    "vote": ("glosowanie", "wybory", "frekwenc", "lokal wyborczy", "urna"),
    "result": ("wyniki wybor", "wygral", "wygrala", "zwyciez", "mandat"),
    "team": ("zespol sledcz", "powstaje zespol", "powolano zespol", "powolanie zespol"),
    "arrest": ("areszt", "zatrzyman", "wniosek o areszt", "tymczasow"),
    "charges": ("zarzut", "oskarzen", "akt oskarzenia"),
    "youth": ("u18", "u-18", "junior", "mlodziez", "kadet"),
    "senior": ("senior", "reprezentacja polski", "kadra polski"),
    "marathon": ("maraton", "polmaraton"),
    "traffic": ("utrudnienia", "zamkniete ulice", "ruch drogowy", "objazd"),
}


def _event_profile(text: str) -> set[str]:
    folded = _fold(text)
    compact = re.sub(r"\s+", " ", folded)
    out: set[str] = set()
    for label, markers in _EVENT_MARKERS.items():
        if any(marker in compact for marker in markers):
            out.add(label)
    # „Reprezentacja Polski U18” nadal jest kategorią młodzieżową.
    if "youth" in out and "senior" in out and "senior" not in compact:
        out.discard("senior")
    # Tekst skupiony na objazdach/utrudnieniach jest innym podtypem niż relacja z biegu.
    # Nie oznaczamy tak artykułów zaczynających się od „Maraton...” / „Maratończycy...”,
    # nawet jeśli później wspominają utrudnienia.
    if "traffic" in out and re.match(r"(?:utrudnienia|objazdy|zamkniete ulice|zmiany w ruchu)\b", compact):
        out.add("traffic_only")
    return out


def _event_conflict(a: set[str], b: set[str]) -> bool:
    # Jawne różnice faz/podtypów tej samej szerokiej sprawy.
    if ("poll" in a) != ("poll" in b) and ({"vote", "result"} & (a | b)):
        return True
    if ("team" in a) != ("team" in b) and ({"arrest", "charges"} & (a | b)):
        return True
    if ("youth" in a) != ("youth" in b) and "senior" in (a | b):
        return True
    # Czysty tekst o objazdach/utrudnieniach nie jest tym samym materiałem co relacja z biegu.
    if ("traffic_only" in a) != ("traffic_only" in b) and "marathon" in (a | b):
        return True
    return False



_GENERIC_ANCHORS = {
    "komisja", "komisji", "sledcza", "sledczej", "pegasus", "pegasusa", "sprawa", "sprawie",
    "byly", "byla", "jest", "bedzie", "wniosek", "decyzja", "sejm", "polska", "polski",
    "nowy", "kolejny", "kolejna", "prezes", "minister", "premier", "polityk", "szef", "bylego",
}

def _entity_anchors(text: str) -> set[str]:
    """Wyciąga proste kotwice nazw własnych do ochrony przed szerokimi klastrami."""
    out: set[str] = set()
    words = re.findall(r"[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9-]{1,}", str(text or ""))
    for raw in words:
        token = _fold(raw).strip("-")
        if len(token) < 2 or token in _STOP_FOLDED or token in _GENERIC_ANCHORS:
            continue
        out.add(token[:20])
    # Akronimy bywają zapisane w środku zdania i są dobrymi kotwicami instytucji.
    for raw in re.findall(r"\b[A-ZĄĆĘŁŃÓŚŹŻ]{2,6}\b", str(text or "")):
        token = _fold(raw)
        if token not in _GENERIC_ANCHORS:
            out.add(token)
    return out

def _weighted_set(tokens: list[str], idf: Dict[str, float]) -> Dict[str, float]:
    counts = Counter(tokens)
    return {token: idf.get(token, 1.0) * (1.0 + math.log1p(count)) for token, count in counts.items()}


def _weighted_jaccard(a: Dict[str, float], b: Dict[str, float]) -> float:
    labels = set(a) | set(b)
    if not labels:
        return 0.0
    num = sum(min(a.get(x, 0.0), b.get(x, 0.0)) for x in labels)
    den = sum(max(a.get(x, 0.0), b.get(x, 0.0)) for x in labels)
    return num / den if den else 0.0


def _pair_score(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    title = _weighted_jaccard(a["title_weights"], b["title_weights"])
    body = _weighted_jaccard(a["body_weights"], b["body_weights"])
    story = _plain_jaccard(a.get("story_tokens", set()), b.get("story_tokens", set()))
    rare_overlap = len(a["rare_tokens"] & b["rare_tokens"])
    # Story-Jaccard ma większą wagę niż dokładna forma słów, bo polskie tytuły
    # często odmieniają te same nazwy i czasowniki.
    score = 0.55 * story + 0.25 * title + 0.20 * body
    if rare_overlap >= 3:
        score += 0.08
    elif rare_overlap >= 2:
        score += 0.05
    elif rare_overlap == 1:
        score += 0.02
    da, db = a.get("date_dt"), b.get("date_dt")
    if da and db:
        days = abs((da - db).total_seconds()) / 86400.0
        if days > 7:
            score *= 0.45
        elif days > 3:
            score *= 0.75
        elif days <= 1.5:
            score += 0.03
    return max(0.0, min(1.0, score))


def _representative_title(cluster: list[Dict[str, Any]]) -> str:
    if not cluster:
        return "(bez tytułu)"
    # Tytuł o największym średnim podobieństwie do pozostałych.
    best = None
    for item in cluster:
        avg = sum(_pair_score(item, other) for other in cluster if other is not item) / max(1, len(cluster) - 1)
        candidate = (avg, -len(item["metadata"]["title"]), item["metadata"]["title"])
        if best is None or candidate > best[0]:
            best = (candidate, item)
    return str(best[1]["metadata"]["title"] or "(bez tytułu)") if best else "(bez tytułu)"


def discover_same_story_topics(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]],
    *, min_publishers: int = 2,
    min_score: float = 0.125,
) -> Dict[str, Any]:
    rows = [(document, result) for document, result in completed_results if is_article_document(document)]
    docs: list[Dict[str, Any]] = []
    raw_token_docs: list[set[str]] = []
    for document, result in rows:
        meta = _extract_metadata(document)
        title_tokens = _tokens(meta["title"])
        lead_text = meta["lead"] or str(document.get("_text_content") or "")[:1600]
        body_tokens = _tokens(lead_text)
        token_set = set(title_tokens + body_tokens)
        raw_token_docs.append(token_set)
        docs.append({
            "document": document,
            "result": result,
            "metadata": meta,
            "publisher": comparison_group(document, result, "publisher"),
            "date_dt": _parse_date(meta["date"]),
            "title_tokens_raw": title_tokens,
            "body_tokens_raw": body_tokens,
            "story_tokens": _story_tokens((meta["title"] or "") + " " + (meta["lead"] or lead_text)),
            "entity_anchors": _entity_anchors((meta["title"] or "") + " " + (meta["lead"] or lead_text)[:700]),
            "event_profile": _event_profile((meta["title"] or "") + " " + (meta["lead"] or lead_text)),
        })
    n = len(docs)
    df: Counter[str] = Counter()
    for token_set in raw_token_docs:
        df.update(token_set)
    idf = {token: math.log((n + 1) / (freq + 1)) + 1.0 for token, freq in df.items()}
    rare_cutoff = max(2, int(math.ceil(n * 0.35)))
    for item in docs:
        item["title_weights"] = _weighted_set(item.pop("title_tokens_raw"), idf)
        item["body_weights"] = _weighted_set(item.pop("body_tokens_raw"), idf)
        item["rare_tokens"] = {t for t in item["title_weights"] if df.get(t, n) <= rare_cutoff}

    pair_scores: Dict[tuple[int, int], float] = {}
    eligible_edges: list[tuple[float, int, int]] = []

    def pair_is_eligible(i: int, j: int, score: float | None = None) -> bool:
        if docs[i]["publisher"] == docs[j]["publisher"]:
            return False
        if score is None:
            score = _pair_score(docs[i], docs[j])
        title_overlap = set(docs[i]["title_weights"]) & set(docs[j]["title_weights"])
        story_overlap = docs[i].get("story_tokens", set()) & docs[j].get("story_tokens", set())
        strong_story_overlap = len(story_overlap) >= 5
        medium_story_overlap = len(story_overlap) >= 3 and score >= 0.14
        strong_title_overlap = len(title_overlap) >= 2
        event_conflict = _event_conflict(docs[i].get("event_profile", set()), docs[j].get("event_profile", set()))
        da, db = docs[i].get("date_dt"), docs[j].get("date_dt")
        days = abs((da - db).total_seconds()) / 86400.0 if da and db else None
        date_ok = days is None or days <= 5 or score >= 0.30
        anchor_overlap = docs[i].get("entity_anchors", set()) & docs[j].get("entity_anchors", set())
        identity_ok = bool(anchor_overlap) or (len(story_overlap) >= 6 and score >= 0.20)
        return bool((not event_conflict) and date_ok and identity_ok and score >= min_score and (strong_title_overlap or strong_story_overlap or medium_story_overlap))

    for i in range(n):
        for j in range(i + 1, n):
            if docs[i]["publisher"] == docs[j]["publisher"]:
                continue
            score = _pair_score(docs[i], docs[j])
            pair_scores[(i, j)] = score
            if pair_is_eligible(i, j, score):
                eligible_edges.append((score, i, j))

    def score_for(i: int, j: int) -> float:
        if i == j:
            return 1.0
        key = (min(i, j), max(i, j))
        cached = pair_scores.get(key)
        return cached if cached is not None else _pair_score(docs[i], docs[j])

    def merge_is_cohesive(left: set[int], right: set[int]) -> bool:
        proposed = left | right
        cross_pairs: list[tuple[int, int, float, bool]] = []
        for pos, i in enumerate(sorted(proposed)):
            for j in sorted(proposed)[pos + 1:]:
                if docs[i]["publisher"] == docs[j]["publisher"]:
                    continue
                score = score_for(i, j)
                cross_pairs.append((i, j, score, pair_is_eligible(i, j, score)))
        if not cross_pairs:
            return False
        avg_score = sum(item[2] for item in cross_pairs) / len(cross_pairs)
        eligible_ratio = sum(1 for item in cross_pairs if item[3]) / len(cross_pairs)
        # Każdy dokument musi mieć bezpośredni, kwalifikowany odpowiednik w innej redakcji.
        linked = {idx: False for idx in proposed}
        for i, j, _score, eligible in cross_pairs:
            if eligible:
                linked[i] = True
                linked[j] = True
        if not all(linked.values()):
            return False
        # To jest właściwa ochrona przed „łańcuchem”: komponent nie może rosnąć
        # tylko dlatego, że kolejne pary łączą się słabymi mostami.
        return avg_score >= max(min_score, 0.20) and eligible_ratio >= 0.60

    cluster_for = list(range(n))
    clusters: Dict[int, set[int]] = {idx: {idx} for idx in range(n)}
    for _score, i, j in sorted(eligible_edges, reverse=True):
        ci, cj = cluster_for[i], cluster_for[j]
        if ci == cj:
            continue
        left, right = clusters.get(ci, set()), clusters.get(cj, set())
        if not left or not right or not merge_is_cohesive(left, right):
            continue
        # Stabilnie zachowujemy mniejszy identyfikator klastra.
        keep, drop = (ci, cj) if ci < cj else (cj, ci)
        merged = left | right
        clusters[keep] = merged
        clusters.pop(drop, None)
        for idx in merged:
            cluster_for[idx] = keep

    groups: Dict[int, list[int]] = {cid: sorted(indexes) for cid, indexes in clusters.items()}

    topics: list[Dict[str, Any]] = []
    for indexes in groups.values():
        cluster = [docs[i] for i in indexes]
        publishers = sorted({x["publisher"] for x in cluster})
        if len(cluster) < 2 or len(publishers) < min_publishers:
            continue
        # Nie pozwalamy, aby łańcuch słabych połączeń skleił odległe historie.
        cross = []
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                if docs[i]["publisher"] != docs[j]["publisher"]:
                    cross.append(score_for(i, j))
        avg_score = sum(cross) / len(cross) if cross else 0.0
        max_score = max(cross) if cross else 0.0
        rep_title = _representative_title(cluster)
        key_parts = sorted(str(x["document"].get("content_sha256") or x["document"].get("id")) for x in cluster)
        topic_id = "topic_" + sha1("|".join(key_parts).encode("utf-8")).hexdigest()[:14]
        dates = [x["date_dt"] for x in cluster if x["date_dt"]]
        topic_docs = []
        for x in sorted(cluster, key=lambda d: (str(d["publisher"]).casefold(), str(d["metadata"]["title"]).casefold())):
            topic_docs.append({
                "document_id": int(x["document"].get("id") or 0),
                "title": x["metadata"]["title"],
                "publisher": x["publisher"],
                "date": x["metadata"]["date"],
                "relative_path": x["document"].get("relative_path") or x["document"].get("filename") or "",
                "url": x["metadata"]["url"],
            })
        topics.append({
            "topic_id": topic_id,
            "title": rep_title,
            "documents": len(cluster),
            "publishers": publishers,
            "publisher_count": len(publishers),
            "date_from": min(dates).date().isoformat() if dates else "",
            "date_to": max(dates).date().isoformat() if dates else "",
            "avg_similarity": round(avg_score, 3),
            "max_similarity": round(max_score, 3),
            "items": topic_docs,
            "_indexes": indexes,
        })
    topics.sort(key=lambda x: (-x["publisher_count"], -x["documents"], x["title"].casefold()))
    public_topics = [{k: v for k, v in topic.items() if not k.startswith("_")} for topic in topics]
    return {
        "ok": True,
        "schema": TOPIC_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "documents_scanned": n,
        "topics": public_topics,
        "method_note": (
            "Tematy są wykrywane wyłącznie w rekordach rozpoznanych jako artykuły, lokalnie na podstawie podobieństwa tytułu, leadu/początku tekstu, rzadkich słów i daty. "
            "Klastry muszą zachować spójność parową, więc słaby łańcuch podobieństw nie może skleić wielu odległych historii. "
            "To mechanizm dopasowania materiału do porównania, a nie ocena ideologii ani intencji redakcji."
        ),
    }


def build_same_story_comparison(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]],
    *, topic_id: str,
    group_a: str = "",
    group_b: str = "",
    groups: Iterable[str] | None = None,
    mode: str = "publisher",
) -> Dict[str, Any]:
    """Porównuje 2–10 grup wyłącznie w obrębie jednej wykrytej sprawy.

    ``group_a``/``group_b`` pozostają dla zgodności ze starszym frontendem.
    Nowy frontend przekazuje powtarzalny parametr ``group``.
    """
    rows = list(completed_results)
    discovered = discover_same_story_topics(rows)
    topic = next((x for x in discovered["topics"] if x["topic_id"] == topic_id), None)
    if topic is None:
        raise LookupError("Nie znaleziono wskazanego tematu albo nie ma już co najmniej dwóch redakcji.")
    ids = {int(x["document_id"]) for x in topic["items"]}
    subset = [(doc, result) for doc, result in rows if int(doc.get("id") or 0) in ids]

    requested = [str(x or "").strip() for x in (groups or []) if str(x or "").strip()]
    if not requested:
        requested = [x for x in (str(group_a or "").strip(), str(group_b or "").strip()) if x]
    # Zachowaj kolejność i usuń duplikaty bez zmiany nazw widocznych dla użytkownika.
    unique = []
    seen = set()
    for value in requested:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    if len(unique) < 2:
        raise ValueError("Wybierz co najmniej dwie różne grupy do porównania tej samej sprawy.")
    if len(unique) > MAX_COMPARE_GROUPS:
        raise ValueError(f"Możesz porównać maksymalnie {MAX_COMPARE_GROUPS} grup jednocześnie.")

    if len(unique) == 2:
        comparison = build_group_comparison(subset, mode=mode, group_a=unique[0], group_b=unique[1])
    else:
        comparison = build_multi_group_comparison(subset, mode=mode, groups=unique)
    comparison["comparison_schema"] = TOPIC_COMPARE_SCHEMA
    comparison["same_story"] = {
        "topic_id": topic["topic_id"],
        "title": topic["title"],
        "documents": topic["documents"],
        "publishers": topic["publishers"],
        "date_from": topic["date_from"],
        "date_to": topic["date_to"],
        "avg_similarity": topic["avg_similarity"],
    }
    comparison["method_note"] = (
        "Porównanie zostało ograniczone do artykułów automatycznie dopasowanych jako ta sama sprawa. "
        + comparison.get("method_note", "")
    )
    return comparison
