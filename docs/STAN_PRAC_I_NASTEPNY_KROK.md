# STAN PRAC I NASTĘPNY KROK — Drogowskazy SORA — analizy artykułów

**Utworzono:** 2026-10-17 • **TASK_ID:** `SORA-AUDYT0-001` • **Status:** `T01 ODTWORZONY / T02 SQL WYKONANY, KOD NOT_RUN / P0 NIEWDROŻONE`  
**Repozytorium:** https://github.com/adriandziura0-rgb/sora  
**HEAD kodu sprawdzany PRZED dodaniem dokumentacji:** `main` @ `28f5b698105e522c7d2658776a2382f46bc1e7b9`. Ten SHA jest **punktem odczytu**, nie dowodem najnowszego działającego produktu.  
**Standard uniwersalny:** [UNIWERSALNY STANDARD v1.0](https://github.com/adriandziura0-rgb/przewijarka-app/blob/main/docs/UNIWERSALNY_STANDARD_PRACY_I_KONTYNUACJI_v1_0.md). Dodatkowo obowiązuje lokalny `AGENTS.md`; MASTER LIVE tylko w odpowiedniej domenie.

## 1. Co sprawdzono i co wiadomo

`main` w repozytorium nie jest aktywną gałęzią rozwojową. Ostatni zweryfikowany kod produktu wskazany w planie to **1.2.17** na gałęzi `sora-full-html-snapshot-1.2.17-20261016`, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`. Odrębna gałąź dokumentacyjna: `sora-plan-prac-20261016`.

**Dowody i dokumentacja:** [Audyt-0 — DAWCA/ODBIORCA/CLEAN](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/AUDYT_0_SORA_1_2_17_DAWCA_ODBIORCA_CZYSTOSC_2026-10-16.md), [plan A1–A5](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/PLAN_PRAC_I_STAN_SORA_2026-10-16.md), [lokalne zasady](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md).

## 2. Stan zadania

- **Zakończone/dowiedzione:** Audyt statyczny 11 ścieżek zapisany; T01 na rzeczywistych fragmentach JS w izolowanym V8 wykazał 3 pliki odczytane 6 razy, przekazanie jednego pakietu 3 dokumentów i brak automatycznego zapisu SQLite. Zielone poprzednie CI Android/Windows 1.2.17 pozostaje punktem odniesienia, **nie obejmuje naprawy T01**.
- **Otwarte / BLOKADA:** T01: podwójny skan 3→6; T02: po analizie kodu i uruchomieniu projekcji SQL drugi folder nie staje się odrębnym przypisaniem w `documents`/raporcie (decyzja biznesowa i uruchomienie testu prawdziwych modułów nadal wymagane); T03: cykl cytatów A→B→A do odtworzenia; ponadto limity list 12/60.
- **Testy wykonane:** **T01 — FAIL (3→6)**. **T02 — 4/4 izolowane projekcje SQL PASS**, w tym A→B ta sama treść daje `documents=1`, `import_events=2` i grupy A=1/B=0, kolejność B→A odwraca przypisanie. **Test prawdziwych modułów T02 NOT_RUN**: test zapisany na osobnej gałęzi. T03 NOT_RUN; GitHub CI niedawno `startup_failure`. Brak napraw, zmian CORE/SQLite i nowych wydań.
- **DAWCA → ODBIORCA:** do potwierdzenia na rzeczywistym torze podanym w kroku poniżej; nie udawać, że wszystkie ogniwa już sprawdzono.
- **Kolizje i CLEAN:** istniejące hipotezy/raporty trzeba prześledzić do SHA i testu; żadnego kasowania `OLD` ani automatycznej przebudowy.
- **CORE, baza, historia, program:** **nietknięte**. Nie nadpisano SQLite, schematu, par wyników ani skryptów produktu.

## 3. Jeden następny krok — zaczynać TUTAJ

**Kolejny dokładny krok: uruchomić `python tools/test_t02_duplicate_folders.py --audit` na prawdziwym checkout SORA 1.2.17 (najlepiej GitHub CI po usunięciu `startup_failure`) i potwierdzić logi. Nie zmieniać bazy. Dopiero następnie wykonać T03 cytaty A→B→A. T01 i projekcji SQL T02 nie ponawiać bez nowego kodu/dowodu.**

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

**TASK_ID:** `SORA-T02-TOZSAMOSC-FOLDEROW` • **status: SQL-model PASS, pełny test modułów NOT_RUN, decyzja kontraktu OTWARTA.** Kod bazowy bez zmiany: `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.

- [Raport T02: schemat, dawca→odbiorca, 4 próby SQLite i ryzyka](https://github.com/adriandziura0-rgb/sora/blob/sora-t02-deduplikacja-foldery-20261017/docs/AUDYT_T02_TOZSAMOSC_TRESCI_I_FOLDEROW_2026-10-17.md).
- [Test prawdziwych modułów SORA do uruchomienia (`--audit` / `--gate`)](https://github.com/adriandziura0-rgb/sora/blob/sora-t02-deduplikacja-foldery-20261017/tools/test_t02_duplicate_folders.py).
- W izolowanym SQLite wykonano: A→B identyczna treść: jeden dokument, duplikat B w zdarzeniu, wykaz folderów A=1/B=0; odwrotne B→A daje B=1/A=0; różne teksty A=1/B=1; ponowiony B zwiększa tylko liczbę zdarzeń duplikatu. **Wykonana próba to projekcja SQL, nie realny moduł.**
- **Brama następna:** wykonać `python tools/test_t02_duplicate_folders.py --audit` z rzeczywistego checkoutu 1.2.17 i potwierdzić status. Przed zmianą schematu wybrać kontrakt: unikalne teksty czy wystąpienia w folderach. Sugerowany bezpieczny kierunek to **jedno obliczenie na treść + osobna ewidencja pochodzenia**, ale **NIE WDROŻONO** go.
- Po potwierdzeniu T02 przejść do T03 (cytaty A→B→A); naprawy P0/P1 pod kontrolą oddzielnego planu. Nie nadpisywać schematu ani danych.
