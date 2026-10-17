# SORA — T02: ta sama treść z dwóch folderów (DAWCA → ODBIORCA)

**Data:** 2026-10-17  
**TASK_ID:** `SORA-T02-TOZSAMOSC-FOLDEROW`  
**Badana wersja kodu:** SORA 1.2.17, `sora-full-html-snapshot-1.2.17-20261016`, `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.  
**Gałąź bezpiecznych testów i dokumentacji:** `sora-t02-deduplikacja-foldery-20261017`.  
**Status po aktualizacji tego samego dnia:** **T02 POTWIERDZONY NA PRAWDZIWYCH MODUŁACH PYTHON 1.2.17** uzyskanych z oryginalnego artefaktu APK i porównanych co do Git blob SHA z badanym commitem. Cztery scenariusze i integralność SQLite PASS; **to nadal nie jest realny E2E telefonu ani zatwierdzony kontrakt wieloprzypisania**. Historyczny etap projekcji SQL opisano poniżej.

## 1. Cel i definicja dwóch różnych pojęć

1. **Unikalna treść**: tekst o ustalonym SHA; tę samą treść najlepiej analizować raz.
2. **Wystąpienie publikacji/źródła**: ten sam tekst znaleziony pod dwiema ścieżkami, w dwóch folderach lub nawet u dwóch redakcji. Ta informacja może być potrzebna **osobno**, aby raport o folderze i pochodzeniu nie był zaniżony.

W SORA 1.2.17 te pojęcia są połączone w pojedynczy rekord `documents` ze **stałym pojedynczym `relative_path`**. Wybór, czy raport ma liczyć unikalne treści, czy wystąpienia w folderach, wymaga zatwierdzonego kontraktu. Żadna migracja nie jest dopuszczona samym wynikiem T02.

## 2. Dowody DAWCA → ODBIORCA w rzeczywistym kodzie

| Kolejny element | Źródło dowodu | Co faktycznie robi |
|---|---|---|
| DAWCA 1 | `Folder_A/ten_sam.txt` | wysyła ten sam tekst i ścieżkę A |
| DAWCA 2 | `Folder_B/ten_sam.txt` | wysyła taki sam tekst i ścieżkę B |
| ODBIORCA API | [`runtime_source/app.py` `/api/baza/importuj` linie ~358–432](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/app.py#L358-L432) | przekazuje treść/nazwę/`relative_path` do `DocumentDatabase.begin_import`; `duplicate` nie trafia do worker-a |
| Unikalność w SQLite | [`document_database.py` linia ~162](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/document_database.py#L162) | `documents.content_sha256 TEXT NOT NULL UNIQUE`, jedna `relative_path` |
| Deduplikacja i zapis zdarzenia | [`document_database.py` linie 276–295](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/document_database.py#L276-L295) | przy istniejącym SHA `done/processing` dodaje `import_events(outcome='duplicate', relative_path=B)`, ale zwraca dotychczasowy dokument, bez utworzenia przypisania do B |
| Indeks folderów | [`document_database.py` `list_document_folders` linie 564–594](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/document_database.py#L564-L594) | pobiera wyłącznie wiersze `documents`; `import_events` nie zasila indeksu |
| Grupy raportu | [`editorial_compare.py` linie 157–196](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/editorial_compare.py#L157-L196) | nazwa folderu pochodzi z pierwszego segmentu `documents.relative_path`; brak drugiej ścieżki |
| Analiza zaznaczonych | [`database_overview.py` linie 29–56](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/runtime_source/clean_core/database_overview.py#L29-L56) | iteruje ukończone dokumenty; filtruje po **jednej** przypisanej grupie |
| Ekran / eksport | `/api/baza/analiza_wybranych` → `static/full-database.js` → raport HTML/JSON | odziedziczy brak B z danych agregatu; samo UI nie może odtworzyć drugiego przypisania |

## 3. WYKONANY test lokalny w izolowanym SQLite — projekcja SQL kontraktu

W Pythonie uruchomiono na **tymczasowych bazach SQLite** model dokładnie istotnych reguł SQL SORA: `content_sha256 UNIQUE`, transakcję `BEGIN IMMEDIATE`, wstawienie nowej treści, `import_events(duplicate)` zamiast kolejnego rekordu, oraz grupowanie z jednego `relative_path`. W modelu nie zaimportowano pełnego `clean_core` i nie wywołano prawdziwego endpointu, dlatego raport rozdziela **projekcję wykonaną** od **testu rzeczywistego modułu oczekującego**.

| Scenariusz | Importy | Liczba rekordów documents | Zdarzenia importu | Folder A | Folder B |
|---|---|---:|---:|---:|---:|
| A potem B — tekst identyczny | new, duplicate | **1** | 2 (1 duplicate) | **1** | **0** |
| B potem A — tekst identyczny | new, duplicate | **1** | 2 (1 duplicate) | **0** | **1** |
| A potem B — tekst różny | new, new | **2** | 2 (0 duplicate) | **1** | **1** |
| A potem B, B powtórzony | new, duplicate, duplicate | **1** | 3 (2 duplicate) | **1** | **0** |

**Wynik lokalny:** 4 projekcje SQL **PASS** pod względem zgodności z przeanalizowanym kontraktem. **Problem semantyczny:** w widoku folderów brak B pomimo wystąpienia B w zdarzeniu `import_events`. Kolejność importu rozstrzyga, który folder „posiada” rekord. Ponowienie tego samego importu dodaje kolejne zdarzenie duplikatu, nawet gdy liczba unikalnych treści nie rośnie.

**Wniosek ostrożny:** bez względu na to, czy biznesowo chcemy deduplikować analizę, **nie wolno automatycznie utożsamiać liczby unikalnych tekstów z liczbą publikacji lub wystąpień folderowych**. Nie jest to dowód utraty treści z `documents` ani korupcji SQLite.

## 4. Kanoniczny test repozytorium przygotowany (osobna komenda --audit pozostaje NOT_RUN)

[`tools/test_t02_duplicate_folders.py`](../tools/test_t02_duplicate_folders.py) to test przygotowany tak, aby **uruchomić rzeczywiste** `DocumentDatabase`, `mark_success`, `iter_completed_results`, `list_document_folders`, `list_documents`, `list_comparison_groups`, `build_selected_database_overview`. Używa wyłącznie syntetycznych TXT i `TemporaryDirectory` z nową bazą; sprawdza też `PRAGMA integrity_check` oraz `foreign_key_check`. **Komenda tego konkretnego skryptu nie została uruchomiona na checkout repozytorium. Wykonano natomiast później równoważny test tych samych rzeczywistych modułów wyodrębnionych z podpisanego artefaktu APK 1.2.17 — szczegóły i dowód niżej w sekcji 7.**

Polecenia po sklonowaniu gałęzi:
```bash
python tools/test_t02_duplicate_folders.py --audit
python tools/test_t02_duplicate_folders.py --gate
```

- `--audit` (obecny kontrakt): powinien zakończyć się PASS, jeśli w pełnych modułach zobaczymy opisane A-only/B-only oraz import_events. Jeśli nie — STOP, raportować różnicę i zmienić diagnozę.
- `--gate` (hipotetyczne liczenie *wystąpień*): oczekuje widoczności tego samego tekstu w A i B, więc **dla wersji 1.2.17 powinien być RED**. Nie jest jednak obowiązującą definicją biznesową dopóki decyzja architektoniczna nie zostanie przyjęta.
- Wyniki **NOT_RUN**, nie wolno dopisywać PASS/FAlL testu pełnych modułów na podstawie projekcji SQL.

## 5. Testy i ryzyko CLEAN

| Kontrola | Status |
|---|---|
| Rzeczywiste gałęzie i SHA programu | **PASS** (zweryfikowano `67f48a45...`) |
| Wykonanie 4 projekcji istotnego kontraktu SQL na temp SQLite | **PASS** |
| Odtworzenie utraty *drugiej lokalizacji w indeksie* | **POTWIERDZONE LOGICZNIE przez kod + projekcję SQL** |
| Zachowanie RAW / SQLite użytkownika | **PASS (nie otwierano danych użytkownika)** |
| Python `clean_core` z oryginalnego APK 1.2.17 | **PASS — 4 scenariusze + integralność**; osobny kanoniczny plik `tools/test_t02_duplicate_folders.py` nadal NOT_RUN |
| Rzeczywiste Flask API / WebView / APK / PC | **NOT_RUN** |
| Nowa migracja/zmiana schematu/naprawa | **NIE WYKONANO** |
| Czy deduplikacja unikalnego tekstu sama w sobie jest błędem? | **NIE**; kontrakt produktu wymaga decyzji |
| Czy `import_events` gwarantuje odzyskanie wszystkich oryginalnych publikacji? | **NIEZWERYFIKOWANE**; zdarzenia są historią importu, nie tabelą wystąpień o stabilnym UID |

## 6. Decyzja i następny krok bez kręcenia się w kółko

**AUDYT T02 zaliczony w zakresie SQL, rzeczywistych modułów Pythona i prześledzenia dawca–odbiorca.** **Bramka zmiany schematu pozostaje NO-GO**: nadal brak decyzji, czy raporty liczą unikalne treści czy wystąpienia w folderach. Osobny plik `--audit` w gałęzi nie był wykonywany, ale jego ścieżki funkcjonalne sprawdzono równoważną próbą na module z APK.

**Zalecana (niezatwierdzona) architektura:**
- Zachować **jeden dokument i jeden wynik analizy na unikalną treść** (ochrona obecnego silnika i deduplikacji).
- Odrębnie ewidencjonować **wystąpienia/pochodzenie w folderach** powiązane z `document_id` lub stabilnym źródłowym identyfikatorem, nie mnożyć analizy tego samego tekstu.
- Porównania pokazywać rozdzielnie: `unikalne artykuły` vs `liczba wystąpień publikacji`; nie mylić dwóch grup z dwoma niezależnymi dokumentami.
- Wszelkie zmiany tabel, TRANSFER, eksportów, UID, walidacji starszych baz wymagają osobnego ADR, wersjonowanej migracji na kopiach, backupu i regresji PC↔PHONE; **nie wprowadzać schematu w T02**.

**Stan najnowszy (17.10):** pełne moduły T02 już sprawdzone, a T03 (wyścig cytatów A→B→A) odtworzony w osobnym teście źródłowego JavaScript. **Następny krok:** decyzja architektoniczna co do unikalnej treści vs wystąpień w folderach, następnie izolowane minimalne poprawki z ochroną CORE i regresją. Nie powtarzać całych audytów bez zmiany SHA lub nowego dowodu.


## 7. NOWY DOWÓD — rzeczywiste moduły wydobyte z APK SORA 1.2.17

**Sposób wykonania:** oryginalny artefakt GitHub Actions `Drogowskazy-Sora-APK`, artifact ID `12029879124`, run `38864600041`. Wyodrębniono `Drogowskazy-Sora-1.2.17.apk` → `assets/drogowskazy-runtime.zip` (66 plików). Z ZIP-a tymczasowo zaimportowano `clean_core.document_database.DocumentDatabase`, `editorial_compare.list_comparison_groups`, `database_overview.build_selected_database_overview`. **Brak sieci, prywatnych danych i modyfikacji oryginalnego APK**. Testowy plik SQLite powstawał oddzielnie w `TemporaryDirectory` dla każdego scenariusza.

- Git artifact ZIP SHA-256: `89a866dff52457d71881775e18a3e1b119672c7a93070fecbe92a3e6e5f1231b`.
- `document_database.py`: Git SHA `2a8398f841417a34d4e489fcf7ae34fa5e04c525` — **zgodny z repo 1.2.17**.
- `editorial_compare.py`: Git SHA `814b2ac8bf923c972fd0ea603d51499bd65cbd84` — zgodny.
- `database_overview.py`: Git SHA `e226e7cacf3d232e7df73a94cdd0d215d1ade4e9` — zgodny.
- `shared-content.js`: Git SHA `c2618cd0182755131271f13adfdf5c9d288324d2` — zgodny.
- JSON wyników w odizolowanym środowisku: SHA-256 `ed714fca5f1c7c7c47010e1c730d5d7480cc96fe2cf12c7e9e72ea44edab82fb`.

| Scenariusz | Wynik `begin_import` | `documents` | `list_documents` A | `list_documents` B | `import_events` | `PRAGMA integrity_check` / FK |
|---|---|---:|---:|---:|---:|---|
| A → B identyczna treść | new, duplicate | 1 | 1 | 0 | 2 | ok / 0 |
| B → A identyczna treść | new, duplicate | 1 | 0 | 1 | 2 | ok / 0 |
| A → B różna treść | new, new | 2 | 1 | 1 | 2 | ok / 0 |
| A → B → B ten sam tekst | new, duplicate, duplicate | 1 | 1 | 0 | 3 | ok / 0 |

**Weryfikacja odbiorcy:** `list_comparison_groups(..., mode='folder')` przy A→B pokazuje **jedynie Folder_A:1**, a przy B→A **jedynie Folder_B:1**; raport `build_selected_database_overview(...groups=[A,B])` ma `analyzed_articles=1`. Gdy tekst jest różny, obie grupy mają po 1, `analyzed_articles=2`.

**Interpretacja:** rzeczywisty kod Pythona potwierdza, że tożsamość treści jest deduplikowana prawidłowo na poziomie przechowywania analizy, lecz wystąpienie w kolejnym folderze nie zasila statystyk tego folderu. **Nie zmieniać bez ADR** `UNIQUE(content_sha256)`, TRANSFER i referencji innych tabel. Próg produktowy (unikalne treści vs wystąpienia publikacji) pozostaje otwarty.

**CI i E2E:** ten test uruchomiono lokalnie na faktycznym runtime APK, **nie w Actions**; nie odtworzono fizycznego Androida/Windows i nie przeprowadzono migracji istniejącej bazy.
