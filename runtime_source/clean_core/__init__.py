"""Aktualny rdzeń aplikacji Drogowskazy.

Moduły są importowane jawnie przez aplikację; pakiet nie uruchamia pobocznych
warstw przez efekty uboczne importu.
"""

from .version import APP_NAME, APP_VERSION, STAGE

__all__ = ["APP_NAME", "APP_VERSION", "STAGE"]
