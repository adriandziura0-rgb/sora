from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


_AUDIT_SECTION_KEYS = {"visibility_audit", "degradation_audit", "role_audit"}


def _as_cards(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [card for card in value if isinstance(card, dict)]


def _card_key(card: Dict[str, Any]) -> str:
    relation_id = str(card.get("relation_id") or "").strip()
    if relation_id:
        return f"relation:{relation_id}"
    return "|".join(
        str(card.get(key) or "").strip().casefold()
        for key in ("label", "phrase", "fragment", "document_id")
    )


def _unique_cards(*collections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for collection in collections:
        for card in collection:
            if not isinstance(card, dict):
                continue
            key = _card_key(card)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(card)
    return out


def _examples(cards: Iterable[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        out.append(
            {
                "label": card.get("label"),
                "phrase": card.get("phrase"),
                "fragment": str(card.get("fragment") or "")[:180],
                "why": str(card.get("why") or "")[:220],
                "relation_id": card.get("relation_id"),
            }
        )
        if len(out) >= limit:
            break
    return out


def build_visibility_audit_cards(
    sections: Dict[str, Any],
    public_cards: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Audyt widoczności dla jedynego aktywnego runtime.

    Audyt nie tworzy nowych wyników merytorycznych. Porównuje pełne sekcje
    aktywnego modelu z ograniczonym publicznym rejestrem kart oraz TOP-em.
    Sekcje audytowe są pomijane w licznikach, żeby audyt nie liczył sam siebie.
    """
    list_sections: Dict[str, List[Dict[str, Any]]] = {
        key: _as_cards(value)
        for key, value in (sections or {}).items()
        if key not in _AUDIT_SECTION_KEYS and isinstance(value, list)
    }
    section_counts = {key: len(cards) for key, cards in list_sections.items()}
    total_section_cards = sum(section_counts.values())

    public_cards = _as_cards(public_cards)
    public_top = _as_cards(sections.get("public_top"))
    public_relations = _as_cards(sections.get("public_relations"))
    canonical_relations = _as_cards(sections.get("canonical_relations"))
    rejected_relations = _as_cards(sections.get("canonical_relation_rejections"))

    public_keys = {_card_key(card) for card in public_cards if _card_key(card)}
    all_unique = _unique_cards(*(cards for cards in list_sections.values()))
    unique_not_in_public = [card for card in all_unique if _card_key(card) not in public_keys]

    no_text_anchor = 0
    for card in all_unique:
        start = int(card.get("start", card.get("poczatek", -1)) or -1)
        end = int(card.get("end", card.get("koniec", -1)) or -1)
        phrase = str(card.get("phrase") or card.get("fraza") or "").strip()
        if start < 0 or end <= start or not phrase:
            no_text_anchor += 1

    top_sections: List[Tuple[str, int]] = sorted(
        section_counts.items(), key=lambda item: (-item[1], item[0])
    )[:12]
    top_sections_txt = "; ".join(
        f"{name}: {count}" for name, count in top_sections if count
    ) or "brak kart w sekcjach"

    return [
        {
            "label": "AUDIT_VISIBILITY_SUMMARY",
            "level": "INFO",
            "role": "VISIBILITY_AUDIT",
            "phrase": "audyt widoczności aktywnego runtime",
            "fragment": "",
            "why": (
                f"Unikalne karty w sekcjach aktywnego modelu: {len(all_unique)}; "
                f"public_cards: {len(public_cards)}; TOP: {len(public_top)}; "
                f"relacje publiczne: {len(public_relations)}; relacje kanoniczne: {len(canonical_relations)}; "
                f"odrzucone relacje: {len(rejected_relations)}; poza public_cards: {len(unique_not_in_public)}; "
                f"bez pewnej kotwicy tekstowej: {no_text_anchor}."
            ),
            "score": float(len(all_unique)),
            "rank_score": float(len(all_unique)),
            "evidence": {
                "karty_w_sekcjach_surowo": total_section_cards,
                "karty_w_sekcjach_unikalne": len(all_unique),
                "public_cards": len(public_cards),
                "public_top": len(public_top),
                "public_relations": len(public_relations),
                "canonical_relations": len(canonical_relations),
                "canonical_relation_rejections": len(rejected_relations),
                "unikalne_poza_public_cards": len(unique_not_in_public),
                "bez_pewnej_kotwicy_tekstowej": no_text_anchor,
                "documents": int(summary.get("documents", 0) or 0),
                "sekcje_top12": dict(top_sections),
                "przyklady_poza_public_cards": _examples(unique_not_in_public),
            },
        },
        {
            "label": "AUDIT_VISIBILITY_POLICY",
            "level": "INFO",
            "role": "VISIBILITY_AUDIT",
            "phrase": "polityka widoczności",
            "fragment": "",
            "why": (
                "Publiczny TOP i public_cards są skróconą projekcją. Pełne listy pozostają w sekcjach "
                f"aktywnego wyniku. Największe sekcje: {top_sections_txt}."
            ),
            "score": float(len(public_cards) + len(public_top)),
            "rank_score": float(len(public_cards) + len(public_top)),
            "evidence": {
                "single_pipeline_active": True,
                "audyt_tylko_odczytuje_aktywny_model": True,
                "najwieksze_sekcje": top_sections_txt,
            },
        },
    ]


def build_degradation_audit_cards(
    sections: Dict[str, Any],
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Jawny rejestr blokad, kandydatów i nieawansów w aktywnym runtime."""
    rejected = _as_cards(sections.get("canonical_relation_rejections"))
    p1_candidates = _as_cards(sections.get("p1_candidates"))
    structure = _as_cards(sections.get("structure_candidates"))
    semantic = _as_cards(sections.get("semantic_candidates"))
    candidate_union = _unique_cards(p1_candidates, structure, semantic)

    p2 = _as_cards(sections.get("p2_techniques"))
    p3 = _as_cards(sections.get("p3_frames"))
    p4 = _as_cards(sections.get("p4_strategies"))
    p5 = _as_cards(sections.get("p5_diagnoses"))
    promoted_higher = _unique_cards(p2, p3, p4, p5)

    p0_total = int(summary.get("p0_markers_total", 0) or 0)
    p0_promoted_estimate = min(p0_total, len(promoted_higher))
    p0_not_promoted_estimate = max(0, p0_total - p0_promoted_estimate)

    reason_summary = _as_cards(sections.get("rejection_reason_summary"))

    return [
        {
            "label": "AUDIT_DEGRADATION_SUMMARY",
            "level": "INFO",
            "role": "GATES_AND_DEGRADATIONS_AUDIT",
            "phrase": "bramki, degradacje i nieawansy",
            "fragment": "",
            "why": (
                f"Odrzucone relacje: {len(rejected)}; unikalni kandydaci P1: {len(candidate_union)}; "
                f"wyniki P2-P5: {len(promoted_higher)}; P0 bez awansu (szacunek): {p0_not_promoted_estimate}."
            ),
            "score": float(len(rejected) + len(candidate_union) + p0_not_promoted_estimate),
            "rank_score": float(len(rejected) + len(candidate_union) + p0_not_promoted_estimate),
            "evidence": {
                "odrzucone_relacje": len(rejected),
                "typy_przyczyn_odrzucen": len(reason_summary),
                "kandydaci_p1_unikalni": len(candidate_union),
                "kandydaci_p1_surowo": len(p1_candidates),
                "kandydaci_struktur": len(structure),
                "kandydaci_semantyczni": len(semantic),
                "wyniki_p2_p5_unikalne": len(promoted_higher),
                "p0_markery": p0_total,
                "p0_awansowane_szacunek": p0_promoted_estimate,
                "p0_nieawansowane_szacunek": p0_not_promoted_estimate,
                "przyklady_odrzucone": _examples(rejected),
                "przyklady_kandydaci": _examples(candidate_union),
            },
        },
        {
            "label": "AUDIT_DEGRADATION_RULE",
            "level": "INFO",
            "role": "GATES_AND_DEGRADATIONS_AUDIT",
            "phrase": "różnica: blokada, degradacja, nieawans",
            "fragment": "",
            "why": (
                "Blokada oznacza odrzucenie relacji przez walidator. Degradacja oznacza pozostawienie wyniku "
                "na poziomie kandydata. Nieawans oznacza, że sygnał niższego poziomu nie został uznany za "
                "wynik P2-P5. Szacunek awansu P0 nie jest mapowaniem 1:1."
            ),
            "score": 1.0,
            "rank_score": 1.0,
            "evidence": {
                "single_pipeline_active": True,
                "blokada": "odrzucona relacja kanoniczna",
                "degradacja": "kandydat pozostawiony do kontroli",
                "nieawans": "sygnał nie przeszedł do wyższego poziomu",
                "uwaga": "P0->P2/P3/P4/P5 jest raportowane tylko jako ostrożny szacunek, nie śledzenie 1:1.",
            },
        },
    ]
