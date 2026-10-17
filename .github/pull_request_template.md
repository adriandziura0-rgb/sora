# Zgłoszenie zmiany — obowiązkowy audyt przed wdrożeniem

## Rozpoznanie
- [ ] Sprawdzono repo, bazową i docelową gałąź, commity, wersję oraz rzeczywisty błąd/nową potrzebę.
- [ ] Zapisano przyczynę, dowody i wpływ na inne moduły. Bez tego zmiana nie może zostać zaakceptowana.

## Mapa danych DAWCA → ODBIORCA
- [ ] Wskazano źródło, parser, transport, odbiór, normalizację, zapis, odczyt, analitykę, ekran i eksport (w zakresie zmiany).
- [ ] Potwierdzono odbiór, kompletność i spójność danych; brakujące pola są jawnie odróżnione od zera.
- [ ] Zweryfikowano identyfikatory, kolizje, duplikaty, powtórzenia, opóźnienia, wyścigi i nieaktualne odpowiedzi.

## Czystość i ochrona
- [ ] Sprawdzono OLD, martwe funkcje, podwójne implementacje, przypadkowe łatki i niepotrzebne operacje.
- [ ] Zachowano zamrożony CORE, historię, bazy i zgodność schematu; każdą konieczną zmianę CORE udowodniono osobno.
- [ ] Przygotowano backup, rollback bez utraty nowych danych i analizę migracji (jeśli dotyczy).
- [ ] Nie wprowadzono niezamówionych zmian UI, sekretów, binariów, baz ani artefaktów do repo.

## Wykonane testy — wpisz wyniki, nie tylko zaznaczaj pola
- [ ] Unit/integracja: ...
- [ ] E2E/DAWCA→ODBIORCA i SQLite: ...
- [ ] Regresje i testy danych historycznych: ...
- [ ] Android (tło/łączność/wznowienie) i/lub Windows: ...
- [ ] Eksport/import, duplikaty, ponowienia: ...
- [ ] Zidentyfikowane testy nieprzeprowadzone oraz ryzyka: ...

## Wydanie i odbiór
**Co zmieniono:**

**Czego nie zmieniono:**

**Dowody (logi/raporty/commit):**

**Ryzyko / cofnięcie:**

**Decyzja: AKCEPTUJ / BLOKUJ / DO TESTÓW**

Regulamin: [AGENTS.md](../AGENTS.md) i [MASTER v1.0](../docs/PRZEWIJAK_LIVE_MASTER_ZASADY_PRACY_ANALITYKA_v1_0.md).
