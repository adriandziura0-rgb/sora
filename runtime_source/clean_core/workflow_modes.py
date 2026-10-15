from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List

from .version import STAGE


@dataclass(frozen=True)
class TrybPracy:
    id: str
    nazwa: str
    opis: str
    pokazuje: List[str]
    endpoint: str


TRYBY_PRACY: Dict[str, TrybPracy] = {
    "analiza": TrybPracy(
        id="analiza",
        nazwa="Analizuj",
        opis="Pełna bieżąca analiza: relacje, TOP, aktorzy, sprawczość, P0–P5 i audyty jakości.",
        pokazuje=[
            "TOP najważniejszych relacji",
            "kto mówi → o kim → co mówi",
            "aktorów i sprawczość",
            "P0–P5 jako warstwy pomocnicze",
            "audyty ról, widoczności i bramek",
        ],
        endpoint="/api/analizuj",
    ),
    "sugestie": TrybPracy(
        id="sugestie",
        nazwa="Szukaj sugestii",
        opis="Pomocnicze wskazówki do ręcznego przeglądu materiału; nie zastępują wyniku analizy.",
        pokazuje=["sugestie", "kandydatów do przeglądu", "P0 jako kontekst pomocniczy"],
        endpoint="/api/sugestie",
    ),
    "raport": TrybPracy(
        id="raport",
        nazwa="Raport / eksport",
        opis="Jednorazowy lokalny eksport aktualnego wyniku do Markdown i JSON.",
        pokazuje=["raport Markdown", "raport szczegółowy", "pełny JSON bieżącej analizy"],
        endpoint="/api/raport",
    ),
}


def lista_trybow_pracy() -> dict:
    return {
        "ok": True,
        "etap": STAGE,
        "zasada": "Wszystkie tryby korzystają z jednego aktualnego rdzenia; nie ma drugiego pipeline'u analizy.",
        "tryby": [asdict(v) for v in TRYBY_PRACY.values()],
    }
