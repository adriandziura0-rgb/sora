# SORA 1.2.14 — etap 4 CLEAN, finalizacja

## Zmiany
- Scalenie eksportu HTML/JSON wybranych materiałów z istniejącą, wspólną funkcją `pobierzPlik`, obsługiwaną przez Android SAF i natywne PC WebView2.
- Usunięcie zbędnej alternatywnej implementacji Blob URL z `runtime_source/static/full-database.js`. Pozostałe raporty i cytaty już wywołują wspólną funkcję.
- Rozdzielenie diagnostyki (PDB, dokumentacja WebView2 XML, zrzuty prawdziwego okna i statusy testów) od paczki Windows użytkownika. Diagnostyka jest osobnym artefaktem `Sora-WINDOWS-DIAGNOSTYKA`.
- Finalne kontrole CLEAN, wersja aplikacji Android 1.2.14 (versionCode 17).

## Zamrożenie
- CORE i klasyfikator są **nietknięte**.
- 66 plików runtime; zmienia się wyłącznie `static/full-database.js`.
- Identyfikator silnika transferu `acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e`, nie zmienia się.
- Zmienia się SHA-256 całego runtime ZIP z `bee4fd3c9f67131e8d49cbf2789bce46fdfcde25610aeeb4e3566529e44cffd8` na `f590c1f6f78fa9dba4ef922f75eb24760661db52d36038683a04833cdcf9213b`, ponieważ UI jest nowy.
- SQLite, WAL i SHM nadal poza kodem instalacyjnym. Żaden test nie ingeruje w bazę użytkownika.

## Warunek wydania
1. Android: poprawny podpis i wersja, 257/257 GOLD, test SAF, raporty, cytaty, porównania, transfer.
2. Windows: natywny EXE + działający backend, test realnego okna, watchdog i ponowny test po rozpakowaniu.
3. Brak PDB i WebView2 XML w ZIP instalacyjnym, diagnostyka w osobnym archiwum.
4. Obie platformy przechodzą na tym samym commicie; po tym można udostępnić instalatory testowe CLEAN.

Nie odinstalowuj starego APK — wykonaj najpierw TRANSFER i instaluj na obecnej aplikacji, aby zachować jej dane.