"""Porównanie dwóch grup zapisanych analiz: redakcji/źródeł albo folderów.

Moduł nie uruchamia klasyfikatora ponownie i nie próbuje przypisywać mediom
ideologii. Zestawia wyłącznie mierzalne cechy zapisanych wyników: liczebność,
relacje, review, typy twierdzeń, aktorów, targety, tematy oraz warstwy P0-P4.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import sqrt
from pathlib import PurePosixPath
import re
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, Iterator

from .version import APP_VERSION
from .document_kind import is_article_document

COMPARE_SCHEMA = "database_editorial_compare_v2"
MULTI_COMPARE_SCHEMA = "database_editorial_multi_compare_v1"
VALID_MODES = {"publisher", "folder"}
MAX_COMPARE_GROUPS = 10

_PUBLISHER_ALIASES = {
    "tvn24": "TVN24", "tvn24.pl": "TVN24", "www.tvn24.pl": "TVN24",
    "tvn meteo": "TVN Meteo", "tvnmeteo.pl": "TVN Meteo",
    "tvn warszawa": "TVN Warszawa", "tvnwarszawa.pl": "TVN Warszawa",
    "tvp": "tvp.info", "tvp info": "tvp.info", "tvp.info": "tvp.info",
    "pap": "PAP", "onet": "Onet", "onet.pl": "Onet",
    "interia": "Interia", "interia.pl": "Interia",
    "rmf24": "RMF24", "rmf24.pl": "RMF24",
    "polsat news": "Polsat News", "polsatnews.pl": "Polsat News",
}


def _normalize_publisher(value: Any) -> str:
    value = _clean(value)
    if not value:
        return ""
    # Usuwa sklejone nagłówki z eksportów, np. `PAP Autorka/Autor: ...`.
    value = re.split(r"\s+(?:Autorka?/Autor|Autor(?:ka)?|Data publikacji|URL)\s*:\s*", value, maxsplit=1, flags=re.I)[0]
    value = _clean(value)
    return _PUBLISHER_ALIASES.get(value.casefold(), value)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split()).strip()


def _section(result: Dict[str, Any], name: str) -> list[Dict[str, Any]]:
    rows = ((result.get("sekcje") or {}).get(name) or [])
    return [row for row in rows if isinstance(row, dict)]


def _publisher_from_structured_text(document: Dict[str, Any]) -> str:
    text = str(document.get("_text_content") or "")
    if not text:
        return ""
    head = text[:5000]
    url_match = re.search(r"(?im)^\s*URL\s*:\s*(https?://\S+)", head)
    structured_export = bool(
        url_match
        and re.search(r"(?im)^\s*TYTUŁ\s*:", head)
        and re.search(r"(?im)^\s*(LEAD|TREŚĆ)\s*:", head)
    )
    if structured_export:
        source_match = re.search(r"(?im)^[ \t]*ŹR[ÓO]DŁO[ \t]*:[ \t]*([^\n\r]*)$", head)
        if source_match:
            value = _clean(source_match.group(1))
            if value:
                return _normalize_publisher(value)
    if not url_match:
        return ""
    try:
        parsed = urlparse(url_match.group(1).strip())
        host = (parsed.hostname or "").casefold()
        path = (parsed.path or "").casefold()
    except Exception:
        return ""
    if host.endswith("tvn24.pl"):
        if path.startswith("/tvnmeteo/"):
            return "TVN Meteo"
        if path.startswith("/tvnwarszawa/"):
            return "TVN Warszawa"
        return "TVN24"
    if host.startswith("www."):
        host = host[4:]
    # V4.4.3: jedna marka ma jedną nazwę niezależnie od subdomeny/ścieżki.
    # To zapobiega sztucznemu rozbijaniu np. wydarzenia.interia.pl i biznes.interia.pl.
    brand_rules = (
        ("interia.pl", "Interia"),
        ("onet.pl", "Onet"),
        ("polsatnews.pl", "Polsat News"),
        ("rmf24.pl", "RMF24"),
        ("dziennik.pl", "Dziennik.pl"),
        ("dorzeczy.pl", "Do Rzeczy"),
        ("pap.pl", "PAP"),
        ("gazeta.pl", "Gazeta.pl"),
        ("wyborcza.pl", "Gazeta Wyborcza"),
        ("rp.pl", "Rzeczpospolita"),
        ("money.pl", "Money.pl"),
        ("businessinsider.com.pl", "Business Insider Polska"),
    )
    for domain, brand in brand_rules:
        if host == domain or host.endswith("." + domain):
            return brand
    return host or ""


def _publisher_from_result(document: Dict[str, Any], result: Dict[str, Any]) -> str:
    """Ustala redakcję/serwis, oddzielając ją od źródła przywołanego.

    Dla nowych eksportów strukturalnych używamy nagłówka `ŹRÓDŁO:` i URL.
    Starsze wyniki mogą mieć `publisher_source=PAP` mimo publikacji na TVN24,
    dlatego dopiero w fallbacku korzystamy z metadanych analizy.
    """
    structured = _publisher_from_structured_text(document)
    if structured:
        return structured

    # Jeśli ścieżka sama jawnie identyfikuje serwis, jest bezpieczniejsza niż
    # stare pole publisher_source, które historycznie oznaczało również agencję.
    path = _clean(document.get("relative_path") or "").casefold()
    if "tvn24" in path:
        return "TVN24"

    # Dla kontrolowanych folderów importu nazwa folderu jest wiarygodnym
    # identyfikatorem publikującej redakcji i ma pierwszeństwo przed historycznym
    # `publisher_source`, które bywało używane także dla autora/agencji.
    folder_publishers = {
        "pegazustvp": "tvp.info",
        "pegazusrvn": "TVN24",
        "tvn24_artykuly": "TVN24",
    }
    mapped = folder_publishers.get(_folder_from_document(document).casefold())
    if mapped:
        return mapped

    doc = result.get("dokument") or {}
    metadata = doc.get("metadata_by_document") or {}
    if isinstance(metadata, dict):
        values = []
        for meta in metadata.values():
            if not isinstance(meta, dict):
                continue
            value = _clean(meta.get("publisher_source"))
            if value:
                values.append(value)
        if values:
            return _normalize_publisher(Counter(values).most_common(1)[0][0])

    return "(nieustalona redakcja)"


def _folder_from_document(document: Dict[str, Any]) -> str:
    """Zwraca główny folder importu, nie katalog pojedynczego artykułu.

    Starsza wersja używała całej ścieżki nadrzędnej, przez co podfoldery
    `0001_.../raw.html` stawały się osobnymi grupami.
    """
    path = _clean(document.get("relative_path") or document.get("filename")).replace("\\", "/").strip("/")
    if not path:
        return "(bez folderu)"
    parts = [part for part in PurePosixPath(path).parts if part not in ("", ".")]
    if len(parts) <= 1:
        return "(bez folderu)"
    return parts[0]


def comparison_group(document: Dict[str, Any], result: Dict[str, Any], mode: str) -> str:
    safe_mode = str(mode or "").strip().casefold()
    if safe_mode == "publisher":
        return _publisher_from_result(document, result)
    if safe_mode == "folder":
        return _folder_from_document(document)
    raise ValueError(f"Nieobsługiwany tryb porównania: {mode}")


def list_comparison_groups(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]], *, mode: str
) -> list[Dict[str, Any]]:
    safe_mode = str(mode or "").strip().casefold()
    if safe_mode not in VALID_MODES:
        raise ValueError("Tryb musi być publisher albo folder.")
    counts: Counter[str] = Counter()
    chars: Counter[str] = Counter()
    for document, result in completed_results:
        if not is_article_document(document):
            continue
        group = comparison_group(document, result, safe_mode)
        counts[group] += 1
        chars[group] += int(document.get("text_chars") or result.get("dlugosc_tekstu") or 0)
    return [
        {"id": name, "label": name, "documents": int(count), "text_chars": int(chars[name])}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]


def _claim_type(card: Dict[str, Any]) -> str:
    return _clean(
        card.get("typ_twierdzenia")
        or card.get("typ_twierdzenia_kod")
        or card.get("status")
        or card.get("tytul")
    ) or "(nieokreślony)"


def _label(card: Dict[str, Any], *fields: str) -> str:
    for field_name in fields:
        value = _clean(card.get(field_name))
        if value:
            return value
    return "(nieokreślone)"


def _unique_cards(cards: list[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    seen: set[str] = set()
    for idx, card in enumerate(cards):
        relation_id = _clean(card.get("relation_id"))
        if relation_id:
            key = f"r:{relation_id}"
        else:
            key = "|".join(
                _clean(card.get(k)) for k in ("kod_techniczny", "kto_mowi", "o_kim", "fraza", "fragment")
            ) or f"idx:{idx}"
        if key in seen:
            continue
        seen.add(key)
        yield card


@dataclass
class _GroupAccumulator:
    name: str
    documents: int = 0
    text_chars: int = 0
    words: int = 0
    relations: int = 0
    relation_review: int = 0
    docs_with_relation: int = 0
    docs_with_p1: int = 0
    docs_with_p2: int = 0
    docs_with_p3: int = 0
    docs_with_p4: int = 0
    docs_with_p5: int = 0
    speakers: Counter[str] = field(default_factory=Counter)
    targets: Counter[str] = field(default_factory=Counter)
    topics: Counter[str] = field(default_factory=Counter)
    cited_sources: Counter[str] = field(default_factory=Counter)
    claim_types: Counter[str] = field(default_factory=Counter)
    p0: Counter[str] = field(default_factory=Counter)
    p1: Counter[str] = field(default_factory=Counter)
    p2: Counter[str] = field(default_factory=Counter)
    p3: Counter[str] = field(default_factory=Counter)
    p4: Counter[str] = field(default_factory=Counter)
    p5: Counter[str] = field(default_factory=Counter)
    speaker_docs: Counter[str] = field(default_factory=Counter)
    target_docs: Counter[str] = field(default_factory=Counter)
    topic_docs: Counter[str] = field(default_factory=Counter)
    cited_source_docs: Counter[str] = field(default_factory=Counter)
    claim_type_docs: Counter[str] = field(default_factory=Counter)
    p0_docs: Counter[str] = field(default_factory=Counter)
    p1_docs: Counter[str] = field(default_factory=Counter)
    p2_docs: Counter[str] = field(default_factory=Counter)
    p3_docs: Counter[str] = field(default_factory=Counter)
    p4_docs: Counter[str] = field(default_factory=Counter)
    p5_docs: Counter[str] = field(default_factory=Counter)

    def add(self, document: Dict[str, Any], result: Dict[str, Any]) -> None:
        self.documents += 1
        self.text_chars += int(document.get("text_chars") or result.get("dlugosc_tekstu") or 0)
        raw_text = str(document.get("_text_content") or (result.get("czyszczenie_tekstu") or {}).get("source_text") or "")
        self.words += len(re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9]+", raw_text))

        relations = list(_unique_cards(_section(result, "relacje_wypowiedzi")))
        if relations:
            self.docs_with_relation += 1
        self.relations += len(relations)
        doc_speakers, doc_targets, doc_topics, doc_cited = set(), set(), set(), set()
        for card in relations:
            if bool(card.get("wymaga_przegladu")):
                self.relation_review += 1
            speaker = _clean(card.get("kto_mowi"))
            target = _clean(card.get("o_kim"))
            topic = _clean(card.get("temat"))
            cited = _clean(card.get("zrodlo_przywolane"))
            if speaker:
                self.speakers[speaker] += 1; doc_speakers.add(speaker)
            if target:
                self.targets[target] += 1; doc_targets.add(target)
            if topic:
                self.topics[topic] += 1; doc_topics.add(topic)
            if cited:
                self.cited_sources[cited] += 1; doc_cited.add(cited)
        for value in doc_speakers: self.speaker_docs[value] += 1
        for value in doc_targets: self.target_docs[value] += 1
        for value in doc_topics: self.topic_docs[value] += 1
        for value in doc_cited: self.cited_source_docs[value] += 1

        doc_claim_types = set()
        for card in _unique_cards(_section(result, "fact_opinia_cytat")):
            label = _claim_type(card)
            self.claim_types[label] += 1
            doc_claim_types.add(label)
        for value in doc_claim_types: self.claim_type_docs[value] += 1

        p0_data = result.get("p0") or {}
        for label, count in (p0_data.get("wedlug_etykiet") or {}).items():
            try:
                clean_label = _clean(label) or "(nieokreślone)"
                numeric = int(count)
                self.p0[clean_label] += numeric
                if numeric > 0: self.p0_docs[clean_label] += 1
            except (TypeError, ValueError):
                pass

        layer_specs = (
            ("potwierdzone_p1", self.p1, "docs_with_p1", ("tytul", "kod_techniczny", "fraza")),
            ("techniki_p2", self.p2, "docs_with_p2", ("tytul", "kod_techniczny", "fraza")),
            ("ramy_p3", self.p3, "docs_with_p3", ("frame_label", "tytul", "fraza")),
            ("strategie_p4", self.p4, "docs_with_p4", ("tytul", "kod_techniczny", "fraza")),
            ("diagnozy_p5", self.p5, "docs_with_p5", ("tytul", "kod_techniczny", "fraza")),
        )
        presence_map = {
            "potwierdzone_p1": self.p1_docs, "techniki_p2": self.p2_docs, "ramy_p3": self.p3_docs,
            "strategie_p4": self.p4_docs, "diagnozy_p5": self.p5_docs,
        }
        for section_name, counter, doc_field, fields in layer_specs:
            cards = list(_unique_cards(_section(result, section_name)))
            if cards:
                setattr(self, doc_field, getattr(self, doc_field) + 1)
            seen_labels = set()
            for card in cards:
                label = _label(card, *fields)
                counter[label] += 1
                seen_labels.add(label)
            for label in seen_labels:
                presence_map[section_name][label] += 1

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round((float(numerator) / float(denominator) * 100.0), 2) if denominator else 0.0

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "documents": self.documents,
            "text_chars": self.text_chars,
            "words": self.words,
            "relations": self.relations,
            "relations_per_document": round(self.relations / self.documents, 2) if self.documents else 0.0,
            "relations_per_1000_words": round(self.relations / self.words * 1000.0, 2) if self.words else 0.0,
            "review_per_1000_words": round(self.relation_review / self.words * 1000.0, 2) if self.words else 0.0,
            "relation_review": self.relation_review,
            "relation_review_rate": self._rate(self.relation_review, self.relations),
            "documents_with_relation": self.docs_with_relation,
            "coverage_relation_documents": self._rate(self.docs_with_relation, self.documents),
            "documents_with_p1": self.docs_with_p1,
            "documents_with_p2": self.docs_with_p2,
            "documents_with_p3": self.docs_with_p3,
            "documents_with_p4": self.docs_with_p4,
            "documents_with_p5": self.docs_with_p5,
            "coverage_p1": self._rate(self.docs_with_p1, self.documents),
            "coverage_p2": self._rate(self.docs_with_p2, self.documents),
            "coverage_p3": self._rate(self.docs_with_p3, self.documents),
            "coverage_p4": self._rate(self.docs_with_p4, self.documents),
            "coverage_p5": self._rate(self.docs_with_p5, self.documents),
        }


def _distribution(counter: Counter[str], *, limit: int = 15) -> Dict[str, Any]:
    total = int(sum(counter.values()))
    rows = []
    for label, count in counter.most_common(limit):
        rows.append({
            "label": label,
            "count": int(count),
            "share": round((count / total * 100.0), 2) if total else 0.0,
        })
    return {"total": total, "rows": rows}


def _compare_distribution(
    a: Counter[str], b: Counter[str], *, limit: int = 15,
    a_docs: int = 0, b_docs: int = 0, a_words: int = 0, b_words: int = 0,
    a_presence: Counter[str] | None = None, b_presence: Counter[str] | None = None,
) -> Dict[str, Any]:
    total_a = int(sum(a.values()))
    total_b = int(sum(b.values()))
    labels = set(a) | set(b)
    a_presence = a_presence or Counter()
    b_presence = b_presence or Counter()
    def share(counter: Counter[str], label: str, total: int) -> float:
        return (counter.get(label, 0) / total * 100.0) if total else 0.0
    ranked = sorted(
        labels,
        key=lambda label: (
            max(share(a, label, total_a), share(b, label, total_b)),
            a.get(label, 0) + b.get(label, 0),
            label.casefold(),
        ),
        reverse=True,
    )[:limit]
    rows = []
    for label in ranked:
        sa = share(a, label, total_a)
        sb = share(b, label, total_b)
        ad = (a_presence.get(label, 0) / a_docs * 100.0) if a_docs else 0.0
        bd = (b_presence.get(label, 0) / b_docs * 100.0) if b_docs else 0.0
        ar = (a.get(label, 0) / a_words * 1000.0) if a_words else 0.0
        br = (b.get(label, 0) / b_words * 1000.0) if b_words else 0.0
        rows.append({
            "label": label,
            "a_count": int(a.get(label, 0)), "a_share": round(sa, 2),
            "b_count": int(b.get(label, 0)), "b_share": round(sb, 2),
            "delta_pp": round(sa - sb, 2),
            "a_docs": int(a_presence.get(label, 0)), "a_doc_share": round(ad, 2),
            "b_docs": int(b_presence.get(label, 0)), "b_doc_share": round(bd, 2),
            "delta_doc_pp": round(ad - bd, 2),
            "a_per_1000_words": round(ar, 2), "b_per_1000_words": round(br, 2),
            "delta_per_1000_words": round(ar - br, 2),
        })
    return {"a_total": total_a, "b_total": total_b, "rows": rows}


def _sample_warning(a_docs: int, b_docs: int) -> list[str]:
    warnings: list[str] = []
    if min(a_docs, b_docs) < 5:
        warnings.append("Co najmniej jedna grupa ma mniej niż 5 dokumentów; różnice udziałów są bardzo niestabilne.")
    elif min(a_docs, b_docs) < 20:
        warnings.append("Co najmniej jedna grupa ma mniej niż 20 dokumentów; traktuj różnice jako opis próby, nie trwałą cechę redakcji.")
    ratio = max(a_docs, b_docs) / max(1, min(a_docs, b_docs))
    if ratio >= 4:
        warnings.append("Grupy mają bardzo różne liczebności. Porównuj przede wszystkim udziały procentowe, nie surowe liczby.")
    return warnings


def _metric_specs() -> tuple[tuple[str, str, str], ...]:
    return (
        ("Dokumenty", "documents", "count"),
        ("Znaki tekstu", "text_chars", "count"),
        ("Słowa", "words", "count"),
        ("Relacje wypowiedzi", "relations", "count"),
        ("Relacje / dokument", "relations_per_document", "number"),
        ("Relacje / 1000 słów", "relations_per_1000_words", "number"),
        ("Review / 1000 słów", "review_per_1000_words", "number"),
        ("Relacje wymagające review", "relation_review_rate", "percent"),
        ("Dokumenty z relacją", "coverage_relation_documents", "percent"),
        ("Dokumenty z P1", "coverage_p1", "percent"),
        ("Dokumenty z P2", "coverage_p2", "percent"),
        ("Dokumenty z P3", "coverage_p3", "percent"),
        ("Dokumenty z P4", "coverage_p4", "percent"),
        ("Dokumenty z P5", "coverage_p5", "percent"),
    )


def build_multi_group_comparison(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]],
    *, mode: str, groups: Iterable[str],
) -> Dict[str, Any]:
    safe_mode = str(mode or "").strip().casefold()
    if safe_mode not in VALID_MODES:
        raise ValueError("Tryb musi być publisher albo folder.")
    names: list[str] = []
    seen: set[str] = set()
    for raw in groups:
        name = _clean(raw)
        key = name.casefold()
        if name and key not in seen:
            names.append(name); seen.add(key)
    if len(names) < 2:
        raise ValueError("Wybierz co najmniej dwie różne grupy.")
    if len(names) > MAX_COMPARE_GROUPS:
        raise ValueError(f"Jednocześnie można porównać maksymalnie {MAX_COMPARE_GROUPS} grup.")

    accumulators = {name: _GroupAccumulator(name) for name in names}
    by_casefold = {name.casefold(): name for name in names}
    for document, result in completed_results:
        if not is_article_document(document):
            continue
        group = comparison_group(document, result, safe_mode)
        target = by_casefold.get(group.casefold())
        if target is not None:
            accumulators[target].add(document, result)

    missing = [name for name, acc in accumulators.items() if not acc.documents]
    if missing:
        raise LookupError("Brak zakończonych analiz dla grup: " + ", ".join(missing))

    summaries = [accumulators[name].summary() for name in names]
    metrics = []
    for label, key, kind in _metric_specs():
        metrics.append({
            "label": label, "key": key, "kind": kind,
            "values": {summary["name"]: summary[key] for summary in summaries},
        })

    warnings: list[str] = []
    smallest = min(acc.documents for acc in accumulators.values())
    largest = max(acc.documents for acc in accumulators.values())
    if smallest < 5:
        warnings.append("Co najmniej jedna grupa ma mniej niż 5 dokumentów; różnice są bardzo niestabilne.")
    elif smallest < 20:
        warnings.append("Co najmniej jedna grupa ma mniej niż 20 dokumentów; traktuj wynik jako opis próby.")
    if largest / max(1, smallest) >= 4:
        warnings.append("Grupy mają bardzo różne liczebności. Porównuj przede wszystkim wskaźniki znormalizowane.")

    return {
        "ok": True,
        "comparison_schema": MULTI_COMPARE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "mode": safe_mode,
        "mode_label": "linia redakcyjna / źródło dokumentu" if safe_mode == "publisher" else "główny folder źródłowy",
        "groups": summaries,
        "metrics": metrics,
        "warnings": warnings,
        "max_groups": MAX_COMPARE_GROUPS,
        "method_note": (
            "Porównanie jest opisowe i obejmuje wyłącznie rekordy rozpoznane jako właściwe artykuły; pliki techniczne (np. metadata.json, raw.html, indeksy) są pomijane. "
            "Nie przypisuje redakcjom ideologii ani intencji. Wskaźniki /1000 słów i odsetki dokumentów "
            "służą do ograniczenia wpływu różnej wielkości prób."
        ),
    }


def build_group_comparison(
    completed_results: Iterable[tuple[Dict[str, Any], Dict[str, Any]]],
    *, mode: str, group_a: str, group_b: str,
) -> Dict[str, Any]:
    """Kompatybilny interfejs A↔B używany m.in. przez matcher tej samej sprawy."""
    rows = list(completed_results)
    multi = build_multi_group_comparison(rows, mode=mode, groups=[group_a, group_b])
    a_name, b_name = [summary["name"] for summary in multi["groups"]]
    a = _GroupAccumulator(a_name); b = _GroupAccumulator(b_name)
    for document, result in rows:
        if not is_article_document(document):
            continue
        group = comparison_group(document, result, mode)
        if group.casefold() == a_name.casefold(): a.add(document, result)
        elif group.casefold() == b_name.casefold(): b.add(document, result)
    summary_a, summary_b = a.summary(), b.summary()
    metric_rows = []
    for label, key, kind in _metric_specs():
        av, bv = summary_a[key], summary_b[key]
        metric_rows.append({"label": label, "kind": kind, "a": av, "b": bv, "delta": round(float(av)-float(bv), 2)})
    common = dict(a_docs=a.documents, b_docs=b.documents, a_words=a.words, b_words=b.words)
    distributions = {
        "speakers": _compare_distribution(a.speakers,b.speakers,a_presence=a.speaker_docs,b_presence=b.speaker_docs,**common),
        "targets": _compare_distribution(a.targets,b.targets,a_presence=a.target_docs,b_presence=b.target_docs,**common),
        "topics": _compare_distribution(a.topics,b.topics,a_presence=a.topic_docs,b_presence=b.topic_docs,**common),
        "cited_sources": _compare_distribution(a.cited_sources,b.cited_sources,a_presence=a.cited_source_docs,b_presence=b.cited_source_docs,**common),
        "claim_types": _compare_distribution(a.claim_types,b.claim_types,a_presence=a.claim_type_docs,b_presence=b.claim_type_docs,**common),
        "p0": _compare_distribution(a.p0,b.p0,a_presence=a.p0_docs,b_presence=b.p0_docs,**common),
        "p1": _compare_distribution(a.p1,b.p1,a_presence=a.p1_docs,b_presence=b.p1_docs,**common),
        "p2": _compare_distribution(a.p2,b.p2,a_presence=a.p2_docs,b_presence=b.p2_docs,**common),
        "p3": _compare_distribution(a.p3,b.p3,a_presence=a.p3_docs,b_presence=b.p3_docs,**common),
        "p4": _compare_distribution(a.p4,b.p4,a_presence=a.p4_docs,b_presence=b.p4_docs,**common),
        "p5": _compare_distribution(a.p5,b.p5,a_presence=a.p5_docs,b_presence=b.p5_docs,**common),
    }
    return {
        "ok": True, "comparison_schema": COMPARE_SCHEMA, "generated_at": multi["generated_at"],
        "app_version": APP_VERSION, "mode": multi["mode"], "mode_label": multi["mode_label"],
        "group_a": summary_a, "group_b": summary_b, "metrics": metric_rows,
        "distributions": distributions, "warnings": _sample_warning(a.documents,b.documents),
        "method_note": multi["method_note"],
    }
