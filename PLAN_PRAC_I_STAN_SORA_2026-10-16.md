# SORA — STAN PROJEKTU I PLAN PRAC (16.10.2026)

**Repozytorium:** https://github.com/adriandziura0-rgb/sora  
**Bieżąca, zweryfikowana wersja rozwojowa:** SORA **1.2.17**, Android `versionCode 20`, silnik 4.5.12.  
**Źródło aplikacji:** `sora-full-html-snapshot-1.2.17-20261016`, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.  
**Uwaga:** domyślna gałąź `main` ma nadal wersję **1.2.5**. Nie traktować jej jako najnowszego kodu. Nie scalać ani nie resetować bez planu migracji i testów.  
**To jest zapis planu w odrębnej gałęzi dokumentacyjnej:** nie modyfikuje APK, EXE, SQLite, WAL/SHM ani silnika.

## 1. Co wykonano i gdzie zapisano kod

| Zakres | Wersja i gałąź | Stan |
|---|---|---|
| CLEAN etap 1: SHA-256 przy aktualizacji APK, ochrona danych | 1.2.13; `sora-full-clean-stage1-20261014` | wdrożone, buildy zielone |
| CLEAN etap 2: usunięcie starego Tkinter/Qt, ochrona historycznej logiki raportu, .gitignore | 1.2.13; `sora-full-clean-stage2-20261015` | wdrożone, buildy zielone |
| CLEAN etap 3: jedno źródło `runtime_source/`, deterministyczna budowa ZIP bez skryptów łatkujących | 1.2.13; `sora-full-clean-stage3-20261015` | wdrożone, buildy zielone |
| CLEAN etap 4: wspólny eksport UI, diagnostyka Windows poza paczką instalacyjną | 1.2.14; `sora-full-clean-stage4-20261015` | wdrożone, buildy zielone |
| A1: anulowanie starych zapytań, spójność zakresu 2 folderów i tej samej sprawy, brak starego wyniku po błędzie | 1.2.15; `sora-full-analizy-a1-20261015` | wdrożone, osobny test regresji |
| A2: tożsamość zapisanego artykułu, JSON/Markdown/PDF bez niejawnego ponownego uruchamiania analizy | 1.2.16; `sora-full-analizy-a2-20261015` | wdrożone, osobny test regresji |
| Rozszerzenie A2: zapis niezależnego HTML snapshotu | **1.2.17**; `sora-full-html-snapshot-1.2.17-20261016` | **najnowsza potwierdzona wersja: APK i PC SUCCESS** |
| A3: 1 i 2 foldery; kompletność list i dowodów | następna osobna gałąź z 1.2.17 | DO ZROBIENIA |
| A4: jedna sprawa — pełne dokumenty/cytaty i kompletność raportu | po A3 | DO ZROBIENIA |
| A5: końcowe testy, paczki i próby na rzeczywistych bazach | po A3 i A4 | DO ZROBIENIA |

### Audyty i ścieżka dokumentacji
- Audyt CLEAN: https://github.com/adriandziura0-rgb/sora/blob/audit-sora-clean-20261014/AUDYT_CZYSTOSCI_SORA_1_2_12_2026-10-14.md
- Audyt 4 trybów analiz: https://github.com/adriandziura0-rgb/sora/blob/audit-sora-analizy-4-tryby-20261015/AUDYT_ANALIZY_1_ARTYKUL_1_FOLDER_2_FOLDERY_TA_SAMA_SPRAWA.md
- Dokument A1: https://github.com/adriandziura0-rgb/sora/blob/sora-full-analizy-a1-20261015/ANALIZY_A1_STABILNY_ZAKRES_1_2_15.md
- Dokument A2: https://github.com/adriandziura0-rgb/sora/blob/sora-full-analizy-a2-20261015/ANALIZY_A2_JEDEN_ZAPISANY_ARTYKUL_1_2_16.md

## 2. Potwierdzony punkt kontrolny 1.2.17

