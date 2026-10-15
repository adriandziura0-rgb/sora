from __future__ import annotations

from typing import Any, Dict, List

from .canonical_relation import get_canonical_relation_cards
from .version import DISPLAY_STAGE

SCHEMAT_SEKCJI_PL = "panel_sekcji_current_v1"


def _lista(x: Any) -> list[Any]:
    return x if isinstance(x, list) else []


def _licz(x: Any) -> int:
    return len(_lista(x))


def _blok(
    identyfikator: str,
    tytul: str,
    opis: str,
    rodzaj: str,
    *,
    liczba: int = 0,
    otwarta: bool = False,
    status: str = "aktywna",
    zrodlo: str = "linia_t",
    uwaga: str = "",
) -> Dict[str, Any]:
    return {
        "id": identyfikator,
        "tytul": tytul,
        "opis": opis,
        "rodzaj": rodzaj,
        "liczba": liczba,
        "otwarta": otwarta,
        "status": status,
        "zrodlo": zrodlo,
        "uwaga": uwaga,
    }


def buduj_plan_sekcji_analizy(analiza_pl: Dict[str, Any]) -> Dict[str, Any]:
    """Publiczny plan aktualnych sekcji interfejsu."""
    sekcje = analiza_pl.get("sekcje", {}) or {}
    p0 = analiza_pl.get("p0", {}) or {}
    summary = analiza_pl.get("podsumowanie", {}) or {}
    p0_count = int(p0.get("liczba_markerow", 0) or 0)
    layer_count = sum(int(summary.get(key, 0) or 0) for key in (
        "markery_p0", "potwierdzone_p1", "techniki_p2", "ramy_p3", "strategie_p4", "diagnozy_p5"
    ))
    blocks = [
        _blok("top_relacji", "TOP najważniejszych relacji", "Najlepsze niepowtarzające się relacje.", "relacje", liczba=_licz(sekcje.get("top_wyniki")), otwarta=True),
        _blok("relacje_wypowiedzi", "Kto mówi → o kim → co mówi", "Jedyny publiczny rdzeń relacji.", "relacje", liczba=_licz(sekcje.get("relacje_wypowiedzi")), otwarta=True),
        _blok("aktorzy_sprawczosc", "Aktorzy i sprawczość", "Aktor, czynność i treść z tej samej relacji.", "relacje", liczba=_licz(sekcje.get("mapa_sprawczosci")), otwarta=True),
        _blok("fakt_opinia_cytat", "Fakt / opinia / cytat", "Status twierdzeń z tych samych relation_id.", "relacje", liczba=_licz(sekcje.get("fact_opinia_cytat")), otwarta=False),
        _blok("p_pomocnicze", "Warstwy analizy P0–P5", "Tylko faktycznie wykryte warstwy bieżącej analizy.", "pomocnicze", liczba=layer_count or p0_count, otwarta=False),
    ]
    blocks = [block for block in blocks if int(block.get("liczba", 0) or 0) > 0]
    return {
        "schemat": "production_sections_current_v1",
        "tryb_pracy": "analiza_relacji",
        "zasada": "Najpierw TOP i zaakceptowane relacje; warstwy analizy są pomocnicze, a pełny JSON jest dostępny wyłącznie jako eksport bieżącego wyniku.",
        "lewy_panel": [
            _blok("tekst_roboczy", "Tekst roboczy", "Pole tekstowe i akcje analizy.", "wejscie", liczba=int(analiza_pl.get("dlugosc_tekstu", 0) or 0), otwarta=True),
            _blok("tryby_widoku", "Tryby widoku", "Raport, relacje, P/R, podświetlenia i eksport.", "nawigacja", liczba=5, otwarta=True),
        ],
        "prawy_panel": blocks,
    }


def raport_roboczy_po_polsku(analiza_pl: Dict[str, Any]) -> str:
    p = analiza_pl.get("podsumowanie", {}) or {}
    sekcje = analiza_pl.get("sekcje", {}) or {}
    lines = [
        f"RAPORT ROBOCZY — DROGOWSKAZY {DISPLAY_STAGE}", "",
        "Cel: produkcyjny widok oparty na jednym kontrakcie relacji i jednej karcie relacji.", "",
        f"Długość tekstu: {analiza_pl.get('dlugosc_tekstu', 0)} znaków",
        f"TOP najważniejszych relacji: {len(sekcje.get('top_wyniki', []) or [])}",
        f"Kto mówi → o kim → co mówi: {len(sekcje.get('relacje_wypowiedzi', []) or [])}",
        f"Karty publiczne: {p.get('public_card_count', 0)}", "",
        "Zasada: speaker, claim, target, medium i program pochodzą z tej samej zaakceptowanej relacji.",
    ]
    return "\n".join(lines).strip() + "\n"
