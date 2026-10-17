# STAN PRAC I NASTĘPNY KROK — Drogowskazy SORA — analizy artykułów

**Utworzono:** 2026-10-17 • **TASK_ID:** `SORA-AUDYT0-001` • **Status:** `T01 FAIL 3→6 / T02 REAL PY PASS / T03 FAIL A→B→A / P0-P1 NIEWDROŻONE`  
**Repozytorium:** https://github.com/adriandziura0-rgb/sora  
**HEAD kodu sprawdzany PRZED dodaniem dokumentacji:** `main` @ `28f5b698105e522c7d2658776a2382f46bc1e7b9`. Ten SHA jest **punktem odczytu**, nie dowodem najnowszego działającego produktu.  
**Standard uniwersalny:** [UNIWERSALNY STANDARD v1.0](https://github.com/adriandziura0-rgb/przewijarka-app/blob/main/docs/UNIWERSALNY_STANDARD_PRACY_I_KONTYNUACJI_v1_0.md). Dodatkowo obowiązuje lokalny `AGENTS.md`; MASTER LIVE tylko w odpowiedniej domenie.

## 1. Co sprawdzono i co wiadomo

`main` w repozytorium nie jest aktywną gałęzią rozwojową. Ostatni zweryfikowany kod produktu wskazany w planie to **1.2.17** na gałęzi `sora-full-html-snapshot-1.2.17-20261016`, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`. Odrębna gałąź dokumentacyjna: `sora-plan-prac-20261016`.

**Dowody i dokumentacja:** [Audyt-0 — DAWCA/ODBIORCA/CLEAN](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/AUDYT_0_SORA_1_2_17_DAWCA_ODBIORCA_CZYSTOSC_2026-10-16.md), [plan A1–A5](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/PLAN_PRAC_I_STAN_SORA_2026-10-16.md), [lokalne zasady](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md).

## 2. Stan zadania

- **Zakończone/dowiedzione:** Audyt statyczny 11 ścieżek zapisany; T01 na rzeczywistych fragmentach JS w izolowanym V8 wykazał 3 pliki odczytane 6 razy, przekazanie jednego pakietu 3 dokumentów i brak automatycznego zapisu SQLite. Zielone poprzednie CI Android/Windows 1.2.17 pozostaje punktem odniesienia, **nie obejmuje naprawy T01**.
- **Otwarte / BLOKADA:** T01: podwójny skan 3→6; T02: rzeczywiste moduły Python z APK 1.2.17 potwierdzają, że identyczny artykuł w drugim folderze zapisuje zdarzenie duplikatu, lecz nie staje się drugim przypisaniem w raporcie; decyzja kontraktu unikalna treść/wystąpienia nadal OTWARTA. T03: realny JS przy A→B→A pokazuje stary wynik i pozwala go eksportować. Otwarte limity list 12/60.
- **Testy wykonane:** **T01 — czerwony 3→6** na rzeczywistym JS; T02 — **4/4 PASS reprodukcji na oryginalnych modułach Python z APK 1.2.17**, cztery tymczasowe bazy, wszystkie integralność i FK OK, zweryfikowane blob SHA; T03 — **źródłowy JS w V8: stary wynik, eksport, błąd i blokada A2 potwierdzone**, `--audit` PASS, `--gate` FAIL. **GitHub Actions dla testu T01 miało `startup_failure`, bez jobs**; fizyczne testy Android/Windows po naprawach NOT_RUN. Brak poprawek, zmian CORE/SQLite i nowych wydań.
- **DAWCA → ODBIORCA:** do potwierdzenia na rzeczywistym torze podanym w kroku poniżej; nie udawać, że wszystkie ogniwa już sprawdzono.
- **Kolizje i CLEAN:** istniejące hipotezy/raporty trzeba prześledzić do SHA i testu; żadnego kasowania `OLD` ani automatycznej przebudowy.
- **CORE, baza, historia, program:** **nietknięte**. Nie nadpisano SQLite, schematu, par wyników ani skryptów produktu.

## 3. Jeden następny krok — zaczynać TUTAJ

**Kolejny dokładny krok: P0 — przygotować i przetestować MINIMALNĄ zmianę eliminującą drugi skan w `import-recovery.js` / `app.js` przy zachowaniu limitu 1800 KiB, drogi do bazy i anulowania. Najpierw graf odpowiedzialności i test T01, potem mały fix i regresja. T02 (związany ze zmianą schematu) pozostaje wstrzymany do decyzji o kontrakcie liczników; T03 gotowy do późniejszej oddzielnej poprawki P1. Nie łączyć P0/P1 w jeden commit.**

**Kryterium GO/NO-GO:** T01–T03 mają logi PASS/FAIL i minimalny plan. Zmiana schema SQLite tylko po osobnej decyzji i rollback.

**Punkt powrotu:** ostatni potwierdzony commit **kodu aplikacji** i oddzielna spójna kopia danych użytkownika przed przyszłą zmianą; nie cofać zapisanej historii. Bez wskazanego testu i kopii nie wdrażać poprawki.

## 4. Zasada kontynuacji bez powtórzeń

Przy następnej rozmowie przeczytać **ten rejestr → lokalny AGENTS.md → wskazany plan/audyt → HEAD/zmienione pliki**. Zmienić status dopiero po wykonanym zadaniu i wyniku testu. Jeżeli SHA aplikacji się nie zmienił, **nie ponawiać całego audytu**: sprawdzić tylko konkretną lukę lub nowy dowód. Każde kolejne wykonane zadanie aktualizuje wpis lub dopisuje nowe TASK_ID, nie tworzy konkurencyjnego `PLAN_FINAL_2`.

## 5. Szablon wpisu kończącego następny test

```text
TASK_ID:
KOD: repo / branch / SHA / wersja:
DAWCA → ODBIORCA: dowód na obu końcach:
DIAGNOZA: fakt / hipoteza / niezweryfikowane:
CLEAN: stare/nowe implementacje, zależności, brak nowej duplikacji:
TESTY: PASS / FAIL / BLOCKED / NOT_RUN + log:
ZMIANY: (brak lub diff, osobny commit):
DANE / CORE: stan przed/po, backup:
DECYZJA: GO / NO-GO / ROLLBACK:
NASTĘPNY JEDEN KROK:
```

**Uwaga:** ten dokument jest początkową migawką wiedzy, nie automatycznym monitoringiem GitHuba. Każda kolejna osoba/asystent musi zweryfikować faktyczny branch, kod i datę przed aktualizacją.


## 6. Kontynuacja po teście T01 (2026-10-17)

**TASK_ID:** `SORA-T01-FOLDER-SCAN` — **odtworzony czerwony test; fix nie wykonany**.

**Kod bazowy:** `sora-full-html-snapshot-1.2.17-20261016` @ `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.  
**Izolowana gałąź testowa:** `sora-t01-reprodukcja-skanu-20261017`.

- [Raport T01: dawca/odbiorca, 3→6, przypadek dużego folderu, ograniczenia](https://github.com/adriandziura0-rgb/sora/blob/sora-t01-reprodukcja-skanu-20261017/docs/AUDYT_T01_REPRODUKCJA_PODWOJNY_SKAN_2026-10-17.md).
- [Kod odtwarzalnego, celowo czerwonego testu Node](https://github.com/adriandziura0-rgb/sora/blob/sora-t01-reprodukcja-skanu-20261017/tools/test_t01_folder_scan.mjs).
- [GitHub Actions: startup_failure, zero wykonanych zadań](https://github.com/adriandziura0-rgb/sora/actions/runs/39030648844) — **nie interpretować jako wynik testu Node**.
- **Obecny wynik**: trzykrotnie wybrany fragment danych przechodzi `getFile` 6×, ale trafia dalej raz (3 dokumenty). Przyczyna: wrapper `import-recovery.js` i `originalFolder` wykonują pełne skany kolejno. Bez zmian bazy/CORE/kodu produkcyjnego.
- **Decyzja:** T01 nie powtarzać bez zmiany kodu lub potrzeby testu regresji. Przejść do T02; naprawę P0 podjąć osobno po bramkach testów i z kontrolą CLEAN.


## 7. Kontynuacja po T02 — 17.10.2026

**TASK_ID:** `SORA-T02-TOZSAMOSC-FOLDEROW` • **status po aktualizacji: pełne moduły Python z APK 1.2.17 PASS (4 scenariusze reprodukcji), decyzja kontraktu OTWARTA.** Kod bazowy bez zmiany: `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.

- [Raport T02: schemat, dawca→odbiorca, 4 próby SQLite i ryzyka](https://github.com/adriandziura0-rgb/sora/blob/sora-t02-deduplikacja-foldery-20261017/docs/AUDYT_T02_TOZSAMOSC_TRESCI_I_FOLDEROW_2026-10-17.md).
- [Test prawdziwych modułów SORA do uruchomienia (`--audit` / `--gate`)](https://github.com/adriandziura0-rgb/sora/blob/sora-t02-deduplikacja-foldery-20261017/tools/test_t02_duplicate_folders.py).
- W izolowanym SQLite wykonano pierwotnie model SQL: A→B identyczna treść: jeden dokument, duplikat B w zdarzeniu, wykaz folderów A=1/B=0; odwrotne B→A daje B=1/A=0; różne teksty A=1/B=1. **Następnie ten sam wniosek zweryfikowano wykonaniem oryginalnych modułów `DocumentDatabase`, `editorial_compare`, `database_overview` wydobytych z APK 1.2.17; źródła zgodne co do blob SHA.**
- **Brama T02:** odtwarzalny wynik pełnych modułów **JEST**; osobne wykonanie dokładnie `tools/test_t02_duplicate_folders.py --audit` jeszcze nie nastąpiło, lecz równoważne ścieżki kodu zostały przetestowane. Decyzja biznesowa przed zmianą schematu: unikalne teksty czy wystąpienia w folderach. Bezpieczny wariant do zatwierdzenia to **jedno obliczenie na treść + osobna ewidencja pochodzenia**, ale **NIE WDROŻONO**.
- T03 następnie również **wykonano na oryginalnym JavaScript**. Następna bezpieczna praca: osobna minimalna naprawa P0 skanowania, z testem przed/po. Nie zmieniać schematu ani danych.


## 8. Zamknięcie testów reprodukcyjnych T02 + T03 — 17.10.2026

### T02 rzeczywiste moduły Pythona

- **Wykonanie:** oryginalny APK 1.2.17 z udanego buildu, [run 38864600041](https://github.com/adriandziura0-rgb/sora/actions/runs/38864600041), artifact ID `12029879124`, wypakowanie `assets/drogowskazy-runtime.zip`.
- Git blob SHA `document_database.py` `2a8398f841417a34d4e489fcf7ae34fa5e04c525`, `editorial_compare.py` `814b2ac8bf923c972fd0ea603d51499bd65cbd84`, `database_overview.py` `e226e7cacf3d232e7df73a94cdd0d215d1ade4e9`. Wszystkie zgodne z badanym źródłem `67f48a45...`.
- Cztery syntetyczne próby na prawdziwych funkcjach zakończyły się potwierdzeniem obecnego zachowania: A→B identyczne = A:1/B:0; B→A identyczne = A:0/B:1; teksty różne = A:1/B:1; A→B→B = jeden dokument i trzy zdarzenia (dwa duplikaty). Wszystkie cztery `PRAGMA integrity_check=ok`, `foreign_key_check=0`.
- [Raport i szczegóły](https://github.com/adriandziura0-rgb/sora/blob/sora-t02-deduplikacja-foldery-20261017/docs/AUDYT_T02_TOZSAMOSC_TRESCI_I_FOLDEROW_2026-10-17.md). **Nie ma decyzji o zmianie kontraktu ani schematu.**

### T03 oryginalny JavaScript — A→B→A

- [Raport](https://github.com/adriandziura0-rgb/sora/blob/sora-t03-kolizja-cytatow-20261017/docs/AUDYT_T03_KOLIZJA_CYTATOW_A_B_A_2026-10-17.md).
- [Test regresyjny `--audit` i `--gate`](https://github.com/adriandziura0-rgb/sora/blob/sora-t03-kolizja-cytatow-20261017/tools/test_t03_quote_scope_race.mjs).
- Badany `shared-content.js` Git blob SHA `c2618cd0182755131271f13adfdf5c9d288324d2`.
- **Wynik:** przy A1→B→A2 stara odpowiedź A1 zaakceptowana i możliwa do eksportu; pozostając przy B jest prawidłowo odrzucana; stary błąd A1 jest wyświetlany po powrocie do A; drugie zapytanie A2 nie startuje podczas `quoteBusy`. `--audit` PASS reprodukcji, `--gate` oczekiwane FAIL przed poprawką.
- Kontrola dotyczy rzeczywistego JS w izolowanym V8, nie prawdziwej przeglądarki ani Flask/SQLite. **CORE/FROZEN/klasyfikator niezmienione.**

### JEDEN następny krok

**P0 — usunięcie podwójnego skanowania przy użyciu istniejącej funkcji, bez nowej warstwy i bez zmiany schematu/CORE.** Dopiero po testach T01 i regresjach wdrożenie, a osobno P1 cytaty i ADR T02. Zatrzymać wydanie, jeśli testy PC/Android nie zostaną potwierdzone.

**Stan wydania:** nadal **SORA 1.2.17**, żadna poprawka z T01–T03 nie została wdrożona do aplikacji. `main` nadal nie jest najnowszym kodem rozwojowym.
