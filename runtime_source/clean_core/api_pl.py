from __future__ import annotations

import re

from typing import Any, Dict, List

from .sections import buduj_plan_sekcji_analizy, raport_roboczy_po_polsku
from .highlights import buduj_podglad_tekstu, uzupelnij_linki_kart_do_tekstu
from .canonical_relation import canonical_relation
from .entity_role_policy import is_public_entity_name
from .version import APP_VERSION

SCHEMAT_API_PL = "polski_interfejs_api_current_v1"

LABEL_PL = {
    "P1_kontrast": "Kontrast",
    "P1_falszywa_dychotomia": "Fałszywa dychotomia",
    "P1_pytanie_retoryczne": "Pytanie retoryczne",
    "P1_generalizacja": "Generalizacja",
    "P1_wyliczenie": "Wyliczenie retoryczne",
    "P1_insynuacja": "Insynuacja",
    "P1_hiperbola": "Hiperbola",
    "P1_metafora": "Metafora",
    "P1_personifikacja": "Personifikacja",
    "P1_eufemizacja": "Eufemizacja",
    "P1_jezyk_administracyjny": "Język administracyjny",
    "P1_nominalizacja": "Nominalizacja",
    "P1_ukrycie_sprawcy": "Ukrycie sprawcy",
    "P2_ramowanie_bezpieczenstwa": "Ramowanie bezpieczeństwa",
    "P2_polaryzacja": "Polaryzacja",
    "P2_manipulacja_narracyjna": "Manipulacja narracyjna",
    "P3_depolityzacja_decyzji": "Depolityzacja decyzji",
    "P3_naturalizacja_koniecznosci": "Naturalizacja konieczności",
    "P3_rozsadek_kontra_emocje": "Rozsądek kontra emocje",
    "P4_strategia_argumentacyjna": "Strategia argumentacyjna",
    "P4_strategia_legitymizacji": "Strategia legitymizacji",
    "P4_strategia_depolityzacji": "Strategia depolityzacji",
    "P4_strategia_naturalizacji": "Strategia naturalizacji konieczności",
    "P4_strategia_rozsadek_emocje": "Strategia rozsądek kontra emocje",
    "P5_diagnoza_syntetyczna": "Diagnoza syntetyczna",

    "FACT_OPINION_QUOTE_FAKT_OPISOWY": "Fakt opisowy",
    "FACT_OPINION_QUOTE_OPINIA_CYTOWANA": "Opinia cytowana",
    "FACT_OPINION_QUOTE_OPINIA_PRZYPISANA": "Opinia przypisana",
    "FACT_OPINION_QUOTE_CYTAT": "Cytat",
    "FACT_OPINION_QUOTE_OCENA_REDAKCYJNA_KANDYDAT": "Możliwa ocena redakcyjna",
    "FACT_OPINION_QUOTE_ZRODLO_MEDIUM": "Źródło/medium",
    "FACT_OPINION_QUOTE_PODSUMOWANIE": "Podsumowanie fakt/opinia/cytat",
    "SPEAKER_RELATION": "Kto mówi → o kim → co mówi",
    "ENTITY_GROUP": "Grupa aktorów / źródeł",
    "SEM_SOURCE_ROLE_CLASSIFIER": "Role źródeł i aktorów",
    "SEM_RELATION_MISSING": "Brak relacji wypowiedzi",
    "SEM_SPEAKER_RELATION_SUMMARY": "Kto mówi — podsumowanie relacji",
    "SEM_RELATION_COMPLETENESS": "Kompletność relacji wypowiedzi",
    "SEM_CLAIM_STATUS_SUMMARY": "Status fakt/opinia/cytat",
    "SEM_CLAIM_REVIEW_NEEDED": "Twierdzenia do kontroli",
    "SEM_P0_TO_P1_GATE_SUMMARY": "Bramka P0 → P1",
    "SEM_ALBO_MARKER_BLOCKED": "Marker albo bez awansu",
    "SEM_FRAME_POWAGA_KONTRA_SPEKTAKL": "P3 — powaga państwa kontra spektakl",
    "SEM_FRAME_ODPOWIEDZIALNOSC_KONTRA_UNIKANIE": "P3 — odpowiedzialność kontra unikanie",
    "SEM_FRAME_LEGALNOSC_KONTRA_GRA_POLITYCZNA": "P3 — legalność kontra gra polityczna",
    "SEM_FRAME_INSTYTUCJA_KONTRA_OSOBA": "P3 — instytucja kontra osoba",
    "SEM_FRAME_INWIGILACJA_KONTRA_UCZCIWOSC_WYBOROW": "P3 — inwigilacja opozycji kontra uczciwość wyborów",
    "SEM_FRAME_INWIGILACJA_KONTRA_STANDARDY_DEMOKRATYCZNE": "P3 — inwigilacja państwa kontra standardy demokratyczne",
    "SEM_FRAME_INWIGILACJA_JAKO_NARZEDZIE_WALKI_POLITYCZNEJ": "P3 — inwigilacja jako narzędzie walki politycznej",
    "SEM_FRAME_ODPOWIEDZIALNOSC_URZEDU_KONTRA_DYSTANSOWANIE": "P3 — odpowiedzialność urzędu kontra dystansowanie się",
    "SEM_FRAME_MEDIA_KONTRA_AKTOR": "P3 — źródło medialne kontra aktor",
    "SEM_ANALYSIS_EFFECTIVENESS_REPORT": "Integralność pipeline analizy",
    "VISIBILITY_AUDIT_SUMMARY": "Audyt widoczności — podsumowanie",
    "VISIBILITY_AUDIT_TOP_POLICY": "Audyt widoczności — polityka TOP",
    "VISIBILITY_AUDIT_NEXT_STEP": "Audyt widoczności — następny krok",
    "SUGGEST_P0_PREVIEW_GROUPING": "Grupuj surowe markery P0",
    "SUGGEST_KEEP_RELEVANCE_FILTER": "Zostaw filtr istotności",
    "NO_STRONG_P1_DECISIONS": "Brak mocnej techniki P1",
    "NO_STRONG_SUGGESTIONS": "Brak mocnych sugestii",
}

