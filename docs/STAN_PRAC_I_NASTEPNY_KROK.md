# STAN PRAC I NASTĘPNY KROK — Drogowskazy SORA — analizy artykułów

**Utworzono:** 2026-10-17 • **TASK_ID:** `SORA-AUDYT0-001` • **Status:** `T01 FIX NA OSOBNEJ GAŁĘZI, TEST LOKALNY PASS / CI BLOCKED / BRAK WYDANIA`  
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

**Kolejny dokładny krok: zbadać `startup_failure` GitHub Actions i uzyskać rzeczywisty PASS testów P0 na gałęzi `sora-full-p0-single-scan-20261017` (Android/Windows na jednym SHA), a potem test ręczny WebView na urządzeniach i audyt końcowy. Nie wydawać APK/EXE z P0 przed tą bramką. Nie mieszać osobnej naprawy P1 cytatów ani migracji T02.**

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

**P0: kod na osobnej gałęzi już zmieniono i lokalna regresja skanowania jest zielona; pozostało odblokowanie CI, pełne E2E Android/Windows i audyt końcowy.** P1 cytatów i ADR T02 pozostają oddzielnymi zadaniami.

**Stan wydania:** nadal oryginalne **SORA 1.2.17**; P0 istnieje **wyłącznie na nieopublikowanej gałęzi**, nie ma nowego APK/EXE ani zatwierdzonej regresji w CI. `main` nadal nie jest źródłem najnowszego kodu rozwojowego.


## 9. Wynik naprawy P0 — 17.10.2026 (najnowszy punkt wznowienia)

**TASK_ID:** `SORA-P0-JEDEN-SKAN`  
**Stan:** `KOD WDROŻONY NA BRANCHU / TEST LOKALNY PASS / CI STARTUP_FAILURE / WYDANIE NO-GO`.  
**Gałąź:** `sora-full-p0-single-scan-20261017`  
**HEAD gałęzi P0:** `aa6c208c03f88ff1d92856d1a6884bf56a7ad61b`  
**Bazowy działający punkt odniesienia (bez zmiany):** `67f48a45a79c30e8e22e8a3cb6c2426685566b42` (SORA 1.2.17).

- [Pełny raport P0, porównanie przed/po i audyt CLEAN](https://github.com/adriandziura0-rgb/sora/blob/sora-full-p0-single-scan-20261017/docs/RAPORT_P0_JEDEN_SKAN_FOLDERU_2026-10-17.md).
- [Kod P0 — gałąź testowa](https://github.com/adriandziura0-rgb/sora/tree/sora-full-p0-single-scan-20261017).
- [T01 — bramka regresyjna](https://github.com/adriandziura0-rgb/sora/blob/sora-full-p0-single-scan-20261017/tools/test_t01_folder_scan.mjs).
- [Ostatnia próba CI startup_failure — bez uruchomionych jobs](https://github.com/adriandziura0-rgb/sora/actions/runs/39036260543).
- **P0 DAWCA → ODBIORCA:** picker → zbieranie `entries` **1×** → obecny handler `dodajFolderZHandle(handle,entries)` → walidacja/analiza; bez ponownego skanu. Brak zmian parsera, klasyfikatora, schematu i danych SQLite.
- **Przed:** 3 pliki → 6 wywołań `getFile` i jeden pakiet. **Po:** 3 pliki → **3** wywołania i jeden pakiet. 7 lokalnych scenariuszy z syntetycznym DOM i FileSystem handles: PASS, w tym podfolder, za duży folder, zamknięcie, pliki nieobsługiwane, pusty zbiór, podwójne kliknięcie i anulowanie. Składnia obu JS PASS. Nie jest to test prawdziwego WebView/Android.
- **CLEAN i deterministyczny build:** 2 pliki JavaScript z małym diffem, 1 test i +1 linia w dwóch workflow. Uzupełniono też obowiązkowe sumy SHA w kanonicznym `runtime_source/zip_manifest.json` i stałą `RUNTIME_SHA` w `tools/build_runtime_from_sources.py` — bez zmiany `ENGINE_SHA` zamrożonego silnika, 64 niezmienione pliki runtime. Odtworzone pakowanie ZIP lokalnie bitowo zgodne z algorytmem i manifestem. Brak nowej warstwy patchy/OLD i brak ingerencji w bazę.
- **BLOKADA:** automatyczne GitHub Actions dla brancha P0 kończą się `startup_failure` **przed testami** (0 jobs). Nie deklarować pełnego PASS ani publikacji.
- **NASTĘPNY JEDEN KROK:** zdiagnozować przyczynę startup_failure i uruchomić realne GitHub CI na SHA P0. Jeżeli trzeba zmienić workflow, najpierw audyt przyczyny, nie próby losowych poprawek. Następnie rzeczywiste testy PHONE/PC i decyzja o wydaniu.
- **POZOSTAŁE, OSOBNE:** P1 cytaty A→B→A (czerwony test istnieje); T02 duplikaty folderów (pełne moduły z APK przebadane, decyzja co do definicji liczenia wystąpień nadal otwarta); A3 wstrzymany do potrzebnych bramek.

**Punkt rollback:** commit bazowego kodu `67f48a45...`; danych SQLite nie cofano i nie należy ich kopiować/podmieniać „na żywo”. Nie zmieniać `main` bez testów.


### Bramka pakowania P0 (zapis uzupełniający)

Wykryto, że kanoniczny builder SORA przerywa pracę po zmianie JS bez aktualizacji manifestu. Na gałęzi P0:
- zaktualizowano **wyłącznie** SHA `static/app.js`, `static/import-recovery.js` i całego ZIP w `runtime_source/zip_manifest.json`;
- stała `RUNTIME_SHA` = `daa8ed53b0d77e4af449539b0f3f0fd4b09c306d34d3cf2c0da58f0b113c85df` odpowiada odtworzonemu bajtowo lokalnemu ZIP P0;
- `ENGINE_SHA` = `acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e` bez zmian; wszystkie 64 inne pliki runtime identyczne z bazą;
- zapisana w GitHub [dodatkowa kontrola deterministycznego pakowania P0](https://github.com/adriandziura0-rgb/sora/blob/sora-full-p0-single-scan-20261017/docs/RAPORT_P0_JEDEN_SKAN_FOLDERU_2026-10-17.md#7-obowiązkowy-audyt-pakowania-deterministycznego--po-modyfikacji-ui).

**Następny jeden krok pozostaje bez zmian:** zweryfikować/odblokować `startup_failure` w GitHub Actions; przetestować prawdziwy kanoniczny builder, regresje + build Android i PC na jednym SHA. To jest **test lokalnej rekonstrukcji**, nie zielone GitHub Actions.
