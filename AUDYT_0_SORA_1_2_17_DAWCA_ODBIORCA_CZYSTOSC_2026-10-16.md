# SORA 1.2.17 — AUDYT-0: przepływ DAWCA → ODBIORCA, kolizje i czystość kodu

**Data:** 16.10.2026  
**Repo:** https://github.com/adriandziura0-rgb/sora  
**Badana gałąź:** `sora-full-html-snapshot-1.2.17-20261016`  
**Badany commit (zamrożony punkt odniesienia):** `67f48a45a79c30e8e22e8a3cb6c2426685566b42`  
**Gałąź zapisu raportu:** `sora-plan-prac-20261016` — tylko dokumentacja.  
**Zakres:** wybrane krytyczne przepływy runtime Python, WebView JS, SQLite, importer, analizator zaznaczonych materiałów, cytaty, foldery, transfer PHONE↔PC i pakowanie. **Nie jest to wykonanie napraw, pełna formalna weryfikacja każdej linii repozytorium ani audyt prywatnych danych.**

## 0. Decyzja etapu

**AUDYT-0 wykonany w zakresie inspekcji statycznej; bramka do zmian P0/P1 warunkowa, NIE automatycznie zaliczona.** Wskazano potwierdzone defekty/rozbieżności kontraktu, ryzyka i nieprzetestowane ścieżki. **NIE wykonano zmian kodu, migracji, resetu SQLite, ponownego testu E2E ani instalacji na urządzeniu.** Następne wdrożenie wymaga osobnych testów odtwarzających i decyzji o kontrakcie folderów/duplikatów.

### Punkt odniesienia / wiarygodność danych

