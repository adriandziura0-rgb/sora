from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def build_expert_report_markdown(analysis_pl: Dict[str, Any], *, source_text: str = "") -> str:
    """Buduje ekspercki raport Markdown wyłącznie z bieżącego wyniku analizy."""
    p = analysis_pl.get("podsumowanie", {}) or {}
    s = analysis_pl.get("sekcje", {}) or {}
    clean = analysis_pl.get("czyszczenie_tekstu", {}) or {}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def section_cards(title: str, key: str, limit: int = 5) -> List[str]:
        out = [f"## {title}", ""]
        cards = s.get(key, []) or []
        if not cards:
            out += ["Brak.", ""]
            return out
        for i, c in enumerate(cards[:limit], 1):
            out += [
                f"### {i}. {c.get('tytul') or c.get('fraza') or c.get('kod_techniczny') or 'Karta'}",
                f"- Poziom: {c.get('poziom', '')}",
                f"- Rola: {c.get('rola', '')}",
                f"- Fraza: {c.get('fraza', '')}",
                f"- Fragment: {c.get('fragment', '')}",
                f"- Uzasadnienie: {c.get('uzasadnienie', '')}",
                "",
            ]
        return out

    lines: List[str] = [
        "# Raport ekspercki — Drogowskazy",
        "",
        f"Wygenerowano: {generated}",
        "",
        "## Zasada raportu",
        "",
        "Raport nie dodaje drugiej analizy. Składa bieżące wyniki P0–P5, role, dowody i elementy do kontroli człowieka.",
        "",
        "## Podsumowanie liczbowe",
        "",
        f"- P0 markery: {p.get('markery_p0', 0)}",
        f"- P1 potwierdzone: {p.get('potwierdzone_p1', 0)}",
        f"- P2 techniki: {p.get('techniki_p2', 0)}",
        f"- P3 ramy: {p.get('ramy_p3', 0)}",
        f"- P4 strategie: {p.get('strategie_p4', 0)}",
        f"- P5 diagnozy: {p.get('diagnozy_p5', 0)}",
        f"- Mapa aktorów: {p.get('mapa_aktorow', 0)}",
        f"- Mapa sprawczości: {p.get('mapa_sprawczosci', 0)}",
        "",
        "## Czyszczenie tekstu",
        "",
        f"- Metatekst wykryty: {clean.get('metatext_detected', False)}",
        f"- Usunięte znaki: {clean.get('removed_characters', 0)}",
        f"- Usunięte duplikaty dokumentów: {clean.get('duplicate_documents_removed', 0)}",
        "",
    ]
    lines += section_cards("Główna diagnoza P5", "diagnozy_p5", 3)
    lines += section_cards("Strategie P4", "strategie_p4", 5)
    lines += section_cards("Ramy P3", "ramy_p3", 8)
    lines += section_cards("Techniki P2", "techniki_p2", 10)
    lines += section_cards("Najważniejsze relacje", "top_wyniki", 10)
    lines += section_cards("Audyt ról relacji", "audyt_rol_relacji", 5)
    lines += section_cards("Audyt bramek i degradacji", "audyt_bramek_degradacji", 5)
    if source_text:
        excerpt = source_text.strip()
        lines += ["## Tekst źródłowy — podgląd", "", excerpt[:2500] + ("..." if len(excerpt) > 2500 else ""), ""]
    return "\n".join(lines).strip() + "\n"