ROLE_PL = {
    "DECISION_SUGGESTION": "potwierdzona technika P1",
    "STRUCTURE_CANDIDATE": "kandydat struktury do przeglądu",
    "SEMANTIC_CANDIDATE": "kandydat semantyczny do przeglądu",
    "NARRATIVE_HYPOTHESIS": "rama narracyjna P3",
    "DISCOURSE_STRATEGY": "strategia dyskursywna P4",
    "SYNTHETIC_DIAGNOSIS": "diagnoza syntetyczna P5",
    "RAW_SIGNAL": "surowy marker P0",
    "SUGGESTION_ONLY": "sugestia rozwojowa",
    "REPORT_ONLY": "sekcja audytowa / raportowa",
    "BLOCKED_BY_GUARD": "zablokowane przez bramkę jakości",
    "CANDIDATE_RANKING": "ranking kandydatów 3P",
    "EVIDENCE_CHAIN": "łańcuch dowodowy P5",
    "EXPERT_SUGGESTION": "sugestia ekspercka",
    "EXPERT_REPORT": "raport ekspercki",
    "FACT_OPINION_QUOTE": "fakt / opinia / cytat",
    "MEDIA_STATEMENT_RELATION": "relacja wypowiedzi medialnej",
    "AGENCY_RELATION": "relacja sprawczości",
    "GROUPED_ENTITY_LIST": "zgrupowana lista aktorów/źródeł",
    "SEMANTIC_SOURCE_ROLE": "role źródeł i aktorów",
    "SEMANTIC_RELATION_QUALITY": "jakość relacji wypowiedzi",
    "SEMANTIC_CLAIM_STATUS": "status fakt/opinia/cytat",
    "SEMANTIC_P0_P1_GATE": "bramka P0 do P1",
    "SEMANTIC_FRAME_DETECTOR": "detektor ram P3",
    "SEMANTIC_EFFECTIVENESS_REPORT": "integralność pipeline analizy",
}

CONFIDENCE_PL = {
    "high": "wysoka",
    "medium": "średnia",
    "low": "niska",
}

RELEVANCE_PL = {
    "high": "wysoka",
    "medium": "średnia",
    "low": "niska",
}


def _etykieta(kod: str | None) -> str:
    if not kod:
        return "Bez etykiety"
    value = LABEL_PL.get(kod, kod.replace("_", " "))
    value = re.sub(r"\bR[0-3]\b", "", value, flags=re.I)
    value = re.sub(r"\bcanonical entity\b", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" -_")
    business_names = {
        "WYPOWIEDZ PRZYPISANA": "Wypowiedź przypisana",
        "OPINIA CYTOWANA": "Opinia cytowana",
        "OPINIA PRZYPISANA": "Opinia przypisana",
        "CYTAT PRZYPISANY": "Cytat przypisany",
        "FAKT OPISOWY": "Fakt opisowy",
    }
    return business_names.get(value.upper(), value or "Wynik analizy")


def _rola(kod: str | None) -> str:
    if not kod:
        return "brak roli"
    return ROLE_PL.get(kod, kod.replace("_", " ").lower())


def _pewnosc(kod: str | None) -> str:
    return CONFIDENCE_PL.get(str(kod or ""), str(kod or ""))


def _istotnosc(kod: str | None) -> str:
    return RELEVANCE_PL.get(str(kod or ""), str(kod or ""))


