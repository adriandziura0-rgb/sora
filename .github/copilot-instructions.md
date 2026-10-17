# Stałe instrukcje pracy GitHub Copilot — wszystkie zmiany

JĘZYK POLSKI. Zanim zaproponujesz patch lub napiszesz kod, przeczytaj [AGENTS.md](../AGENTS.md) oraz, gdy dotyczy Przewijak LIVE, [pełny MASTER](../docs/PRZEWIJAK_LIVE_MASTER_ZASADY_PRACY_ANALITYKA_v1_0.md).

**NIE ZMIENIAJ KODU PRZED AUDYTEM.** Wymagane: (1) stan repo/commit i reprodukcja; (2) analiza przyczyny i skutków; (3) mapa DAWCA→ODBIORCA, łącznie z faktycznym zapisem; (4) sprawdzenie kolizji/duplikatów/wyścigów/znikających danych; (5) inwentaryzacja OLD/martwych funkcji/podwójnych implementacji/łatek; (6) plan minimalnej zmiany, kopii bazy i rollbacku; (7) testy przed/po; (8) raport oparty na dowodach.

Nie kasuj ani nie nadpisuj baz, historii, sesji, działających wersji i elementów zamrożonego CORE. Nie zakładaj, że NULL = 0, build = poprawność działania lub że zielona kontrolka = zapis w SQLite. Nie twórz drugiego silnika, jeśli istniejący działa. Analizy i wskaźniki trzymaj poza źródłową bazą tam, gdzie tak określono architekturę.

Zmiany wprowadzaj w małych, audytowalnych krokach. Każdy patch wymaga oceny regresji. Weryfikuj PC/Android i realne warunki użytkowania, jeżeli dotyczy. Brak testu oznaczaj jawnie jako „NIEPRZETESTOWANE”. Nie usuwaj starego kodu, gdy nie wykazano jego nieużywania i nie zabezpieczono odtworzenia.

**Zakres domenowy:** specyficzne dla LIVE reguły MASTER_MATCH_UID, SOURCE_MATCH_UID i meczów nie mają zastosowania do Sora i artykułów, chyba że projekt jawnie takie dane obsługuje.
