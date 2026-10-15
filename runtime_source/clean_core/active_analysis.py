from __future__ import annotations

from typing import Any, Dict, List

from .agency_extractor import build_agency_cards
from .canonical_entity_builder import (
    build_canonical_affiliation_cards_from_relations,
    build_canonical_entity_cards_from_relations,
    build_canonical_source_cards_from_relations,
)
from .fact_opinion_quote import detect_fact_opinion_quote_cards, summarize_claim_types
from .pipeline_context import build_pipeline_context
from .public_projection import build_compact_public_sections
from .relation_pipeline import build_relation_pipeline
from .semantic_effectiveness import build_effectiveness_report_cards, build_semantic_frame_cards
from .role_audit import build_role_audit_cards
from .runtime_audits import build_degradation_audit_cards, build_visibility_audit_cards
from .version import STAGE



BLOCK_REASON_LABELS = {
    "unresolved_attribution": "Nie udało się jednoznacznie przypisać autora wypowiedzi",
    "unresolved_attribution_source": "Nie udało się jednoznacznie ustalić źródła wypowiedzi",
    "speaker_action_gender_mismatch": "Forma wypowiedzi nie pasuje do rozpoznanego mówcy",
    "claim_broken_start": "Początek wypowiedzi wygląda na urwany lub sklejony z metadanymi",
    "claim_incomplete_ending": "Koniec wypowiedzi wygląda na niepełny lub urwany",
    "claim_too_short": "Wypowiedź jest zbyt krótka, aby bezpiecznie ją przypisać",
    "invalid_document_source": "Niepoprawne lub niepewne źródło dokumentu",
    "inna_przyczyna": "Inna przyczyna odrzucenia",
}

def _sorted(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(cards, key=lambda c: (-float(c.get("rank_score", c.get("score", 0)) or 0), str(c.get("label", "")), str(c.get("fragment", ""))))




def _candidate_semantic_key(card: Dict[str, Any]) -> str:
    """Klucz deduplikacji kandydatów przed rankingiem i renderowaniem.

    Dwa detektory mogą opisać tę samą frazę inną etykietą. W publicznej
    warstwie ma pozostać jedna jednostka, a informacja o detektorach jest
    zachowana w ``detected_by_labels``.
    """
    import re
    text = str(card.get("fragment") or card.get("phrase") or "")
    text = re.sub(r"[„”\"]", "", text)
    text = re.sub(r"\s*[-–—]\s*(?:napisał|napisała|powiedział|powiedziała|dodał|dodała|stwierdził|stwierdziła|ocenił|oceniła|zaznaczył|zaznaczyła)\.?\s*$", "", text, flags=re.I)
    text = re.sub(r"[.!?,;:]+$", "", text.strip())
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def _dedupe_candidate_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}
    for source in cards:
        card = dict(source)
        key = _candidate_semantic_key(card)
        if not key:
            key = "|".join(str(card.get(k) or "").strip().casefold() for k in ("label", "phrase", "why"))
        existing = index.get(key)
        if existing is None:
            labels = [str(card.get("label") or "").strip()]
            card["detected_by_labels"] = [x for x in labels if x]
            index[key] = card
            out.append(card)
            continue
        label = str(card.get("label") or "").strip()
        labels = list(existing.get("detected_by_labels") or [])
        if label and label not in labels:
            labels.append(label)
        existing["detected_by_labels"] = labels
        existing["rank_score"] = max(float(existing.get("rank_score") or 0), float(card.get("rank_score") or 0))
        existing["score"] = max(float(existing.get("score") or 0), float(card.get("score") or 0))
    return out

def _public_annotation(card: Dict[str, Any]) -> Dict[str, Any]:
    """Usuwa z publicznej karty nazwy implementacyjne klasyfikatora."""
    out = dict(card)
    technical = {"scientificstructuralclassifier", "classifier", "canonicalentitybuilder", "canonicalrelation"}
    for key in ("source", "source_ref", "engine", "generator", "origin"):
        if str(out.get(key) or "").replace("_", "").casefold() in technical:
            out[key] = ""
    return out