- Android build **SUCCESS**, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`: https://github.com/adriandziura0-rgb/sora/actions/runs/38864600041
- Windows WebView2 build **SUCCESS**, ten sam commit: https://github.com/adriandziura0-rgb/sora/actions/runs/38864600077
- Potwierdzone w logach: **257/257 GOLD**, zgodność kanonicznych 66 plików runtime, import/transfer PHONE ↔ PC, zgodność ochrony SQLite, na Androidzie **110 przycisków i 16 scenariuszy integracyjnych**.
- Oba buildy mają artefakty do pobrania: `Drogowskazy-Sora-APK`, `Sora-WINDOWS-NATIVE-WEBVIEW2`. W Windows paczka użytkowa zawiera `Sora/Sora.exe` z osobnym silnikiem; diagnostyka dostępna jako dodatkowy artefakt.
- Sukces CI NIE zastępuje prób długotrwałego działania na urządzeniu użytkownika i kontroli trafności w realnej bazie artykułów.
- Nie mieszać kodu 1.2.17 z APK 1.2.14 ani uruchamiać zmiany `main` bez potwierdzenia numeru wersji i SHA.

## 3. Etap A3 — analiza jednego i dwóch folderów

**Cel:** wybór dokładnie jednego folderu daje pełną, czytelną analizę tylko jego artykułów; wybór dwóch folderów daje porównanie prób A/B z dowodami, nie przypadkowe „porównanie tej samej sprawy”.

1. Zakres: nazwa folderu, ścieżka, tryb `folder` vs `publisher`, liczba wszystkich/w toku/błędnych/ukończonych artykułów liczona z danych właściwego zakresu. Statusów nie wolno zgadywać z liczby ukończonych analiz.
2. **Pełny indeks źródeł:** obecne „12 ostatnich” w raporcie ma być jasno opisane jako podgląd, a wszystkie artykuły dostępne w paginowanej liście ze statusem, datą i przejściem do zapisanej analizy. Bez ładowania całej bazy do pamięci UI.
3. Jednoznaczne metryki: P0–P5, TOP, aktorzy, relacje, cytaty, brak danych vs zero; przy każdym liczniku liczebność próby i odsyłacze do dokumentów, na których opiera się wartość.
4. Dwa foldery: neutralne delty A−B, wskaźniki na 1000 słów i na dokument, liczby bezwzględne, ostrzeżenia o próbach <5 i <20, nierównych próbach, różnych tematach/dacie.
5. Wyraźnie osobne widoki: „**Porównanie całych folderów**” oraz „**Wspólne sprawy**”. Nie wnioskować automatycznie o pominięciu wydarzenia ani intencji redakcji.
6. Eksport HTML/JSON musi zawierać wybór folderów, datę, metodykę, wersję, licznik całości i informację o ewentualnie niepełnym podglądzie. Zmiana zakresu w trakcie pobierania nie może przypisać poprzedniego raportu.
7. UI: Android karty i wygodne przewijanie, PC kompletne tabele; wszystkie napisy po polsku; bez ukrywania istniejących danych dla analityka.

**Testy A3:** 1 dokument, 1/2 puste foldery, 2 foldery o nierównych próbach, >12 artykułów, 100+ artykułów i podfoldery, zmiana wyboru w trakcie odpowiedzi, błąd 404/500, zapis i otwarcie HTML/JSON, praca w tle bez korupcji bazy. Podczas tych testów klasyfikator i schemat SQLite bez zmian.

## 4. Etap A4 — ta sama sprawa, różne redakcje

**Cel:** porównywanie tylko artykułów **powiązanych z wybranym wydarzeniem**, bez utraty źródeł i bez fałszywego poczucia pewności dopasowania.

1. Zachować obecne heurystyki podobieństwa, ale wyświetlić czytelnie: identyfikator klastra, liczbę redakcji, zakres dat, poziom podobieństwa i oznaczenie „**dopasowanie automatyczne — wymaga sprawdzenia**”.
2. Pokazać **X z Y dokumentów**, nie ucięte do 60 bez ostrzeżenia. Wszystkie źródła przez paginację lub eksport; źródło publikacji musi być oddzielone od źródła cytowanego.
3. Cytaty: obecne „maksymalnie 8” opisać jako podgląd; zapewnić rozwinięcie wszystkich dostępnych zapisanych kart wraz z ID relacji, fragmentem, mówcą, statusem review i łączem do właściwego artykułu.
4. Raport HTML/JSON ma deklarować, czy zawiera pełną ewidencję czy wyciąg. Eksport nie może bazować tylko na widocznym DOM, bo nieotwarte cytaty mogą zniknąć. Nie ma prawa dopisywać cytatów, których nie ma w SQLite.
5. Zabezpieczenia: zmiana tematu/redakcji w trakcie zapytania, 404/500, błąd parsowania i timeout — stary wynik pozostaje ukryty; bez możliwości pobrania starego raportu.
6. Testy false-positive/false-negative na prawdziwych artykułach, bez zmiany silnika bez osobnej zgody. Raportować liczbę trafnych/nietrafnych/skierowanych do weryfikacji, nie nazywać GOLD 257/257 miarą trafności rozpoznawania tych samych spraw.

**Testy A4:** >60 artykułów, >8 cytatów na artykuł, rozbieżne daty, podobny tytuł ale inne wydarzenie, wielokrotne publikacje, brak URL, zmiana zakresu i restart, eksport HTML/JSON i parytet źródeł.

## 5. Etap A5 — regresja, kontrola wydania i test użytkownika

1. Tylko jedna bazowa gałąź/commit dla Androida i Windows. Zakaz budowania „z dwóch różnych gałęzi”; zapis SHA silnika i źródeł w manifestach.
2. Testy: **257/257 GOLD**, integralność SQLite/WAL/SHM, bezpieczna aktualizacja APK, podpis klucza, zachowanie danych przy instalacji; 110 przycisków i **co najmniej 16** scenariuszy bazowych Androida.
3. Wymagana ciągłość: Android praca z wyłączonym ekranem, restart usługi, przerwa w dostępie do internetu i wznowienie kolejki; Windows natywny EXE i start po rozpakowaniu; watchdog lokalnego serwera; zero zapisu nieautoryzowanych danych.
4. TRANSFER Android↔Windows: manifest, wersja, duplikaty, łączenie analiz, ID, niepodmienianie nowszych danych starszymi, pełen rollback po błędzie; nie kopiować otwartej bazy SQLite.
5. Testy czterech widoków: artykuł, 1 folder, 2 foldery, ta sama sprawa; każda wartość możliwa do prześledzenia do tekstu, kompletność raportu oraz jednoznaczny wynik stanu braku dowodu.
6. Osobne artefakty: prawdziwy `.apk` i ZIP z `Sora/Sora.exe`, manifest wersji i kontrola archiwów. Diagnostykę Windows zachować poza paczką użytkową. Nie oznaczać etapu SUCCESS zanim obie platformy nie przejdą na tym samym commicie.
7. Ręczna próba na kopii realnej bazy: wylosowane artykuły/tematy, sprawdzenie dopasowania i oznaczanie błędów. **Nie zmieniać prywatnej bazy użytkownika podczas audytu.**

## 6. Zasady niepodlegające negocjacji przy pracach

- **CORE FROZEN:** bez zmian klasyfikatora, parserów, logiki semantycznej, schematu baz i identyfikatora transferu, chyba że osobny audyt wykaże konieczną poprawkę i user zaakceptuje zmianę.
- Zero kasowania projektów, baz, archiwów użytkownika, zapisanych analiz, GOLD i pozostałych danych.
- Nie podmieniać `live` SQLite podczas działania aplikacji; robić eksport/import z walidacją i kopią bezpieczeństwa.
- Stare pliki usunąć jedynie z gałęzi po wykazaniu, że są nieużywane i po testach; zachować historię Git.
- Nie nakładać kolejnych łatek na dawny ZIP — źródła kanoniczne w `runtime_source/`, deterministyczna przebudowa i manifest SHA-256.
- Wszystkie napisy UI po polsku, osobne podsumowania dla każdego poziomu analizy, neutralna prezentacja różnic.
- Żadne testy na syntetycznych danych nie oznaczają dowiedzionej skuteczności semantycznej na wszystkich prywatnych artykułach.
- Przed wydaniem wymagane kopia TRANSFER i instrukcja aktualizacji **bez odinstalowywania APK**.

## 7. Najbliższy konkretny krok

**NOWA BRAMKA AUDYT-0 (przed jakimkolwiek kodem A3 lub naprawami):** wykonać odczytowy audyt kolizji i czystości kodu oraz zbudować tabelę **DAWCA → ODBIORCA DANYCH** dla importu, kolejek, SQLite, API, cytatów, wyników, eksportu i TRANSFER. Każda para ma mieć typy, ID, zakres/revision, zachowanie przy zaniku danych, właściciela zapisu, test i status. Dopiero po pisemnym raporcie: minimalne naprawy P0 import/recovery, P1 cytaty i zakres, P2 porządki; po zaliczonych testach A3. Zasady są w [ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md](ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md).

**Po audycie, usunięciu krytycznych kolizji i regresjach — A3, część 1:** na nowej gałęzi opartej o `67f48a45a79c30e8e22e8a3cb6c2426685566b42` dodać pełny paginowany indeks dokumentów 1 folderu, odróżniać „12 ostatnich” od pełnej listy, pokazać zakres i dowody bez zmiany silnika. Dołączyć testy odczytowe oraz sprawdzić Android i Windows na tym samym SHA. Dopiero po zielonym A3 część 1 robić widok porównania dwóch folderów.

## 8. Co ten zapis obejmuje, a czego nie

To dokumentacja **stanu kodu, wykonanych etapów, wyników automatycznych buildów i planu** w repozytorium GitHub. Nie jest kopią prywatnej bazy SORA, artykułów użytkownika, istniejących na telefonie katalogów czy SQLite. Takie dane trzeba oddzielnie wyeksportować w aplikacji przez funkcję TRANSFER / kopię bazy.

**Plan może być aktualizowany po każdym przetestowanym etapie**, przy zachowaniu historii i linku do konkretnego SHA.


## 9. Nowe obowiązkowe zasady (16.10.2026) — audyt przed zmianą i kontrola dawca/odbiorca

**Dokument nadrzędny dla kolejnych prac:** [ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md](ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md). Uzupełnia wcześniejszy audyt kolizji i plan, nie zmienia silnika.

**Bramki etapowe:**

| Kolejność | Zadanie | Dowód zakończenia |
|---|---|---|
| 0A | Audyt obecnego kodu 1.2.17 (tylko odczyt), repo, zależności, OLD, duplikaty, martwy kod i nakładki | Lista plików/odwołań, wykryte fakty, hipotezy, brak zmian w kodzie |
| 0B | Mapa DAWCA → ODBIORCA dla wszystkich ścieżek objętych planowaną zmianą | Źródło, odbiorca, kontrakt typów/ID, znikające pola, rewizja i konflikt zapisu |
| 0C | Audyt kolizji/starych wyników/dwukrotnego wywołania i ryzyka regresji PHONE/PC | Test reprodukcji, raport wpływu, punkt powrotu i minimalny plan |
| 1 | Po zatwierdzeniu zakresu: poprawka P0 import/skan i później P1 cytaty/zakres | Osobny commit i testy K/D/C; zero zmian classifiera i schematu SQLite |
| 2 | Po P0/P1: CLEAN potwierdzonych dubli, nakładek, nieużywanych gałęzi | Audyt importów, równoważność zachowania i czystość obu paczek |
| 3 | A3: pełny 1 folder, potem porównanie 2 folderów | Źródła X/Y, paginacja, P0–P5, eksporty, testy danych |
| 4 | A4: ta sama sprawa i baza cytatów | Wszystkie źródła, zgodne ID/temat, brak starego wyniku, neutralne porównanie |
| 5 | A5: audyt końcowy i wydanie | APK i EXE z jednego SHA, GOLD, testy E2E, SQLite/TRANSFER, realne dane na kopii |

**Reguły stałe:** przed każdą zmianą audit-first; przed i po każdej poprawce kontrola producenta i konsumenta, kolizji i czystości kodu; bez dubli, monkey-patchy i cichego usuwania; nie usuwać baz/projektów/GOLD, nie nadpisywać działającej SQLite, CORE pozostaje zamrożony; napisy UI po polsku. Nie zgadywać danych ani nie uznawać zielonego builda za dowód trafności analizy.

**Obecny status:** wyłącznie zapis ustaleń i planu. Nie rozpoczęto wdrażania P0/P1/A3, nie wykonano nowego testu na prywatnej bazie.


## 10. Wynik wykonania etapu AUDYT-0 (16.10.2026)

**Audyt statyczny wykonany i zapisany:** [AUDYT_0_SORA_1_2_17_DAWCA_ODBIORCA_CZYSTOSC_2026-10-16.md](AUDYT_0_SORA_1_2_17_DAWCA_ODBIORCA_CZYSTOSC_2026-10-16.md). Zbadano 11 kluczowych łańcuchów dawca–odbiorca, 123 śledzone pliki Git bez identycznych SHA, 197 unikalnych statycznych ID HTML. Potwierdzono podwójne skanowanie folderu, lukę A→B→A przy cytatach oraz rozbieżność między unikalną treścią dokumentu i wieloma folderami (jeden `relative_path`). Zidentyfikowano limity podglądu 12 i 60.

**Nowa kolejność najbliższych prac:** przed poprawką wykonać T01 (licznik skanów), T02 (identyczny dokument z A i B oraz decyzja o tożsamości źródła), T03 (cytaty A→B→A) z raportem FAIL/PASS. Dopiero później naprawy P0/P1 i ich audyty końcowe; bez automatycznej migracji schematu SQLite/TRANSFER. Nie wykonano w tym etapie nowych testów E2E ani zmian kodu, baz, APK i EXE. `main` nie był aktualizowany.