- Git tree SHA / commit: `67f48a45a79c30e8e22e8a3cb6c2426685566b42`; **123 śledzone bloby/pliki** w całym drzewie; **brak par identycznych SHA** w tym konkretnym drzewie (nie oznacza braku duplikacji logicznej). W katalogu `runtime_source/` 67 plików, w tym manifest.
- Statyczny HTML `runtime_source/templates/index.html`: **197 identyfikatorów `id`, 197 różnych**, brak statycznych duplikatów. Dynamiczne wstrzykiwanie ID wymaga osobnego testu UI.
- `app.js`: ok. 4468 linii, 90 wystąpień `addEventListener(`; `full-database.js`: 5 wystąpień `new MutationObserver`; `same-story-mobile.js`: 1. Są to **liczby miejsc rejestracji**, nie dowód wielokrotnego podłączenia ani wyścigu.
- Obecne, wcześniejsze wyniki GitHub CI z tego samego SHA: [Android SUCCESS #38864600041](https://github.com/adriandziura0-rgb/sora/actions/runs/38864600041), [Windows SUCCESS #38864600077](https://github.com/adriandziura0-rgb/sora/actions/runs/38864600077). W poprzednich logach 257/257 GOLD, 110 statycznych przycisków i 16 scenariuszy Android. **W AUDYT-0 nie uruchomiono ich ponownie**; PASS CI ≠ PASS manualnego użycia i poprawności merytorycznej.
- Nie ma w badanym drzewie śledzonej prywatnej bazy użytkownika. Nie oceniano rzeczywistej zawartości urządzenia. Stwierdzenie „brak danych w Git” nie dowodzi, co leży w instalacji.

## 1. Obowiązkowa mapa przepływu: DAWCA → ODBIORCA

| ID | Dawca → odbiorca | Kontrakt / sprawdzony warunek | Status i ryzyko |
|---|---|---|---|
| F01 | Picker Android SAF / Windows → `static/app.js:zbierzPlikiZKataloguHandle` i `dodajFolderZHandle` → analiza bieżąca | Nazwa, ścieżka, plik, limit, anulowanie; jeden świadomy przebieg skanowania | **KOLIZJA potwierdzona**: `import-recovery.js` skanuje i ponownie deleguje do `originalFolder`, który skanuje jeszcze raz |
| F02 | Picker plików / katalogów → `static/app.js:importujPlikiDoBazy` → `POST /api/baza/importuj` → `DocumentDatabase.begin_import` | Każdy plik ma `relative_path`, typ/rozmiar, odpowiedź `duplicate/queued/processing`; baza w transakcji | **RYZYKO semantyczne**: globalna deduplikacja po treści może zachować tylko jedną lokalizację pliku |
| F03 | `begin_import` → trwałe `documents(status=processing)` → `app.py:_enqueue_import_job/_background_import_worker` → `mark_success/mark_error` | `document_id` + hash, tylko aktualne `processing`; wznowienie po restarcie, bez requeue `done` | **Zabezpieczenia widoczne**; testować restart, równoczesne importy i zmianę reprezentacji |
| F04 | `documents`/wynik `analysis_gzip` → `GET /api/baza/dokument/<id>/wynik` → karta i eksport A2 | ID dokumentu, SHA, `updated_at`, `analysis_run_id`; nie wywoływać cichego `POST /api/raport` | **Istnieją mechanizmy A2**; testować zmianę run między odczytem i eksportem |
| F05 | `iter_completed_results` → `cached_selected_overview` → `/api/baza/analiza_wybranych` → `full-database.js` → JSON/HTML | Jawne 1–10 `group`, `mode`, read-only; wyświetla tylko ukończone; `recent_documents` max 12 | **Ograniczenie kompletności**: „ostatnie 12” nie jest pełną listą; oddzielić podgląd od indeksu |
| F06 | `documents.relative_path` / `editorial_compare.comparison_group` → `/api/baza/porownanie` → tabela PC / karty PHONE | `folder` pochodzi z pierwszego segmentu pojedynczego `relative_path` | **KONFLIKT KONTRAKTU DANYCH**: jeden hash dokumentu nie reprezentuje automatycznie dwóch folderów |
| F07 | `quote_database.selected_quote_database` → `/api/baza/cytaty_wybranych` → `shared-content.js` → cytaty/JSON | `mode+groups`, bieżąca generacja żądania, brak mieszania A/B | **KOLIZJA czasowa / luka**: `fetch` bez AbortController oraz kontroli niezmiennego `request_id`; A→B→A może zaakceptować stare A |
| F08 | `topic_report_cache`/`editorial_compare` → `/api/baza/temat/porownanie` → `app.js`/ `same-story-mobile.js` | `topic_id` i pełny zakres redakcji, odrzuć stare odpowiedzi | **Osłony A1 istnieją**; **kompletność UI ograniczona**: `selectedDocuments` w mobile `.slice(0,60)` |
| F09 | `shared_content.py` → `/api/baza/wspolna_tresc` → `shared-content.js` | Ręczne porównanie zapisanych wyników, w JS jest `AbortController` i `activeKey` | **Zabezpieczenie częściowe**, inne niż w F07; test A→B→A / błąd / restart |
| F10 | Lokalna SQLite PHONE / PC → `data_transfer.export_zip` (snapshot i manifest) → `merge_zip` → docelowa SQLite | Hash, schema 3, zgodny silnik, mapping ID, `BEGIN IMMEDIATE`, kopia przed, rollback; nowszy `updated_at` ma pierwszeństwo | **Mechanizmy obecne**; wymagane testy konfliktu, spóźnionego źródła, restartu i dwóch jednoczesnych urządzeń |
| F11 | `runtime_source/**` + `zip_manifest.json` → `tools/build_runtime_from_sources.py` → asset APK / runtime Windows → `ProjectStore` | Wspólny fingerprint programu, kontrola aktualizacji, nie nadpisywać prywatnego `data`, WAL/SHM | **Mechanizmy widoczne**; ponownie zweryfikować zgodność artefaktów po KAŻDEJ poprawce |

**Policzony zakres:** 11 łańcuchów/obszarów dawców i odbiorców zidentyfikowanych i przejrzanych statycznie; **3 potwierdzone niezgodności** (F01 podwójny skan, F06 utrata wieloprzypisania folderów, F07 luka odpowiedzi cytatów); pozostałe **8 wymagają testów dynamicznych i/lub dalszej weryfikacji zależności**. Nie oznacza to, że istnieje dokładnie 11 par w całej aplikacji. Nie deklarować „0 pozostałych kolizji”.

## 2. POTWIERDZONE ustalenia — konkretne dowody i skutek

### P0-A / import: drugi skan tego samego katalogu

- [`runtime_source/static/import-recovery.js` linie 17–19, 48–91](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/static/import-recovery.js#L17-L91) przechwytuje referencje i **nadpisuje** funkcje globalne, w tym `dodajFolderZHandle` i `zbierzPlikiZKataloguHandle`.
- Na ścieżce folderu pod limitem: wrapper wywołuje `zbierzPlikiZKataloguHandle(handle,...)` w linii 67, a potem `originalFolder(handle)` w linii 75.
- [`runtime_source/static/app.js` linie 2672–2720](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/static/app.js#L2672-L2720): główne `dodajFolderZHandle` ponownie uruchamia `zbierzPlikiZKataloguHandle`. **Dwa skany są logicznie pewne dla tej gałęzi**, natomiast rzeczywiste opóźnienie należy zmierzyć.
- Dodatkowe ryzyko: `originalFolder` używa ponownie systemu postępu i anuluje według innego tokenu. Nie wprowadzać siódmego wrappera.
- Test przed zmianą: folder 3 pliki + podfolder, licznik `getFile`/entries i odbiorca JSON, potem 100+; osobno folder >1,8 MB, anulowanie, Escape i import do SQLite.

### P0-B / rozbieżność tożsamości dokumentu i przypisania źródłowego

- [`document_database.py` linie 160–177](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/document_database.py#L160-L177): `documents.content_sha256 UNIQUE`, jedna `relative_path` w rekordzie.
- [`document_database.py` linie 280–299](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/document_database.py#L280-L299): przy tym samym SHA i statusie `done/processing` zapis zdarzenia `import_events(outcome='duplicate')`, **brak osobnego przypisania artykułu do drugiego folderu w `documents`**.
- [`editorial_compare.py` linie 157–179](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/editorial_compare.py#L157-L179): grupa `folder` wynika z pojedynczego `relative_path`. [`database_overview.py` linie 45–61](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/database_overview.py#L45-L61) grupuje właśnie te zakończone dokumenty.
- **Konsekwencja z analizy kodu:** publikacja w A, identyczny tekst w B → jeden dokument przypisany do jednej ścieżki; druga obecność jest w zdarzeniu importu, nie w zbiorze używanym do porównania folderów. Wyniki obu folderów mogą nie odzwierciedlać rzeczywistych wystąpień artykułu. Nie jest to dowód fizycznego uszkodzenia SQLite, lecz **ważne ograniczenie modelu i metryki źródeł**.
- **STOP przed naprawą:** ustalić, czy raport ma liczyć *unikalne treści* czy *wystąpienia publikacji w folderach*. Nie zmieniać `UNIQUE` ani schematu bazy podczas CLEAN bez oddzielnego projektu migracji i jawnej akceptacji. Najpierw reprodukcja na kopii: A/ten_sam.txt + B/ten_sam.txt, kontrola `documents`, `import_events`, `list_document_folders`, raport A/B.

### P1 / cytaty: wyścig A→B→A

- [`shared-content.js` linie 52–100](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/static/shared-content.js#L52-L100): zapytanie `/api/baza/cytaty_wybranych` bez `signal`; po odpowiedzi sprawdzany tylko `scope().key === chosen.key`.
- [`shared-content.js` linie 163–174](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/static/shared-content.js#L163-L174): zmiana zakresu usuwa cytaty tylko, gdy `quoteScope` jest już ustawione i różne od bieżącego; podczas aktywnego pobrania `quoteScope=null`.
- **Scenariusz kolizji:** A zaczyna pobranie; wybór B, potem A; stare pobranie A wraca, klucz ponownie się zgadza. Nie ma monotonicznej rewizji, więc **akceptacja przestarzałych danych jest możliwa**.
- Nie pomylić z `/api/baza/wspolna_tresc`: ta ścieżka ma już własny `AbortController`. Nie tworzyć drugiego globalnego mechanizmu bez integracji z A1.
- Test negatywny: kontrolowany deferred promise dla A1→B→A2, A1 nie może zmienić DOM ani eksportu A2, również po błędzie 500.

### P1 / kompletność raportów i reprezentacja dawcy

- [`database_overview.py` linie 60–88, 162–169](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/database_overview.py#L60-L169): `recent_heap` przechowuje maksymalnie **12** artykułów; nie jest indeksem pełnego folderu. Kod słusznie ogranicza się do ukończonych analiz, ale liczba `done` nie oznacza liczby wszystkich plików.
- [`same-story-mobile.js` linie 65–78](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/static/same-story-mobile.js#L65-L78): `selectedDocuments` ucina źródła przez `.slice(0,60)`; nie wolno prezentować tej liczby jako pełnej ewidencji. Oddzielić licznik całości od podglądu.
- [`full-database.js` linie 121–164](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/static/full-database.js#L121-L164) generuje HTML z aktualnego DOM, ale rozwija 8 metryk i zamienia nieaktywne przyciski dokumentów w tekst. Poprawka 1.2.17 usuwa martwe przyciski; **nie dowodzi kompletności wszystkich dokumentów i cytatów**, bo ograniczenia są wyżej w danych.
- **Naprawa dopiero w A3/A4:** paginowany pełny indeks, `X z Y`, pochodzenie i status, eksport pełnej ewidencji z API (nie tylko fragment DOM), bez niejawnej ponownej analizy.

## 3. Czystość kodu — wynik kontroli

| Obszar | Ustalenie | Decyzja |
|---|---|---|
| Duplikaty plików bajt-w-bajt | **0 identycznych SHA** w 123 blobach badanego drzewa | PASS tylko dla tego testu; to NIE jest audyt równoważności funkcji |
| Statyczne ID HTML | **197/197 unikalnych** | PASS statycznie, sprawdzić tworzone dynamicznie |
| Monkey-patche funkcji importu | `import-recovery.js` redefiniuje 6 globalnych punktów wejścia/obsługi (część jako wrappery) | DŁUG POTWIERDZONY, priorytet P0 |
| Pętle, listenery, obserwatory | 90 miejsc `addEventListener(` w dużym `app.js`, 5 obserwatorów w `full-database.js` i 1 w `same-story-mobile.js` | RYZYKO, nie rozpoznano zapętlenia; wymaga E2E podwójnego montażu UI |
| Oddzielne widoki tej samej informacji | Desktopowa tabela i mobilne karty, osobne helpery formatowania/escaping | Uzasadnione prezentacją, ale **jeden model danych i rewizji** musi być wspólny |
| Pomocnicze powtórzenia UI | Są podwójne wpisy w liście sekcji czyszczonych przez `app.js`; podobne helpery w wielu modułach | P2; minimalny refaktor dopiero po testach |
| CORE / duplikacja nazw | W sprawdzonych `document_database.py` i `editorial_compare.py` brak powtórzonych nazw deklaracji funkcji; podobne `_clean`/`_tokens` między modułami mogą mieć inny sens | Nie scalać „na nazwę”, CORE FROZEN |
| OLD, generowane ZIP-y i hosty | Bieżąca gałąź nie śledzi starego `tools/patch_engine_runtime.py`, gotowego `drogowskazy-runtime.zip` ani dawnych hostów Tkinter/Qt | Nie przywracać; archiwalne gałęzie zachować, bez automatycznego kasowania |
| Czystość końcowego ZIP/APK | Git tree nie potwierdza zawartości każdej instalacji; wcześniejsze CI opublikowało osobno diagnostykę Windows | Przed wydaniem sprawdzić rzeczywisty pakiet i manifest |
| CSS | Kilka arkuszy, bez przeprowadzonego tu pomiaru kaskady i screenshotów | NIEZWERYFIKOWANE; test wizualny Android/PC |

**Uwaga:** nie wykonano pełnego grafu importów ani testu `ruff/eslint` dla wszystkich plików i nie da się na tej podstawie stwierdzić, że cała baza kodu nie ma już żadnych martwych ścieżek.

## 4. Co należy zachować (nie psuć)

1. `document_database.py`: `BEGIN IMMEDIATE`, `foreign_keys=ON`, `busy_timeout`, WAL, kontrola `document_id + expected_content_sha256` i idempotentny wynik `duplicate`.
2. `app.py`: `_IMPORT_JOB_KEYS` i wznowienie tylko `processing`, nie `done`.
3. A1: `AbortController`, sprawdzanie zakresu i `topic_id`, niewyświetlanie starego wyniku.
4. A2: `document_id`/`content_sha256`/`analysis_run_id` i odczyt GET bez przeliczania przy eksporcie zapisanego artykułu.
5. `topic_report_cache.py`: generation na podstawie `id, content_sha256, updated_at, LENGTH(analysis_gzip)`; cache read-only. **Uwaga:** dodanie samego zdarzenia duplikatu nie zmienia generacji, więc nie zastąpi modelu wieloprzypisania folderów.
6. `data_transfer.py`: snapshot SQLite, manifest i hash, kontrola wersji i schematu, remap ID, blokada i rollback.
7. Instalacje telefonu i PC: jedna kanoniczna wersja runtime, zgodny `engine_sha256`, bez kasowania prywatnego `data`, WAL/SHM.
8. Przypadki GOLD i testy historyczne zachować; wszystkie napisy UI po polsku.

## 5. Testy bazowe przed jakąkolwiek zmianą kodu — lista BLOCKERÓW

| Test | Reprodukcja / oczekiwane zachowanie | Status AUDYT-0 |
|---|---|---|
| T00 | Zamrożony SHA aplikacji i pełna lista artefaktów | DOWÓD GIT, bez nowego CI |
| T01 import | 3 pliki w folderze i podfolder: licznik wejść do skanera, ślad wywołań do analizy | NIE URUCHOMIONO; kod wskazuje drugi skan |
| T02 wieloźródłowość | A/tekst.txt i B/tekst.txt o identycznej treści: przejrzeć oba foldery, events, API i wyniki | NIE URUCHOMIONO; konflikt kontraktu udokumentowany |
| T03 cytaty | Deferred A→B→A, błąd 500, anulowanie, brak starego JSON | NIE URUCHOMIONO |
| T04 metryki | 1 artykuł, 1 folder, 2 foldery, ta sama sprawa; porównanie UI, JSON, HTML z zapisanymi źródłami | NIE URUCHOMIONO |
| T05 kompletność | 13+ źródeł w folderze i 61+ w sprawie: X/Y, paginacja, status, odnośniki i eksport | NIE URUCHOMIONO |
| T06 praca w tle | import/restart/offline/ponowienie, nie przeliczać `done`, nie zostawić zombie `processing` | NIE URUCHOMIONO |
| T07 transfer | PHONE↔PC, konflikt ID, równy `updated_at`, starszy nad nowszym, zły hash, przerwa w trakcie | NIE URUCHOMIONO TERAZ; istnieją testy i historyczne PASS CI |
| T08 CLEAN | Podwójne otwarcie panelu, niepodwójne listenery, czysty runtime, UI i CSS | NIE URUCHOMIONO |
| T09 regresja | `GOLD 257/257`, A1/A2, APK/WebView/SAF, EXE/WebView2 z tego samego SHA | NIE URUCHOMIONO TERAZ; referencja CI 1.2.17 zielona |
| T10 realne materiały | Próbka wybranych rzeczywistych tekstów na **KOPII** bazy, walidacja źródeł i błędnych dopasowań | NIE URUCHOMIONO |

## 6. Plan dopuszczający do następnego etapu

**Bramka 0 (teraz):** raport audytu zapisany, utrwalić jako referencję. Przed naprawami uruchomić **T01, T02 i T03 jako testy odtwarzające błąd**. W T02 najpierw uzgodnić definicję „artykuł w folderze”: unikalna treść czy osobne wystąpienie publikacji.

**Bramka 1 / P0 import (osobna gałąź):** po T01 usunąć podwójny skan i globalny wrapper *zastępując*, a nie dokładując łatkę; jeden właściciel funkcji. PASS T01 + T06 + K05/K06 + brak uszczerbku A1/A2.

**Bramka 2 / model wielu źródeł (bez automatycznej migracji):** po T02 przedstawić wariant bezpiecznego rozdzielenia tożsamości treści i przypisań folderów, z analizą ryzyka SQLite/TRANSFER/retrokompatybilności. **Bez jawnej decyzji użytkownika pozostawić CORE i schemat bez zmian**.

**Bramka 3 / P1 cytaty:** naprawić unieważnianie przez monotoniczne `request_id`/rewizję i `AbortController`, bez globalnej drugiej implementacji; T03, K02–K04. Później jeden właściciel stanu renderowania oraz parytet telefon/PC.

**Bramka 4 / CLEAN:** jedynie udowodnione martwe pliki i duplikacje pomocnicze; graf wywołań przed/po, bez kasowania GOLD, baz, projektów, archiwów i historycznych branchy. Czystość badać ponownie PO każdej zmianie.

**Bramka 5 / A3–A5:** paginacja i pełne źródła 1/2 folderów, jedna sprawa + cytaty, wspólny model UI/JSON/HTML; dopiero na końcu nowa wersja APK/EXE na tym samym SHA, aktywne testy i punkt rollback.

## 7. Co ten raport potwierdza, a czego nie

**Potwierdza statycznie:** repo/wersję, przebieg 11 kluczowych ścieżek, duplikacje dwóch skanów, niedopasowanie „jeden dokument = jeden folder” wobec wspólnego tekstu i brak bezpiecznego rozróżnienia A→B→A dla cytatów; dodatkowo limity podglądu 12/60, brak identycznych SHA śledzonych plików i 197 unikalnych statycznych ID.  
**Nie potwierdza:** rzeczywistego czasu importu, nowego PASS/FAIL testów, stanu Androida podczas blokady ekranu, trafności dopasowań, prawidłowości wszystkich plików ZIP, pełnej inwentaryzacji martwego kodu ani fizycznego stanu prywatnej bazy.  
**Działanie na GitHubie:** wyłącznie plik raportu i aktualizacja planu, bez dotykania gałęzi aplikacji.

## 8. Powiązane dokumenty

- [ZASADY PRACY: AUDYT, DAWCA → ODBIORCA, CZYSTOŚĆ](ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md)
- [PLAN PRAC I STAN SORA 16.10](PLAN_PRAC_I_STAN_SORA_2026-10-16.md)
- [Poprzedni audyt kolizji](https://github.com/adriandziura0-rgb/sora/blob/audit-sora-kolizje-dodatkow-20261016/AUDYT_KOLIZJI_DUPLIKACJI_DODATKOW_SORA_1_2_17.md)

**STATUS KOŃCOWY:** **AUDYT-0 STATYCZNY — ZAPISANY**; **P0/P1 DO TESTÓW REPRODUKCYJNYCH**, **KOD 1.2.17 BEZ ZMIAN**.
