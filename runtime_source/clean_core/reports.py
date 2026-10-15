from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from .expert_report import build_expert_report_markdown
from .version import APP_VERSION

SCHEMAT_RAPORTU_PL = "raport_current_v1"


def _lista(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _txt(x: Any) -> str:
    return str(x or "").strip()


def _line(label: str, value: Any) -> str:
    return f"- **{label}:** {value}"


def _sekcja_kart(tytul: str, cards: Iterable[Dict[str, Any]], limit: int = 20) -> List[str]:
    rows = [f"## {tytul}", ""]
    items = list(cards)[:limit]
    if not items:
        rows += ["Brak.", ""]
        return rows
    for idx, k in enumerate(items, 1):
        rows.append(f"### {idx}. {_txt(k.get('poziom'))} · {_txt(k.get('tytul')) or 'Trafienie'}")
        if k.get("rola"):
            rows.append(_line("Rola", k.get("rola")))
        if k.get("fraza"):
            rows.append(_line("Fraza", f"`{_txt(k.get('fraza'))}`"))
        rel = k.get("relacja_wypowiedzi") if isinstance(k.get("relacja_wypowiedzi"), dict) else {}
        if rel:
            if rel.get("kto_mowi"):
                rows.append(_line("Kto mówi", _txt(rel.get("kto_mowi"))))
            if rel.get("o_kim"):
                rows.append(_line("O kim", _txt(rel.get("o_kim"))))
            if rel.get("co_mowi"):
                rows.append(_line("Co mówi", _txt(rel.get("co_mowi"))[:700]))
        frag = _txt(k.get("fragment"))
        if frag:
            rows.append(_line("Fragment", frag[:700]))
        if k.get("uzasadnienie"):
            rows.append(_line("Uzasadnienie", _txt(k.get("uzasadnienie"))))
        rows.append("")
    return rows


def generuj_raport_markdown(analiza_pl: Dict[str, Any], tekst_zrodlowy: str = "") -> str:
    """Generuje raport wyłącznie z aktualnego publicznego wyniku analizy."""
    p = analiza_pl.get("podsumowanie", {}) or {}
    s = analiza_pl.get("sekcje", {}) or {}
    clean = analiza_pl.get("czyszczenie_tekstu", {}) or {}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: List[str] = [
        "# Drogowskazy — raport",
        "",
        f"**Wygenerowano:** {generated}",
        f"**Schemat:** {SCHEMAT_RAPORTU_PL}",
        f"**Wersja aplikacji:** {APP_VERSION}",
        f"**Identyfikator analizy:** {_txt(analiza_pl.get('analysis_run_id')) or 'brak'}",
        "",
        "## Podsumowanie",
        "",
        _line("Dokumenty", p.get("dokumenty", 0)),
        _line("Relacje", p.get("canonical_relation", 0)),
        _line("TOP", p.get("top_najwazniejszych_relacji", 0)),
        _line("P0 — markery", p.get("markery_p0", 0)),
        _line("P1 — potwierdzone", p.get("potwierdzone_p1", 0)),
        _line("P2 — techniki", p.get("techniki_p2", 0)),
        _line("P3 — ramy", p.get("ramy_p3", 0)),
        _line("P4 — strategie", p.get("strategie_p4", 0)),
        _line("P5 — diagnozy", p.get("diagnozy_p5", 0)),
        _line("Odrzucone przez bramki", p.get("zablokowane_przez_bramki", 0)),
        _line("Usunięte duplikaty dokumentów", clean.get("duplicate_documents_removed", 0)),
        _line("Usunięte znaki", clean.get("removed_characters", 0)),
        "",
    ]

    lines += _sekcja_kart("TOP najważniejszych relacji", _lista(s.get("top_wyniki")), 10)
    lines += _sekcja_kart("Kto mówi → o kim → co mówi", _lista(s.get("relacje_wypowiedzi")), 30)
    lines += _sekcja_kart("P5 — diagnozy", _lista(s.get("diagnozy_p5")), 10)
    lines += _sekcja_kart("P4 — strategie", _lista(s.get("strategie_p4")), 10)
    lines += _sekcja_kart("P3 — ramy", _lista(s.get("ramy_p3")), 20)
    lines += _sekcja_kart("P2 — techniki", _lista(s.get("techniki_p2")), 20)
    lines += _sekcja_kart("P1 — potwierdzone", _lista(s.get("potwierdzone_p1")), 20)
    lines += _sekcja_kart("Audyt ról", _lista(s.get("audyt_rol_relacji")), 10)
    lines += _sekcja_kart("Audyt widoczności", _lista(s.get("audyt_widocznosci")), 10)
    lines += _sekcja_kart("Audyt bramek", _lista(s.get("audyt_bramek_degradacji")), 10)

    if tekst_zrodlowy:
        excerpt = tekst_zrodlowy.strip()
        lines += ["## Tekst źródłowy — podgląd", "", excerpt[:2500] + ("..." if len(excerpt) > 2500 else ""), ""]

    return "\n".join(lines).strip() + "\n"


def generuj_pakiet_eksportu(analiza_pl: Dict[str, Any], tekst_zrodlowy: str = "") -> Dict[str, Any]:
    markdown = generuj_raport_markdown(analiza_pl, tekst_zrodlowy=tekst_zrodlowy)
    detailed = build_expert_report_markdown(analiza_pl, source_text=tekst_zrodlowy)
    return {
        "ok": True,
        "schemat": SCHEMAT_RAPORTU_PL,
        "wersja_aplikacji": APP_VERSION,
        "formaty": ["markdown", "json", "detailed_markdown"],
        "raport_markdown": markdown,
        "raport_szczegolowy_markdown": detailed,
        "raport_json": analiza_pl,
        "analysis_run_id": analiza_pl.get("analysis_run_id", ""),
        "analysis_input_sha256": analiza_pl.get("analysis_input_sha256", ""),
        "analysis_generated_at": analiza_pl.get("analysis_generated_at", ""),
        "single_run_export": True,
        "nazwa_pliku_markdown": "drogowskazy_raport.md",
        "nazwa_pliku_raportu_szczegolowego": "drogowskazy_raport_szczegolowy.md",
        "nazwa_pliku_json": "drogowskazy_raport.json",
    }