def karta_po_polsku(card: Dict[str, Any]) -> Dict[str, Any]:
    card = dict(card)
    for key in ("source", "source_ref", "engine", "generator", "origin"):
        value = str(card.get(key) or "")
        if value.replace("_", "").casefold() in {"scientificstructuralclassifier", "classifier", "canonicalentitybuilder", "canonicalrelation"}:
            card[key] = ""
    """Warstwa prezentacji: karta z polskimi nazwami pól.

    Nie usuwa technicznych identyfikatorów, ale trzyma je pod polami *_techniczny,
    żeby użytkownik widział polski opis, a testy i diagnostyka miały stabilny kod.
    """
    out: Dict[str, Any] = {
        "tytul": card.get("tytul_pl") or _etykieta(card.get("label")),
        "poziom": card.get("level"),
        "poziom_analizy": card.get("analysis_level", card.get("level")),
        "nazwa_poziomu_analizy": card.get("analysis_level_name", ""),
        "ranking": card.get("rank_score", 0),
        "rola": _rola(card.get("role")),
        "fraza": card.get("phrase", ""),
        "fragment": card.get("fragment", ""),
        "uzasadnienie": card.get("uzasadnienie_pl") or card.get("why", ""),
        "dzialanie": card.get("dzialanie_pl") or card.get("speaker_action") or card.get("action", ""),
        "status": card.get("status_pl") or ("Do przeglądu" if card.get("requires_review") else "Informacja"),
        # O2: osobno pokazujemy pewność dopasowania wzorca i pewność interpretacji.
        # Pole "pewnosc" zostaje jako ostrożna wartość ogólna dla stałego kontraktu UI.
        "pewnosc": _pewnosc(card.get("confidence")),
        "pewnosc_wzorca": _pewnosc(card.get("pattern_confidence", card.get("confidence"))),
        "pewnosc_interpretacji": _pewnosc(card.get("interpretation_confidence", card.get("confidence"))),
        "wynik": card.get("score", 0),
        "wymaga_przegladu": bool(card.get("requires_review")),
        "istotnosc_analityczna": _istotnosc(card.get("analytical_relevance")),
        "kod_techniczny": card.get("label"),
        "rola_techniczna": card.get("role"),
        "priorytet": card.get("priority_bucket") or card.get("priority", ""),
        "ranking_priorytetu": card.get("priority_rank", ""),
        "wynik_priorytetu": card.get("priority_score", ""),
        "poczatek": card.get("start", -1),
        "koniec": card.get("end", -1),
        "highlight_id": card.get("highlight_id", ""),
        "link_status": card.get("link_status", ""),
        "brak_podswietlenia_powod": card.get("brak_podswietlenia_powod", ""),
        "typ_twierdzenia": card.get("claim_type_pl", ""),
        "typ_twierdzenia_kod": card.get("claim_type", ""),
        "kto_mowi": card.get("speaker", ""),
        "o_kim": card.get("target", ""),
        "medium": card.get("medium", ""),
        "program": card.get("program", ""),
        "zrodlo_przywolane": card.get("source", ""),
        "zrodlo_dokumentu": card.get("document_source", ""),
        "zrodla_dokumentu": list(card.get("document_sources") or []),
        "zrodla_zdjec": list(card.get("image_sources") or []),
        "temat": card.get("topic", ""),
        "obiekt": card.get("object", ""),
        "marker_atrybucji": card.get("attribution_marker", ""),
        "relacja_wypowiedzi": card.get("statement_relation", {}),
        "canonical_relation": card.get("canonical_relation", {}),
        "relation_id": card.get("relation_id", ""),
        "surowa_pewnosc_relacji": card.get("raw_confidence", card.get("confidence", 0)),
        "dokumenty_potwierdzajace": list(card.get("supporting_document_ids") or []),
        "relacje_potwierdzajace": list(card.get("supporting_relation_ids") or []),
        "liczba_powtorzen_scalonych": int(card.get("deduped_repetitions_count") or 0),
        "document_id": card.get("document_id", ""),
        "document_index": card.get("document_index", 0),
        "entity_id": card.get("entity_id", ""),
        "canonical_name": card.get("canonical_name", ""),
        "entity_type": card.get("entity_type", ""),
        "entity_roles": card.get("entity_roles", []),
        "surface_forms": card.get("surface_forms", []),
        # Current: realny licznik wystąpień z kanonicznej mapy relacji. UI nie
        # może liczyć liczby powielonych kart jako liczby wzmianek.
        "mentions": int(card.get("mentions") or 0),
        "liczba_wzmianek": int(card.get("mentions") or 0),
        "source": card.get("source", ""),
        "affiliation": card.get("affiliation", ""),
        "lista_elementow": card.get("items", []),
        "frame_id": card.get("frame_id") or (card.get("label") if str(card.get("label") or "").startswith("SEM_FRAME_") else ""),
        "frame_label": card.get("frame_label") or (card.get("phrase") if str(card.get("label") or "").startswith("SEM_FRAME_") else ""),
        "evidence_text": card.get("evidence_text", ""),
        "dokladne_fragmenty_dowodowe": list(card.get("evidence_fragments") or []),
        "etykiety_wspierajace": list(card.get("supporting_labels") or []),
        "evidence_roles": list(card.get("evidence_roles") or []),
        "evidence_strength": card.get("evidence_strength", 0),
    }
    if card.get("part_a") or card.get("part_b"):
        out["czlony_struktury"] = {"a": card.get("part_a", ""), "b": card.get("part_b", "")}
    if card.get("examples"):
        out["przyklady"] = [karta_po_polsku(x) if isinstance(x, dict) else x for x in card.get("examples", [])]
    if card.get("grouped_counts"):
        out["liczniki_grup"] = card.get("grouped_counts")
    if card.get("count") is not None:
        out["liczba"] = card.get("count")
    if card.get("r_context_roles"):
        out["role_r_kontekst"] = card.get("r_context_roles")
    if card.get("r_context_note"):
        out["notatka_o_roli_r"] = card.get("r_context_note")
    if card.get("t24_score") is not None:
        out["t24_score"] = card.get("t24_score")
    if card.get("t24_priority"):
        out["t24_priorytet"] = card.get("t24_priority")
    if card.get("unit_rank"):
        out["miejsce_w_top"] = card.get("unit_rank")
    if card.get("actors"):
        out["aktorzy"] = card.get("actors")
    if card.get("sources"):
        out["zrodla"] = card.get("sources")
    for extra_key in ["function_type", "argument_role", "relation", "frame", "agency", "quote_status", "importance", "needs_review", "merged_layers_count"]:
        if card.get(extra_key) not in (None, ""):
            out[extra_key] = card.get(extra_key)
    if card.get("evidence"):
        out["dowody"] = card.get("evidence")
    if card.get("limits"):
        out["ograniczenia"] = card.get("limits")
    return out


def _lista_kart(cards: Any) -> List[Dict[str, Any]]:
    if not isinstance(cards, list):
        return []
    return [karta_po_polsku(c) for c in cards if isinstance(c, dict)]


def _p0_po_polsku(p0: Dict[str, Any] | None) -> Dict[str, Any]:
    p0 = p0 or {}
    return {
        "liczba_markerow": p0.get("total", 0),
        "liczba_grup": len(p0.get("by_label", {}) or {}),
        "wedlug_etykiet": p0.get("by_label", {}) or {},
        "najczestsze_frazy": p0.get("top_phrases", []) or [],
        "przyklady": p0.get("examples", {}) or {},
        "pelny_podglad": _lista_kart(p0.get("full_raw_preview", []) or []),
        "zasada": "P0 to surowe wskazówki. Nie są werdyktem ani decyzją P1.",
    }


