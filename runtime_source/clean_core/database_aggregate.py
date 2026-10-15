"""Zbiorczy wynik wszystkich zapisanych analiz SQLite.

Warstwa nie uruchamia ponownie klasyfikatora. Czyta wyłącznie wyniki ze statusem
``done`` i składa z nich znormalizowany, kompaktowy raport. Karty są trzymane w
jednym rejestrze, a sekcje przechowują tylko referencje — dzięki temu ta sama
relacja nie jest kopiowana wiele razy w JSON-ie.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Iterable, Tuple

from .version import APP_VERSION, STAGE

AGGREGATE_SCHEMA = "database_aggregate_v1"

_CARD_FIELDS = {
    "tytul", "poziom", "poziom_analizy", "nazwa_poziomu_analizy", "ranking",
    "rola", "fraza", "fragment", "uzasadnienie", "dzialanie", "status",
    "pewnosc", "pewnosc_wzorca", "pewnosc_interpretacji", "wynik",
    "wymaga_przegladu", "istotnosc_analityczna", "kod_techniczny",
    "rola_techniczna", "priorytet", "ranking_priorytetu", "wynik_priorytetu",
    "typ_twierdzenia", "typ_twierdzenia_kod", "kto_mowi", "o_kim", "medium",
    "program", "zrodlo_przywolane", "zrodlo_dokumentu", "temat", "obiekt",
    "marker_atrybucji", "relacja_wypowiedzi", "relation_id",
    "surowa_pewnosc_relacji", "entity_id", "canonical_name", "entity_type",
    "entity_roles", "surface_forms", "mentions", "liczba_wzmianek", "source",
    "affiliation", "lista_elementow", "frame_id", "frame_label", "evidence_text",
    "dokladne_fragmenty_dowodowe", "etykiety_wspierajace", "evidence_roles",
    "evidence_strength", "ograniczenia", "dowody",
}

_UNIT_FIELDS = {
    "id", "tytul", "fragment", "relation_id", "aktor", "mowca",
    "marker_atrybucji", "claim", "target", "temat", "instytucja", "afiliacja",
    "zrodlo", "zrodlo_dokumentu", "zrodla_dokumentu", "zrodla_zdjec", "medium",
    "program", "obiekt", "typ_wypowiedzi", "sprawczosc", "dotyczy", "rama",
    "struktura", "pewnosc_relacji", "score", "priorytet", "wymaga_przegladu",
    "warstwy", "liczba_powtorzen_scalonych", "dowody_pomocnicze",
}


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _compact_card(card: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: card[k] for k in _CARD_FIELDS if k in card and _nonempty(card[k])}
    if card.get("wymaga_przegladu") is False:
        out["wymaga_przegladu"] = False
    return out


def _card_key(card: Dict[str, Any]) -> str:
    relation_id = str(card.get("relation_id") or "").strip()
    if relation_id:
        return f"r:{relation_id}"
    basis = [
        card.get("kod_techniczny"), card.get("kto_mowi"), card.get("o_kim"),
        card.get("fraza"), card.get("fragment"), card.get("canonical_name"),
        card.get("medium"), card.get("source"), card.get("frame_id"),
    ]
    raw = json.dumps(basis, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return "c:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _compact_unit(unit: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: unit[k] for k in _UNIT_FIELDS if k in unit and _nonempty(unit[k])}
    if unit.get("wymaga_przegladu") is False:
        out["wymaga_przegladu"] = False
    # Jednostki zbiorcze nie mają jednego wspólnego tekstu, więc pozycje i
    # highlight_id z pojedynczego dokumentu nie mogą sterować globalnym podglądem.
    out["link_status"] = "aggregate_without_single_text"
    out.pop("poczatek", None)
    out.pop("koniec", None)
    out.pop("highlight_id", None)
    return out


def _unit_key(unit: Dict[str, Any]) -> str:
    relation_id = str(unit.get("relation_id") or "").strip()
    if relation_id:
        return f"u:r:{relation_id}"
    raw = json.dumps(
        [unit.get("aktor"), unit.get("claim"), unit.get("target"), unit.get("fragment")],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "u:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _merge_numeric_counts(target: Counter, value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, raw in value.items():
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        target[str(key)] += number



def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _card_priority(card: Dict[str, Any]) -> tuple[float, float, float, int, int]:
    return (
        _numeric(card.get("wynik_priorytetu")),
        _numeric(card.get("ranking")),
        _numeric(card.get("wynik")),
        int(card.get("liczba_wzmianek") or card.get("mentions") or 0),
        len(card.get("dokumenty_bazy_ids") or []),
    )

def build_database_aggregate(
    rows: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]],
    *,
    database_stats: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Składa jeden wynik ze wszystkich zapisanych analiz bez reanalizy tekstów."""
    registry: Dict[str, Dict[str, Any]] = {}
    section_refs: Dict[str, list[str]] = defaultdict(list)
    section_seen: Dict[str, set[str]] = defaultdict(set)
    units_registry: Dict[str, Dict[str, Any]] = {}
    documents: Dict[str, Dict[str, Any]] = {}
    p0_groups: Counter = Counter()
    p0_phrases: Counter = Counter()
    summary_counts: Counter = Counter()
    quality_counts: Counter = Counter()
    versions: Counter = Counter()
    sources: Counter = Counter()
    total_chars = 0
    total_original_chars = 0
    analyzed_documents = 0

    for document, result in rows:
        if not isinstance(result, dict):
            continue
        doc_id = int(document.get("id") or 0)
        if not doc_id:
            continue
        analyzed_documents += 1
        versions[str(document.get("app_version") or result.get("wersja_aplikacji") or "nieznana")] += 1
        total_chars += int(result.get("dlugosc_tekstu") or document.get("text_chars") or 0)
        total_original_chars += int(result.get("dlugosc_tekstu_oryginalnego") or document.get("text_chars") or 0)
        section_counts = {
            str(name): len(cards) for name, cards in (result.get("sekcje") or {}).items()
            if isinstance(cards, list) and cards
        }
        documents[str(doc_id)] = {
            "id": doc_id,
            "filename": document.get("filename") or "",
            "relative_path": document.get("relative_path") or document.get("filename") or "",
            "source_bytes": int(document.get("source_bytes") or 0),
            "text_chars": int(document.get("text_chars") or 0),
            "analyzed_at": document.get("analyzed_at"),
            "app_version": document.get("app_version") or "",
            "analysis_run_id": document.get("analysis_run_id") or result.get("analysis_run_id") or "",
            "analysis_generated_at": result.get("analysis_generated_at"),
            "analysis_summary": {
                "podsumowanie": result.get("podsumowanie") or {},
                "quality_counts": (result.get("jakosc_analizy") or {}).get("counts") or {},
                "p0_markers": int((result.get("p0") or {}).get("liczba_markerow") or 0),
                "section_counts": section_counts,
            },
        }
        _merge_numeric_counts(summary_counts, result.get("podsumowanie"))
        _merge_numeric_counts(quality_counts, (result.get("jakosc_analizy") or {}).get("counts"))
        p0 = result.get("p0") or {}
        _merge_numeric_counts(p0_groups, p0.get("wedlug_etykiet"))
        for item in p0.get("najczestsze_frazy") or []:
            if isinstance(item, dict):
                phrase = str(item.get("phrase") or item.get("fraza") or "").strip()
                if phrase:
                    try:
                        count = int(item.get("count") or item.get("liczba") or 1)
                    except (TypeError, ValueError):
                        count = 1
                    p0_phrases[phrase] += max(1, count)
        for card in p0.get("pelny_podglad") or []:
            if not isinstance(card, dict):
                continue
            compact = _compact_card(card)
            key = _card_key(compact)
            current = registry.setdefault(key, {**compact, "dokumenty_bazy_ids": []})
            for field, value in compact.items():
                if field not in current or not _nonempty(current.get(field)):
                    current[field] = value
            if doc_id not in current["dokumenty_bazy_ids"]:
                current["dokumenty_bazy_ids"].append(doc_id)
            if key not in section_seen["__p0_pelny_podglad"]:
                section_refs["__p0_pelny_podglad"].append(key)
                section_seen["__p0_pelny_podglad"].add(key)

        for source in ((result.get("dokument") or {}).get("sources") or []):
            text = str(source or "").strip()
            if text:
                sources[text] += 1

        for section_name, cards in (result.get("sekcje") or {}).items():
            if not isinstance(cards, list):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                compact = _compact_card(card)
                key = _card_key(compact)
                current = registry.setdefault(key, {**compact, "dokumenty_bazy_ids": []})
                if doc_id not in current["dokumenty_bazy_ids"]:
                    current["dokumenty_bazy_ids"].append(doc_id)
                if key not in section_seen[section_name]:
                    section_refs[section_name].append(key)
                    section_seen[section_name].add(key)

        for unit in result.get("jednostki_znaczenia") or []:
            if not isinstance(unit, dict):
                continue
            compact_unit = _compact_unit(unit)
            key = _unit_key(compact_unit)
            current_unit = units_registry.setdefault(key, {**compact_unit, "dokumenty_bazy_ids": []})
            for field, value in compact_unit.items():
                if field not in current_unit or not _nonempty(current_unit.get(field)):
                    current_unit[field] = value
            if doc_id not in current_unit["dokumenty_bazy_ids"]:
                current_unit["dokumenty_bazy_ids"].append(doc_id)

    # Globalny wynik ma być niezależny od kolejności plików w folderze/bazie.
    # Każdą sekcję sortujemy po dostępnych metrykach jakości/rankingu, a przy
    # remisie po liczbie dokumentów potwierdzających kartę.
    for section_name, refs in section_refs.items():
        refs.sort(key=lambda ref: _card_priority(registry.get(ref) or {}), reverse=True)
    units_sorted = sorted(
        units_registry.values(),
        key=lambda unit: (_numeric(unit.get("score")), len(unit.get("dokumenty_bazy_ids") or [])),
        reverse=True,
    )

    now = datetime.now(timezone.utc).isoformat()
    aggregate_id_basis = json.dumps(
        [analyzed_documents, sorted((int(k), v.get("analysis_run_id")) for k, v in documents.items())],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    run_id = "dbagg_" + hashlib.sha1(aggregate_id_basis.encode("utf-8")).hexdigest()[:16]

    top_refs = section_refs.get("top_wyniki", [])
    relation_refs = section_refs.get("relacje_wypowiedzi", [])
    actor_refs = section_refs.get("mapa_aktorow", [])
    agency_refs = section_refs.get("mapa_sprawczosci", [])
    fact_refs = section_refs.get("fact_opinia_cytat", [])
    p3_refs = section_refs.get("ramy_p3", [])

    readable_items = [
        {"tytul": "Dokumenty w zbiorze", "wartosc": f"{analyzed_documents} przeanalizowanych dokumentów", "opis": "Wynik został złożony z zapisanych analiz SQLite bez ponownego uruchamiania analizatora.", "sekcja": "czyste"},
        {"tytul": "Relacje wypowiedzi", "wartosc": f"{len(relation_refs)} unikalnych relacji", "opis": "Relacje są deduplikowane; karta pamięta wszystkie dokumenty bazy, w których wystąpiła.", "sekcja": "relacje"},
        {"tytul": "Aktorzy / źródła", "wartosc": f"{len(actor_refs)} unikalnych kart aktorów", "opis": "Mapa zbiorcza łączy wyniki z całej bazy.", "sekcja": "aktorzy"},
        {"tytul": "Sprawczość", "wartosc": f"{len(agency_refs)} unikalnych kart", "opis": "Zbiorcza mapa działań i odpowiedzialności.", "sekcja": "sprawczosc"},
        {"tytul": "Fakt / opinia / cytat", "wartosc": f"{len(fact_refs)} unikalnych kart", "opis": "Statusy twierdzeń z całej bazy.", "sekcja": "fact"},
    ]

    right_panel = []
    for section_id, title, refs in (
        ("top_relacji", "TOP relacji", top_refs),
        ("relacje_wypowiedzi", "Relacje wypowiedzi", relation_refs),
        ("mapa_aktorow", "Mapa aktorów", actor_refs),
        ("mapa_sprawczosci", "Mapa sprawczości", agency_refs),
        ("fact_opinia_cytat", "Fakt / opinia / cytat", fact_refs),
        ("p3_ramy", "Ramy P3", p3_refs),
    ):
        if refs:
            right_panel.append({"id": section_id, "tytul": title, "liczba": len(refs), "opis": "Zbiorcza sekcja z całej bazy.", "otwarta": False, "rodzaj": "wynik", "status": "aktywna", "uwaga": "", "zrodlo": "sqlite"})

    stats = dict(database_stats or {})
    stats["used_done_results"] = analyzed_documents
    stats["skipped_unreadable_results"] = max(0, int(stats.get("done") or 0) - analyzed_documents)
    result = {
        "ok": True,
        "aggregate_from_database": True,
        "aggregate_schema": AGGREGATE_SCHEMA,
        "analysis_run_id": run_id,
        "analysis_generated_at": now,
        "analysis_input_sha256": hashlib.sha256(aggregate_id_basis.encode("utf-8")).hexdigest(),
        "etap": STAGE,
        "wersja_aplikacji": APP_VERSION,
        "schemat": "polski_interfejs_api_current_v1",
        "dlugosc_tekstu": total_chars,
        "dlugosc_tekstu_oryginalnego": total_original_chars,
        "database_stats": stats,
        "zbiorcze_dokumenty": documents,
        "zbiorczy_rejestr_kart": registry,
        "zbiorcze_referencje_sekcji": dict(section_refs),
        "zbiorcze_jednostki_znaczenia": units_sorted,
        "podsumowanie": {
            **{k: int(v) for k, v in summary_counts.items()},
            "dokumenty": analyzed_documents,
            "unikalne_karty_zbiorcze": len(registry),
            "unikalne_relacje_zbiorcze": len(relation_refs),
            "unikalne_jednostki_znaczenia": len(units_registry),
        },
        "p0": {
            "liczba_markerow": int(sum(p0_groups.values())),
            "liczba_grup": len(p0_groups),
            "wedlug_etykiet": dict(p0_groups.most_common()),
            "najczestsze_frazy": [{"phrase": phrase, "count": count} for phrase, count in p0_phrases.most_common(50)],
            "pelny_podglad_refy": list(section_refs.get("__p0_pelny_podglad", [])),
            "zasada": "P0 zbiorcze sumuje markery z zapisanych analiz. To sygnały, nie werdykt.",
        },
        "jakosc_analizy": {
            "schema": "analysis_quality_v1",
            "counts": dict(quality_counts),
            "review_risk": "aggregate",
            "warnings": ["To wynik zbiorczy z wielu dokumentów; ocena pojedynczego fragmentu wymaga otwarcia jego dokumentu źródłowego."],
        },
        "raport_czytelny": {
            "tytul": "Zbiorczy wynik całej bazy",
            "podtytul": "Wszystkie zapisane analizy połączone bez ponownej analizy dokumentów.",
            "items": readable_items,
            "do_sprawdzenia": [
                "Karty zbiorcze mogą pochodzić z wielu dokumentów; sprawdzaj listę dokumentów źródłowych przy karcie.",
                "Zbiorczy wynik nie ma jednego wspólnego tekstu do podświetlania.",
            ],
            "metryka": {
                "dokumenty": analyzed_documents,
                "unikalne_karty": len(registry),
                "relacje": len(relation_refs),
                "aktorzy": len(actor_refs),
                "sprawczosc": len(agency_refs),
            },
            "zasada": "Rejestr kart jest wspólny, a sekcje przechowują referencje. Duplikaty semantyczne są scalane wraz z listą dokumentów bazy.",
        },
        "uklad_sekcji": {
            "lewy_panel": [],
            "prawy_panel": right_panel,
            "schemat": "production_sections_current_v1",
            "tryb_pracy": "analiza_zbiorcza_bazy",
            "zasada": "Zbiorczy widok całej bazy bez ponownej analizy tekstu.",
        },
        "podglad_tekstu": {
            "tekst": "",
            "liczba_podswietlen": 0,
            "spany": [],
            "spany_surowe": [],
            "widoki": {},
            "zasada": "Wynik zbiorczy nie ma jednego tekstu źródłowego. Otwórz pojedynczy dokument z bazy, aby użyć podświetleń.",
        },
        "kontrakt_analizy": {
            "single_pipeline_active": True,
            "single_relation_source": True,
            "annotations_are_read_only": True,
            "aggregate_reads_saved_results_only": True,
        },
        "polityka": "Zbiorczy wynik czyta zapisane analizy SQLite, nie analizuje dokumentów ponownie. Każda karta zachowuje identyfikatory dokumentów bazy.",
        "wyjasnienie": {"title": "Jedna baza → jeden zbiorczy wynik", "summary": "Wspólny rejestr kart, sekcje jako referencje, pełna lista dokumentów źródłowych."},
        "raport_roboczy": (
            f"RAPORT ZBIORCZY — DROGOWSKAZY {APP_VERSION}\n\n"
            f"Dokumenty wykorzystane: {analyzed_documents}\n"
            f"Unikalne karty: {len(registry)}\n"
            f"Unikalne relacje wypowiedzi: {len(relation_refs)}\n"
            f"Unikalne jednostki znaczenia: {len(units_registry)}\n"
            f"Unikalne karty wymagające przeglądu: {sum(1 for card in registry.values() if card.get('wymaga_przegladu'))}\n"
            f"Źródła dokumentów: {len(sources)}\n"
            f"Wersje zapisanych analiz: {', '.join(f'{name}={count}' for name, count in versions.most_common()) or 'brak'}\n\n"
            "Wynik powstał przez połączenie zapisanych analiz. Dokumenty nie zostały ponownie przeanalizowane."
        ),
    }
    return result