def analyze_active(text: str) -> Dict[str, Any]:
    """Jedyny aktywny punkt analizy oparty na jednym rdzeniu relacji.

    Nie istnieje drugi pipeline relacji ani alternatywny analizator publiczny.
    Warstwy P0–P5 są adnotacjami nad tym samym tekstem i nie tworzą mówców.
    """
    # Import opóźniony: detektory P pozostają adnotatorami i nie uczestniczą w relacjach.
    from .classifier import (
        Card,
        detect_p0,
        detect_p1,
        detect_p2,
        detect_p4_p5,
        detect_semantic_candidates,
        linguistic_profile,
        normalize,
        p0_summary,
        result_quality,
    )

    pipeline = build_pipeline_context(text)
    normalized = normalize(pipeline.analyzable_text)
    cleaning = {
        "source_text": pipeline.analyzable_text,
        "meta_text": "",
        "metatext_segments": [],
        "removed_characters": int((pipeline.cleaning or {}).get("removed_characters", 0) or 0),
        "original_characters": int((pipeline.cleaning or {}).get("original_characters", len(pipeline.original_text)) or 0),
        "analyzable_characters": int((pipeline.cleaning or {}).get("analyzable_characters", len(pipeline.analyzable_text)) or 0),
        "sanitizer_removed_characters_approx": int((pipeline.cleaning or {}).get("sanitizer_removed_characters_approx", 0) or 0),
        "duplicate_documents_removed": int((pipeline.cleaning or {}).get("duplicate_documents_removed", 0) or 0),
        "duplicate_documents": list((pipeline.cleaning or {}).get("duplicate_documents", []) or []),
        "empty_documents_ignored": int((pipeline.cleaning or {}).get("empty_documents_ignored", 0) or 0),
        "empty_documents": list((pipeline.cleaning or {}).get("empty_documents", []) or []),
        "metatext_detected": bool(pipeline.metadata_segments),
    }

    relation_result = build_relation_pipeline(
        pipeline.relation_text,
        document_sources=pipeline.document_sources,
        image_sources=pipeline.image_sources,
        document_ids=pipeline.document_ids,
        document_metadata=pipeline.document_metadata,
        document_texts=pipeline.document_texts,
        segments=pipeline.segments,
    )
    accepted_cards = _sorted(list(relation_result["accepted_cards"]))
    rejected_cards = _sorted(list(relation_result["rejected_cards"]))
    compact = build_compact_public_sections(
        relation_result["accepted_relations"], relation_result["rejected_relations"], top_limit=5
    )

    # Current: P0-P5 są liczone osobno dla każdego document_id. Dzięki temu
    # żadna rama/technika nie może powstać przez sklejenie dwóch plików.
    p0, p1_all, candidates, p2, p3, p4, p5 = [], [], [], [], [], [], []
    # Current: detektory P działają lokalnie per dokument, ale UI podświetla jeden
    # znormalizowany tekst korpusu. Przeliczamy więc lokalne start/end na jeden
    # globalny układ współrzędnych zamiast traktować offset dokumentu 2 jak offset 0.
    document_offsets: Dict[str, int] = {}
    cursor = 0
    for _doc_id, _doc_text in pipeline.document_texts.items():
        _doc_norm = normalize(_doc_text)
        if not _doc_norm:
            continue
        document_offsets[_doc_id] = cursor
        cursor += len(_doc_norm) + 1  # normalize(analyzable_text) redukuje separator do jednej spacji

    for doc_id, doc_text in pipeline.document_texts.items():
        doc_norm = normalize(doc_text)
        if not doc_norm:
            continue
        dp0 = detect_p0(doc_norm)
        dp1 = detect_p1(doc_norm)
        dp1_decisions = [c for c in dp1 if c.role == "DECISION_SUGGESTION"]
        dcandidates = detect_semantic_candidates(doc_norm)
        dp2 = detect_p2(doc_norm, dp0, dp1_decisions, dcandidates)
        # Current: P3 dostaje strukturę akapitów. Pozostałe detektory zachowują
        # dotychczasowy znormalizowany tekst, więc nie zmieniamy ich kontraktu.
        doc_relation_cards = [
            card for card in accepted_cards
            if str(card.get("document_id") or "") == str(doc_id)
        ]
        dp3 = build_semantic_frame_cards(
            pipeline.document_structured_texts.get(doc_id, doc_text),
            {"canonical_relations": doc_relation_cards},
        )
        dp4, dp5 = detect_p4_p5(doc_norm, dp0, dp1, dp2, dcandidates)
        doc_offset = int(document_offsets.get(doc_id, 0))
        for collection in (dp0, dp1, dcandidates, dp2, dp3, dp4, dp5):
            for card in collection:
                if isinstance(card, dict):
                    card["document_id"] = doc_id
                    card["document_local_start"] = int(card.get("start", -1) or -1)
                    card["document_local_end"] = int(card.get("end", -1) or -1)
                    if card["document_local_start"] >= 0 and card["document_local_end"] > card["document_local_start"]:
                        card["start"] = card["document_local_start"] + doc_offset
                        card["end"] = card["document_local_end"] + doc_offset
                else:
                    try:
                        setattr(card, "document_id", doc_id)
                        local_start = int(getattr(card, "start", -1) or -1)
                        local_end = int(getattr(card, "end", -1) or -1)
                        setattr(card, "document_local_start", local_start)
                        setattr(card, "document_local_end", local_end)
                        if local_start >= 0 and local_end > local_start:
                            card.start = local_start + doc_offset
                            card.end = local_end + doc_offset
                    except Exception:
                        pass
        p0.extend(dp0); p1_all.extend(dp1); candidates.extend(dcandidates); p2.extend(dp2); p3.extend(dp3); p4.extend(dp4); p5.extend(dp5)
    p1_decisions = [c for c in p1_all if c.role == "DECISION_SUGGESTION"]

    claim_cards = _sorted(detect_fact_opinion_quote_cards(normalized, accepted_cards))
    actor_map = _sorted(build_canonical_entity_cards_from_relations(accepted_cards, pipeline.relation_text))
    source_map = _sorted(build_canonical_source_cards_from_relations(accepted_cards, pipeline.relation_text))
    affiliation_map = _sorted(build_canonical_affiliation_cards_from_relations(accepted_cards, pipeline.relation_text))
    agency_map = _sorted(build_agency_cards(pipeline.relation_text, accepted_cards))

    sections: Dict[str, Any] = {}
    # Current: jawne podsumowanie przyczyn blokad, bez przeglądania dziesiątek kart.
    reason_counts: Dict[str, int] = {}
    for rejected in relation_result["rejected_relations"]:
        reasons = list(rejected.get("reasons") or [])
        reason = str((reasons[0] if reasons else rejected.get("reason")) or "inna_przyczyna")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    rejection_reason_summary = [
        {
            "label": "Przyczyna blokady",
            "level": "INFO",
            "role": "REPORT_ONLY",
            "fragment": "",
            "phrase": BLOCK_REASON_LABELS.get(reason, reason),
            "why": f"{count} odrzuconych relacji",
            "technical_reason": reason,
            "score": count,
            "rank_score": count,
        }
        for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    sections.update({
        "canonical_relations": accepted_cards,
        "canonical_relation_rejections": rejected_cards,
        "public_relations": compact["relations"],
        "public_top": compact["top"],
        "blocked_by_guards": rejection_reason_summary[:5] + rejected_cards[:5],
        "rejection_reason_summary": rejection_reason_summary,
        # Current: nie obcinamy modelu danych do 15 kart. Limity są wyłącznie
        # prezentacyjne w UI; podsumowanie typu twierdzeń musi obejmować wszystkie relacje.
        "fact_opinion_quote": claim_cards,
        "claim_type_summary": [
            {"label": "Podsumowanie typu twierdzeń", "level": "INFO", "role": "REPORT_ONLY", "fragment": "", "phrase": x.get("typ", ""), "why": f"{x.get('typ')}: {x.get('liczba')}", "score": x.get("liczba", 0), "rank_score": x.get("liczba", 0)}
            for x in summarize_claim_types(claim_cards)
        ],
        "actor_map": actor_map[:10],
        "source_map": source_map[:10],
        "affiliation_map": affiliation_map[:10],
        "agency_map": agency_map[:15],
        "p0_raw_signals": _sorted([_public_annotation(c.to_dict()) for c in p0]),
        "p1_decisions": _sorted([_public_annotation(c.to_dict()) for c in p1_decisions]),
        "p1_candidates": _sorted([_public_annotation(c.to_dict()) for c in p1_all if c.role != "DECISION_SUGGESTION"]),
        "p2_techniques": _sorted([_public_annotation(c.to_dict()) for c in p2]),
        "p4_strategies": _sorted([_public_annotation(c.to_dict()) for c in p4]),
        "p5_diagnoses": _sorted([_public_annotation(c.to_dict()) for c in p5]),
        "semantic_candidates": _sorted(_dedupe_candidate_cards([_public_annotation(c.to_dict()) for c in candidates])),
        "structure_candidates": _sorted(_dedupe_candidate_cards([_public_annotation(c.to_dict()) for c in p1_all if c.role != "DECISION_SUGGESTION"])),
    })

    # Current: P3 jest wykrywane per document_id, nigdy na sklejonej całości.
    sections["p3_frames"] = _sorted([_public_annotation(c) if isinstance(c, dict) else _public_annotation(c.to_dict()) for c in p3])

    # Pełna mapa sprawczości pozostaje wewnętrznym źródłem kontroli integralności.
    # Publiczny widok nadal może być ograniczony do 15 kart.
    sections["_agency_projection_relation_ids"] = [
        str(card.get("relation_id") or "").strip() for card in agency_map if str(card.get("relation_id") or "").strip()
    ]

    # Current: centralny rejestr publicznych kart. Projekcje z tym samym relation_id
    # są jedną jednostką analityczną, niezależnie od miejsca prezentacji.
    # Publiczny rejestr jest celowo kompaktowy: najważniejsze relacje oraz ograniczona
    # liczba adnotacji. Pełne listy pozostają w sekcjach szczegółowych i eksporcie JSON.
    public_card_sources = [
        *compact["top"],
        *sections["p0_raw_signals"][:5],
        *sections["p1_decisions"][:3],
        *sections["structure_candidates"][:3],
        *sections["semantic_candidates"][:3],
        *sections["p2_techniques"][:3],
    ]
    public_cards: List[Dict[str, Any]] = []
    seen_public: set[str] = set()
    for card in public_card_sources:
        key = str(card.get("relation_id") or "").strip() or "|".join(
            str(card.get(k) or "").strip() for k in ("label", "phrase", "fragment")
        )
        if not key or key in seen_public:
            continue
        seen_public.add(key)
        public_cards.append(card)
    sections["public_cards"] = public_cards

    # Aktywny kontrakt: licznik „raport skuteczności” wskazuje realną kartę jakości,
    # zbudowaną z tego samego zestawu zaakceptowanych/odrzuconych relacji.
    # Nie tworzymy drugiego pipeline'u ani drugiego TOP-u.
    sections["semantic_effectiveness_report"] = build_effectiveness_report_cards(
        normalized, sections, {}
    )

    summary = {
        "accepted_relations": len(accepted_cards),
        "canonical_relations": len(accepted_cards),
        "rejected_relations": len(rejected_cards),
        "blocked_by_guards": len(rejected_cards),
        "public_relations": len(compact["relations"]),
        "public_top": len(compact["top"]),
        "top_relations": len(compact["top"]),
        "actor_map": len(sections["actor_map"]),
        "agency_map": len(sections["agency_map"]),
        "fact_opinion_quote": len(sections["fact_opinion_quote"]),
        "p0_raw_signals": len(sections["p0_raw_signals"]),
        "p0_markers_total": len(sections["p0_raw_signals"]),
        "p0_groups": len((p0_summary(p0).get("by_label") or {})),
        "p1_decisions": len(sections["p1_decisions"]),
        "p1_candidates": len(sections["p1_candidates"]),
        "structure_candidates": len(sections["structure_candidates"]),
        "semantic_candidates": len(sections["semantic_candidates"]),
        "p2_techniques": len(sections["p2_techniques"]),
        "p3_frames": len(sections["p3_frames"]),
        "p4_strategies": len(sections["p4_strategies"]),
        "p5_diagnoses": len(sections["p5_diagnoses"]),
        "public_card_count": len(public_cards),
        "rejection_reason_types": len(rejection_reason_summary),
        "documents": len(pipeline.document_ids),
        "semantic_effectiveness_report": len(sections["semantic_effectiveness_report"]),
    }

    # Audyty runtime: trzy sekcje audytowe są budowane dopiero po
    # złożeniu kompletnego aktywnego modelu. Są read-only i nie tworzą relacji.
    sections["role_audit"] = _sorted(build_role_audit_cards(sections))
    sections["degradation_audit"] = _sorted(build_degradation_audit_cards(sections, summary))
    sections["visibility_audit"] = _sorted(build_visibility_audit_cards(sections, public_cards, summary))
    summary.update({
        "role_audit": len(sections["role_audit"]),
        "degradation_audit": len(sections["degradation_audit"]),
        "visibility_audit": len(sections["visibility_audit"]),
    })

    return {
        "ok": True,
        "stage": STAGE,
        "schema": "drogowskazy_active_core_v2",
        "text_length": len(normalized),
        "original_text_length": len(pipeline.original_text),
        "tekst_znormalizowany": normalized,
        "text_cleaning": cleaning,
        "pipeline_segments": pipeline.segments,
        "pipeline_metadata_segments": pipeline.metadata_segments,
        "document": {
            "document_count": len(pipeline.document_ids),
            "document_ids": list(pipeline.document_ids),
            "sources": list(pipeline.document_sources),
            "metadata_by_document": dict(pipeline.document_metadata),
            "image_sources": list(pipeline.image_sources),
            "source_warnings": list(relation_result.get("metadata_source_warnings") or []),
            "segments": pipeline.segments,
        },
        "relations": accepted_cards,
        "rejected_relations": rejected_cards,
        "annotations": {
            "p0": sections["p0_raw_signals"], "p1": sections["p1_decisions"],
            "p2": sections["p2_techniques"], "p3": sections["p3_frames"],
            "p4": sections["p4_strategies"], "p5": sections["p5_diagnoses"],
        },
        "report": {"top": compact["top"], "relations": compact["relations"], "blocked": compact["blocked"]},
        "sections": sections,
        "summary": summary,
        "p0_summary": p0_summary(p0),
        "blocked_by_guards": rejected_cards[:10],
        "actor_map": actor_map[:10],
        "agency_map": agency_map[:15],
        "linguistic_profile": linguistic_profile(normalized, p0, p1_all, p2, candidates),
        "analysis_quality": result_quality(p0, p1_all, p2, candidates),
        "analysis_contract": {
            "single_relation_source": True,
            "relation_mutators": ["RelationResolver", "RelationValidator"],
            "annotations_are_read_only": True,
            "single_pipeline_active": True,
        },
        "explanation": {"title": "Jeden model danych", "summary": "Jedna relacja, jeden relation_id, czysty widok publiczny i osobna obsługa źródeł medialnych."},
        "policy": "Jeden produkcyjny pipeline, jeden kontrakt relacji i jeden interfejs.",
    }