def _podsumowanie_analizy(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Polskie liczniki są bezpośrednim odbiciem aktywnych sekcji core.

    Zwracamy wyłącznie liczniki sekcji należących do aktualnego kontraktu.
    """
    s = raw.get("summary", {}) or {}
    return {
        "diagnozy_p5": s.get("p5_diagnoses", 0),
        "strategie_p4": s.get("p4_strategies", 0),
        "ramy_p3": s.get("p3_frames", 0),
        "techniki_p2": s.get("p2_techniques", 0),
        "kandydaci_p1": s.get("p1_candidates", 0),
        "potwierdzone_p1": s.get("p1_decisions", 0),
        "kandydaci_struktur": s.get("structure_candidates", 0),
        "kandydaci_semantyczni": s.get("semantic_candidates", 0),
        "audyt_widocznosci": s.get("visibility_audit", 0),
        "audyt_bramek_degradacji": s.get("degradation_audit", 0),
        "audyt_rol_relacji": s.get("role_audit", 0),
        "markery_p0": s.get("p0_markers_total", 0),
        "grupy_p0": s.get("p0_groups", 0),
        "zablokowane_przez_bramki": s.get("blocked_by_guards", 0),
        "mapa_aktorow": s.get("actor_map", 0),
        "mapa_sprawczosci": s.get("agency_map", 0),
        "fact_opinion_quote": s.get("fact_opinion_quote", 0),
        "canonical_relation": s.get("canonical_relations", 0),
        "raport_skutecznosci_semantycznej": s.get("semantic_effectiveness_report", 0),
        "top_najwazniejszych_relacji": s.get("top_relations", 0),
        "public_card_count": s.get("public_card_count", 0),
        "dokumenty": s.get("documents", 0),
    }


def _clip_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].strip() + "…"


def _first_card(cards: Any) -> Dict[str, Any]:
    if isinstance(cards, list):
        for c in cards:
            if isinstance(c, dict):
                return c
    return {}


def _card_summary(card: Dict[str, Any], limit: int = 150) -> str:
    rel = card.get("relacja_wypowiedzi") if isinstance(card.get("relacja_wypowiedzi"), dict) else {}
    # Prezentacja: dla relacji wypowiedzi raport czytelny nie może pokazywać samego
    # urywka „co mówi”. Ma pokazać pełną oś: kto → o kim → co → medium/program.
    if rel:
        who = _clip_text(rel.get("kto_mowi"), 60)
        about = _clip_text(rel.get("o_kim"), 60)
        says = _clip_text(rel.get("co_mowi"), 90)
        medium = _clip_text(rel.get("medium"), 50)
        program = _clip_text(rel.get("program"), 50)
        bits = []
        if who:
            bits.append(who)
        if about:
            bits.append(f"o: {about}")
        if says:
            bits.append(f"mówi: {says}")
        if medium or program:
            bits.append("przez: " + " / ".join(x for x in [medium, program] if x))
        if bits:
            return _clip_text(" → ".join(bits), limit)
    for key in ["dzialanie", "uzasadnienie", "fragment", "fraza", "tytul"]:
        val = card.get(key)
        if val:
            return _clip_text(val, limit)
    return "Brak krótkiego opisu."


def _extract_names(cards: Any, limit: int = 6) -> List[str]:
    out: List[str] = []

    def add(value: Any) -> None:
        text = _clip_text(value, 70)
        if not text or not is_public_entity_name(text):
            return
        if text not in out:
            out.append(text)

    if isinstance(cards, list):
        for card in cards:
            if not isinstance(card, dict):
                continue
            items = list(card.get("lista_elementow") or [])
            if items:
                for item in items:
                    add(item)
                    if len(out) >= limit:
                        return out[:limit]
                # Karta grupująca ma nazwę kategorii w polu fraza. Nie dodajemy jej
                # jako szóstej fałszywej encji typu „Osoby”.
                continue
            for key in ("canonical_name", "kto_mowi", "medium", "source", "affiliation", "fraza"):
                add(card.get(key))
                if len(out) >= limit:
                    return out[:limit]
    return out[:limit]


def _claim_distribution(cards: Any) -> str:
    counts: Dict[str, int] = {}
    if isinstance(cards, list):
        for c in cards:
            if not isinstance(c, dict):
                continue
            name = c.get("typ_twierdzenia") or c.get("tytul") or "Inne"
            counts[str(name)] = counts.get(str(name), 0) + 1
    if not counts:
        return "Brak mocnego rozróżnienia fakt/opinia/cytat."
    ordered = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:4]
    return ", ".join(f"{name}: {count}" for name, count in ordered)




# Jednostki znaczenia — jednostki znaczenia: łączenie R/P po fragmencie.
def _safe_range(card: Dict[str, Any]) -> tuple[int, int]:
    try:
        start = int(card.get("poczatek", -1))
        end = int(card.get("koniec", -1))
    except Exception:
        return (-1, -1)
    if start >= 0 and end > start:
        return (start, end)
    return (-1, -1)


def _overlap_ratio(a: tuple[int, int], b: tuple[int, int]) -> float:
    if a[0] < 0 or b[0] < 0:
        return 0.0
    left = max(a[0], b[0])
    right = min(a[1], b[1])
    if right <= left:
        return 0.0
    smaller = max(1, min(a[1] - a[0], b[1] - b[0]))
    return (right - left) / smaller


def _first_nonempty(*values: Any) -> str:
    for v in values:
        text = _clip_text(v, 180)
        if text:
            return text
    return ""


def _unit_card_kind(card: Dict[str, Any]) -> str:
    hay = f"{card.get('tytul','')} {card.get('rola','')} {card.get('kod_techniczny','')} {card.get('typ_twierdzenia','')}".lower()
    if card.get("relacja_wypowiedzi") or "kto mówi" in hay or "relacja wypowiedzi" in hay:
        return "relacja"
    if "sprawczo" in hay or "agency" in hay or "mini-mapa" in hay:
        return "sprawczosc"
    if "źródło" in hay or "zrodlo" in hay or "medium" in hay or "source" in hay:
        return "zrodlo"
    if "aktor" in hay:
        return "aktor"
    if "opinia" in hay or "cytat" in hay or "fakt" in hay or card.get("typ_twierdzenia"):
        return "twierdzenie"
    if "rama" in hay or "p3" in hay:
        return "rama"
    if "p2" in hay or "hipotez" in hay:
        return "hipoteza"
    if "p1" in hay or "strukt" in hay:
        return "struktura"
    return "inne"


def _score_meaning_unit(cards: List[Dict[str, Any]]) -> int:
    kinds = {_unit_card_kind(c) for c in cards}
    score = len(cards)
    score += 8 if "relacja" in kinds else 0
    score += 7 if "sprawczosc" in kinds else 0
    score += 6 if "aktor" in kinds else 0
    score += 6 if "zrodlo" in kinds else 0
    score += 5 if "twierdzenie" in kinds else 0
    score += 4 if "rama" in kinds else 0
    score += 3 if "struktura" in kinds else 0
    if any(c.get("link_status") == "linked" for c in cards):
        score += 5
    return score


def _build_one_meaning_unit(idx: int, cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    rel_card = next((c for c in cards if _unit_card_kind(c) == "relacja"), {})
    agency_card = next((c for c in cards if _unit_card_kind(c) == "sprawczosc"), {})
    actor_card = next((c for c in cards if _unit_card_kind(c) == "aktor"), {})
    source_card = next((c for c in cards if _unit_card_kind(c) == "zrodlo"), {})
    claim_card = next((c for c in cards if _unit_card_kind(c) == "twierdzenie"), {})
    frame_card = next((c for c in cards if _unit_card_kind(c) == "rama"), {})
    structure_card = next((c for c in cards if _unit_card_kind(c) in {"struktura", "hipoteza"}), {})

    rel = rel_card.get("relacja_wypowiedzi") if isinstance(rel_card.get("relacja_wypowiedzi"), dict) else {}
    start_end = [_safe_range(c) for c in cards if _safe_range(c)[0] >= 0]
    start = min((x[0] for x in start_end), default=-1)
    end = max((x[1] for x in start_end), default=-1)
    main = rel_card or agency_card or claim_card or actor_card or source_card or frame_card or (cards[0] if cards else {})

    rr = canonical_relation(rel_card or main) if (rel_card or main) else {}
    rr_speaker = _first_nonempty(rr.get("speaker"), rr.get("actor"))
    rr_action = _first_nonempty(rr.get("speaker_action"), rr.get("action"))
    rr_target = _first_nonempty(rr.get("target"))

    return {
        "id": f"MU-{idx:02d}",
        "tytul": f"Jednostka znaczenia #{idx}",
        "fragment": _first_nonempty(main.get("fragment"), rel.get("co_mowi"), main.get("fraza"), main.get("uzasadnienie")),
        "aktor": _first_nonempty(rr_speaker, rel.get("kto_mowi"), actor_card.get("fraza"), actor_card.get("tytul"), main.get("kto_mowi")),
        "zrodlo": _first_nonempty(rr.get("source")),
        "zrodlo_dokumentu": _first_nonempty(rr.get("document_source")),
        "zrodla_dokumentu": list(rr.get("document_sources") or []),
        "zrodla_zdjec": list(rr.get("image_sources") or []),
        "medium": _first_nonempty(rr.get("medium")),
        "program": _first_nonempty(rr.get("program")),
        "marker_atrybucji": _first_nonempty(rr.get("attribution_marker")),
        "target": rr_target,
        "temat": _first_nonempty(rr.get("topic")),
        "obiekt": _first_nonempty(rr.get("object")),
        "typ_wypowiedzi": _first_nonempty(claim_card.get("typ_twierdzenia"), claim_card.get("tytul"), rel_card.get("typ_twierdzenia")),
        "sprawczosc": _first_nonempty(rr_action, agency_card.get("dzialanie"), agency_card.get("uzasadnienie"), agency_card.get("fragment")),
        "dotyczy": _first_nonempty(rr_target, rr.get("topic"), rel.get("o_kim"), rel_card.get("o_kim"), main.get("o_kim")),
        "rama": _first_nonempty(frame_card.get("tytul"), frame_card.get("uzasadnienie")),
        "struktura": _first_nonempty(structure_card.get("tytul"), structure_card.get("uzasadnienie")),
        "poczatek": start,
        "koniec": end,
        "link_status": "linked" if start >= 0 and end > start else "unlinked",
        "highlight_id": main.get("highlight_id") or (f"meaning_unit_{start}_{end}" if start >= 0 and end > start else ""),
        "liczba_polaczonych_kart": len(cards),
        "warstwy": sorted({_unit_card_kind(c) for c in cards}),
        "score": _score_meaning_unit(cards),
        "techniczne_karty": [
            {"tytul": c.get("tytul"), "poziom": c.get("poziom"), "kod": c.get("kod_techniczny"), "rola": c.get("rola_techniczna")}
            for c in cards[:8]
        ],
    }


def _meaning_unit_from_top_card(card: Dict[str, Any], idx: int) -> Dict[str, Any]:
    actors = card.get("aktorzy") if isinstance(card.get("aktorzy"), list) else []
    rr = canonical_relation(card)
    rr_speaker = _first_nonempty(rr.get("speaker"), rr.get("actor"))
    rr_action = _first_nonempty(rr.get("speaker_action"), rr.get("action"))
    rr_topic = _first_nonempty(rr.get("target"), rr.get("topic"), rr.get("object"), rr.get("claim_subject"))
    rr_claim = _first_nonempty(rr.get("claim"), card.get("audience_sense"), card.get("fragment"), card.get("fraza"))
    start, end = _safe_range(card)
    return {
        "id": f"T2TOP-{idx:02d}",
        "tytul": _first_nonempty(card.get("audience_title"), f"TOP jednostka znaczenia #{idx}"),
        "fragment": rr_claim,
        "relation_id": rr.get("relation_id", ""),
        "segment_id": rr.get("segment_id", ""),
        "canonical_relation": rr,
        "aktor": _first_nonempty(rr_speaker, actors[0] if actors else ""),
        "mowca": rr_speaker,
        "mowca_id": rr.get("speaker_entity_id", ""),
        "podmiot_twierdzenia": rr.get("claim_subject", ""),
        "dzialanie_mowcy": rr_action,
        "marker_atrybucji": rr.get("attribution_marker", ""),
        "dzialanie_twierdzenia": rr.get("claim_action", ""),
        "claim": rr_claim,
        "target": rr.get("target", ""),
        "temat": rr.get("topic", ""),
        "instytucja": rr.get("institution", ""),
        "afiliacja": rr.get("affiliation", ""),
        "zrodlo": rr.get("source", ""),
        "zrodlo_dokumentu": rr.get("document_source", ""),
        "zrodla_dokumentu": list(rr.get("document_sources") or []),
        "zrodla_zdjec": list(rr.get("image_sources") or []),
        "medium": rr.get("medium", ""),
        "program": rr.get("program", ""),
        "obiekt": rr.get("object", ""),
        "typ_wypowiedzi": _first_nonempty(card.get("function_type"), card.get("argument_role"), card.get("typ_twierdzenia")),
        "sprawczosc": rr_action,
        "dotyczy": rr_topic,
        "rama": _first_nonempty(card.get("frame")),
        "struktura": _first_nonempty(card.get("argument_role")),
        "pewnosc_relacji": rr.get("confidence", 0.0),
        "ostrzezenia_relacji": list(rr.get("warnings") or []),
        "poczatek": start,
        "koniec": end,
        "link_status": "linked" if start >= 0 and end > start else card.get("link_status", "unlinked"),
        "highlight_id": card.get("highlight_id") or (f"t2top_{start}_{end}" if start >= 0 and end > start else ""),
        "liczba_polaczonych_kart": int(card.get("merged_layers_count") or 1),
        "warstwy": ["TOP", "ranking"],
        "score": card.get("t24_score") or card.get("wynik") or card.get("importance") or 0,
        "priorytet": card.get("t24_priorytet") or card.get("t24_priority") or "",
        "wymaga_przegladu": bool(card.get("wymaga_przegladu") or card.get("needs_review")),
        "dowody_pomocnicze": card.get("supporting_evidence") or [],
        "liczba_powtorzen_scalonych": int(card.get("deduped_repetitions_count") or 0),
        "techniczne_karty": [{"tytul": card.get("tytul"), "poziom": card.get("poziom"), "kod": card.get("kod_techniczny"), "rola": card.get("rola_techniczna")}],
    }


def _build_top_meaning_units_for_view(top_cards: Any, limit: int = 5) -> List[Dict[str, Any]]:
    if not isinstance(top_cards, list):
        return []
    units = [_meaning_unit_from_top_card(c, i + 1) for i, c in enumerate(top_cards[:limit]) if isinstance(c, dict)]
    units.sort(key=lambda u: (-float(u.get("score") or 0), int(u.get("poczatek", 10**9) if u.get("poczatek", -1) >= 0 else 10**9)))
    for i, u in enumerate(units, 1):
        u["id"] = f"TOP-{i:02d}"
        u["tytul"] = f"TOP jednostka znaczenia #{i}"
    return units

def _build_readable_report_from_polish(wynik: Dict[str, Any]) -> Dict[str, Any]:
    """Buduje górny, czytelny raport bez technicznych payloadów.

    To adapter prezentacji nad jednym aktywnym wynikiem; nie uruchamia drugiej analizy.
    """
    sekcje = wynik.get("sekcje", {}) or {}
    podsumowanie = wynik.get("podsumowanie", {}) or {}

    p3_cards = list(sekcje.get("ramy_p3") or [])
    frame = _first_card(p3_cards)
    frames_by_document: Dict[str, Dict[str, Any]] = {}
    for p3 in p3_cards:
        if not isinstance(p3, dict):
            continue
        doc_id = str(p3.get("document_id") or "").strip()
        if not doc_id:
            continue
        current = frames_by_document.get(doc_id)
        score = float(p3.get("ranking") or p3.get("wynik") or p3.get("rank_score") or 0)
        current_score = float((current or {}).get("ranking") or (current or {}).get("wynik") or 0) if current else -1
        if current is None or score > current_score:
            frames_by_document[doc_id] = p3
    # Relacja główna pochodzi z jednego aktywnego TOP-u.
    relation = _first_card(sekcje.get("top_wyniki")) or _first_card(sekcje.get("relacje_wypowiedzi"))
    top_view_card = relation
    relation_id = str((relation or {}).get("relation_id") or "")
    agency_candidates = sekcje.get("mapa_sprawczosci") or []
    agency = next((c for c in agency_candidates if isinstance(c, dict) and str(c.get("relation_id") or "") == relation_id), {}) if relation_id else {}
    if not agency:
        agency = _first_card(agency_candidates)
    checklist = []

    # Current: „Najważniejsi” oznacza teraz najczęstszych w zaakceptowanych
    # relacjach, a nie pierwsze nazwy napotkane w korpusie. Mapa aktorów i mapa
    # źródeł są już sortowane po realnym ``mentions`` w core.
    actors: List[str] = _extract_names(sekcje.get("mapa_aktorow"), 6)
    sources: List[str] = _extract_names(sekcje.get("mapa_zrodel"), 5)

    all_doc_ids = list(((wynik.get("dokument") or {}).get("document_ids") or []))
    if frames_by_document or all_doc_ids:
        frame_lines = []
        ordered_doc_ids = all_doc_ids or sorted(frames_by_document)
        for i, doc_id in enumerate(ordered_doc_ids, 1):
            p3 = frames_by_document.get(doc_id)
            label = (p3.get("tytul") or _card_summary(p3, 90)) if p3 else "brak wykrytej ramy P3"
            frame_lines.append(f"Dokument {i}: {label}")
        frame_value = " | ".join(frame_lines)
        frame_title = "Główne ramy dokumentów"
        frame_desc = "Najmocniejsza lokalna rama P3 dla każdego dokumentu; nie udaje jednej ramy dla całego korpusu."
    else:
        frame_value = frame.get("tytul") or _card_summary(frame, 90) if frame else "Nie wykryto ram P3."
        frame_title = "Główna rama tekstu"
        frame_desc = "Najkrótsza interpretacja tego, jak pojedynczy tekst ustawia konflikt lub temat."
    if relation:
        agency_actor = _first_nonempty(relation.get("kto_mowi"), relation.get("mowca"), relation.get("aktor"))
        agency_action = _first_nonempty(relation.get("dzialanie"), "mówi")
        agency_claim = _first_nonempty(relation.get("fraza"), relation.get("claim"), relation.get("fragment"))
        agency_value = f"{agency_actor} → {agency_action} → {_clip_text(agency_claim, 120)}" if agency_actor and agency_claim else "Brak jednoznacznej mapy sprawczości."
    else:
        agency_value = "Brak jednoznacznej mapy sprawczości."
    if relation:
        speaker = _first_nonempty(relation.get("kto_mowi"), relation.get("mowca"), relation.get("aktor"))
        claim = _first_nonempty(relation.get("fraza"), relation.get("claim"), relation.get("fragment"), "wypowiedź do kontroli")
        action = _first_nonempty(relation.get("dzialanie"), "mówi")
        topic = _first_nonempty(relation.get("o_kim"), relation.get("temat"), relation.get("obiekt"))
        medium = _first_nonempty(relation.get("medium"))
        program = _first_nonempty(relation.get("program"))
        source = _first_nonempty(relation.get("zrodlo_przywolane"))
        document_source = _first_nonempty(relation.get("zrodlo_dokumentu"))
        context_bits = []
        if topic:
            context_bits.append(f"temat: {str(topic)[:70]}")
        if medium:
            context_bits.append(f"medium: {medium}")
        if program:
            context_bits.append(f"program: {program}")
        if source:
            context_bits.append(f"źródło przywołane: {source}")
        if document_source:
            context_bits.append(f"źródło dokumentu: {document_source}")
        context = f" ({'; '.join(context_bits)})" if context_bits else ""
        relation_value = f"{speaker} → {action} → {str(claim)[:150]}{context}" if speaker else "Brak pełnej atrybucji relacji — wynik nie został opublikowany jako kto mówi → co mówi."
    else:
        relation_value = "Brak pełnej relacji kto mówi → o kim → co mówi."
    claim_value = _claim_distribution(sekcje.get("fact_opinia_cytat"))

    checks: List[str] = []
    for c in checklist[:5] if isinstance(checklist, list) else []:
        if isinstance(c, dict):
            checks.append(_card_summary(c, 130))
    if not checks:
        checks = [
            "Sprawdź, czy cytaty mają pierwotne źródło i nie są wyrwane z kontekstu.",
            "Sprawdź, czy opinie cytowane nie są pokazane jak fakty redakcyjne.",
            "Sprawdź, czy aktor, działanie i odpowiedzialność są jasno nazwane.",
        ]

    # Current: jeden licznik kart publicznych pochodzi wyłącznie z core.
    liczba_kart = int(podsumowanie.get("public_card_count", 0) or 0)
    items = [
        {
            "tytul": frame_title,
            "wartosc": frame_value,
            "opis": frame_desc,
            "sekcja": "czyste",
        },
        {
            "tytul": "Najważniejsi aktorzy i źródła",
            "wartosc": ", ".join(actors[:6] + ([f"źródła: {', '.join(sources[:5])}"] if sources else [])) or "Brak wystarczająco czystej listy aktorów.",
            "opis": "Lista pochodzi z zaakceptowanych relacji i oddziela aktorów od źródeł oraz mediów.",
            "sekcja": "aktorzy",
        },
        {
            "tytul": "Główna sprawczość",
            "wartosc": agency_value,
            "opis": "Kto działa, kto mówi, kto znika w konstrukcji zdania i kto ponosi odpowiedzialność.",
            "sekcja": "sprawczosc",
        },
        {
            "tytul": "Relacja wypowiedzi",
            "wartosc": relation_value,
            "opis": "Najważniejsze powiązanie: kto mówi → o kim → co mówi → przez jakie medium.",
            "sekcja": "relacje",
        },
        {
            "tytul": "Typ materiału",
            "wartosc": claim_value,
            "opis": "Szybki rozkład faktów, opinii, cytatów i źródeł, żeby nie mieszać poziomów twierdzeń.",
            "sekcja": "fact",
        },
    ]

    return {
        "schemat": "czytelny_raport_current_v1",
        "tytul": "Wynik analizy",
        "podtytul": "Najpierw wynik dla odbiorcy: sens, role, dowody i rzeczy do kontroli. Szczegóły techniczne są niżej.",
        "items": items,
        "do_sprawdzenia": checks[:5],
        "metryka": {
            "liczba_kart_w_sekcjach": liczba_kart,
            "jednostki_znaczenia": len(wynik.get("jednostki_znaczenia") or []),
            "p0": podsumowanie.get("markery_p0", 0),
            "p3": podsumowanie.get("ramy_p3", 0),
            "aktorzy": podsumowanie.get("mapa_aktorow", 0),
            "sprawczosc": podsumowanie.get("mapa_sprawczosci", 0),
        },
        "zasada": "TOP, raport, klasyfikacja twierdzeń i mapa sprawczości korzystają z jednej zaakceptowanej relacji; źródło dokumentu, medium, program i źródło zdjęcia pozostają odrębnymi polami.",
    }

def analiza_po_polsku(raw: Dict[str, Any]) -> Dict[str, Any]:
    sec = raw.get("sections", {}) or {}
    wynik = {
        "ok": bool(raw.get("ok")),
        "etap": raw.get("stage"),
        "wersja_aplikacji": APP_VERSION,
        "schemat": SCHEMAT_API_PL,
        "dlugosc_tekstu": raw.get("text_length", 0),
        "dlugosc_tekstu_oryginalnego": raw.get("original_text_length", raw.get("text_length", 0)),
        "czyszczenie_tekstu": raw.get("text_cleaning", {}),
        "dokument": raw.get("document", {}),
        "podsumowanie": _podsumowanie_analizy(raw),
        "sekcje": {
            "top_wyniki": _lista_kart(sec.get("public_top", [])),
            "diagnozy_p5": _lista_kart(sec.get("p5_diagnoses", [])),
            "strategie_p4": _lista_kart(sec.get("p4_strategies", [])),
            "ramy_p3": _lista_kart(sec.get("p3_frames", [])),
            "techniki_p2": _lista_kart(sec.get("p2_techniques", [])),
            "kandydaci_p1": _lista_kart(sec.get("p1_candidates", [])),
            "potwierdzone_p1": _lista_kart(sec.get("p1_decisions", [])),
            "kandydaci_struktur": _lista_kart(sec.get("structure_candidates", [])),
            "kandydaci_semantyczni": _lista_kart(sec.get("semantic_candidates", [])),
            "audyt_widocznosci": _lista_kart(sec.get("visibility_audit", [])),
            "audyt_bramek_degradacji": _lista_kart(sec.get("degradation_audit", [])),
            "audyt_rol_relacji": _lista_kart(sec.get("role_audit", [])),
            "fact_opinia_cytat": _lista_kart(sec.get("fact_opinion_quote", [])),
            "relacje_wypowiedzi": _lista_kart(sec.get("canonical_relations", [])),
            "podsumowanie_typow_twierdzen": _lista_kart(sec.get("claim_type_summary", [])),
            "raport_skutecznosci_semantycznej": _lista_kart(sec.get("semantic_effectiveness_report", [])),
            "zablokowane_przez_bramki": _lista_kart(sec.get("blocked_by_guards", [])),
            "podsumowanie_przyczyn_blokad": _lista_kart(sec.get("rejection_reason_summary", [])),
            "mapa_aktorow": _lista_kart(sec.get("actor_map", [])),
            "mapa_zrodel": _lista_kart(sec.get("source_map", [])),
            "mapa_afiliacji": _lista_kart(sec.get("affiliation_map", [])),
            "mapa_sprawczosci": _lista_kart(sec.get("agency_map", [])),
        },

        "p0": _p0_po_polsku(raw.get("p0_summary")),
        "wyjasnienie": raw.get("explanation", {}),
        "jakosc_analizy": raw.get("analysis_quality", {}),
        "profil_jezykowy": raw.get("linguistic_profile", {}),
        "kontrakt_analizy": raw.get("analysis_contract", {}),
        "polityka": "Jeden kontrakt relacji zasila wynik, TOP, kartę relacji, raport i eksport; widok użytkownika ma pięć głównych wejść, a szczegóły pozostają w trybie Ekspert.",
    }
    uzupelnij_linki_kart_do_tekstu(raw.get("tekst_znormalizowany", ""), wynik)
    # Widok startowy korzysta z jednego TOP-u zaakceptowanych relacji.
    # Linkowanie powyżej uzupełniło zakresy w polskiej projekcji TOP. Jednostki
    # muszą powstać z tej samej, już podłączonej listy, a nie ponownie z surowego
    # ``public_top`` (to wcześniej zerowało początek/koniec i highlight_id).
    top_units = list((wynik.get("sekcje") or {}).get("top_wyniki") or [])
    # Current: jednostki znaczenia są wyłącznie projekcją public_top; brak TOP nie jest maskowany bocznym fallbackiem.
    wynik["jednostki_znaczenia_surowe"] = []
    wynik["jednostki_znaczenia"] = _build_top_meaning_units_for_view(top_units, limit=5)
    wynik["raport_czytelny"] = _build_readable_report_from_polish(wynik)
    wynik["uklad_sekcji"] = buduj_plan_sekcji_analizy(wynik)
    wynik["podglad_tekstu"] = buduj_podglad_tekstu(raw.get("tekst_znormalizowany", ""), wynik)
    wynik["raport_roboczy"] = raport_roboczy_po_polsku(wynik)
    return wynik


def sugestie_po_polsku(raw: Dict[str, Any]) -> Dict[str, Any]:
    wynik = {
        "ok": bool(raw.get("ok")),
        "etap": raw.get("stage"),
        "wersja_aplikacji": APP_VERSION,
        "schemat": SCHEMAT_API_PL,
        "podsumowanie": raw.get("podsumowanie_sugestii", {}),
        "sugestie": _lista_kart(raw.get("suggestions", [])),
        "liczba_sugestii": raw.get("suggestions_count", 0),
        "p0": _p0_po_polsku(raw.get("p0_summary")),
        "czyszczenie_tekstu": raw.get("text_cleaning", {}),
        "jakosc_analizy": raw.get("analysis_quality", {}),
        "profil_jezykowy": raw.get("linguistic_profile", {}),
        "kontrakt_analizy": raw.get("analysis_contract", {}),
        "polityka": "Sugestie są osobnym trybem pracy. Pokazują wskazówki rozwojowe i kandydatów, ale nie są werdyktem ani decyzją P1.",
    }
    wynik["uklad_sekcji"] = buduj_plan_sekcji_analizy(wynik)
    return wynik
