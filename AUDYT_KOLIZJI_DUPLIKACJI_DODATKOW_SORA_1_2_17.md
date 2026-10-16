# SORA 1.2.17 — audyt duplikacji, nakładania kodu i kolizji dodatków

**Stan źródeł:** `sora-full-html-snapshot-1.2.17-20261016`, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`; Android run `38864600041` SUCCESS, Windows run `38864600077` SUCCESS. **Audyt statyczny:** sprawdzono listę plików repozytorium, główne dodatki JS, kolejność skryptów, HTML, CSS, istotne moduły Python (porównania, foldery, matcher, cache, cytaty, agregaty, eksport, SQLite), mosty Android / natywny Windows oraz testy A1/A2. Nie było rzeczywistej prywatnej bazy do pomiaru trafności i nie przeprowadzano nowych testów manualnych.

## 1. Mapa właścicieli danych i kodu

| Obszar | Źródło prawdy | Konsumenci/dodatki | Krytyczna granica |
|---|---|---|---|
| Analiza pojedynczego artykułu | `clean_core/**`; wynik w `document_database.py` | `static/app.js`, mosty PHONE/PC | Odczyt/eksport A2 nie może po cichu uruchamiać nowego klasyfikatora |
| Porównanie 1–10 grup | `editorial_compare.py`, `database_overview.py`, `topic_report_cache.py` | `static/app.js`, `static/full-database.js` | Ten sam `mode/groups`, brak starego wyniku po zmianie |
| Ta sama sprawa | `topic_matcher.py`, `editorial_compare.py` | `static/app.js`, `static/same-story-mobile.js` | Zawsze bieżący `topic_id` **i** wszystkie wybrane redakcje; matcher heurystyczny |
| Cytaty i wspólne fragmenty | `quote_database.py`, `shared_content.py` | `static/shared-content.js`, karty jednej sprawy | Nie mieszać cytatów z różnych zaznaczeń; nie mylić źródła przywołanego z redakcją |
| Foldery i import | `static/app.js` + trwała kolejka SQLite | `static/import-recovery.js`, SAF Android, katalogi Windows | Dodatki nie mogą niejawnie podmieniać głównej implementacji importu |
| Wersja i pakiet | `runtime_source/**` + manifest + `build_runtime_from_sources.py` | APK, EXE, `ProjectStore.java` | Identyczny podpisany runtime PHONE ↔ PC; zachowanie baz/WAL/SHM |
| Wyświetlanie | `templates/index.html` + 4 pliki CSS + 5 JS | WebView Android i WebView2 PC | Nie dodawać drugiego właściciela tego samego stanu |

## 2. Ustalenia pozytywne, NIE USUWAĆ

1. Finalna wersja gałęzi rozwojowej to **1.2.17**; build Android i Windows na tym samym SHA jest zielony.
2. `templates/index.html` ma **197 unikalnych `id` — zero zduplikowanych w statycznym HTML**. Skrypty są ładowane kolejno: `app.js` → `full-database.js` → `shared-content.js` → `import-recovery.js` → `same-story-mobile.js`.
3. A1 posiada już `AbortController`, porównanie klucza zakresu, kasowanie starej tabeli/JSON po błędzie i kontrolę wybranego tematu. **Nie dorabiać drugiego mechanizmu na ten sam zakres.**
4. A2 1.2.16 zachowuje dla pojedynczego dokumentu identyfikator zapisanego wyniku, hash treści oraz eksport bez niejawnego przeliczenia. Traktować jako stały kontrakt.
5. Sprawdzone kluczowe moduły Python nie mają powtarzanych **nazw definicji najwyższego poziomu w tym samym pliku**. `_tokens` w `topic_matcher.py` i `shared_content.py`, `_clean` w `editorial_compare.py` i `quote_database.py` to **osobne zakresy nazw**; nie wolno uznać tego automatycznie za błąd ani scalić bez testów semantycznych.
6. Powtarzające się `const warnings` w `app.js` są w osobnych funkcjach renderujących — to NIE jest kolizja globalnych nazw.

## 3. Wykryte problemy oraz dowód kodowy

### P0 / wysoki — dynamiczne nadpisywanie funkcji importu

**Plik:** `runtime_source/static/import-recovery.js:17-19,48-91`.

Dodatek zapisuje odwołania do wcześniejszych implementacji, a następnie **bezpośrednio podmienia** globalne `pokazPostepOperacji`, `zakonczPostepOperacji`, `bladPostepuOperacji`, `zbierzPlikiZKataloguHandle`, `dodajFolderZHandle` i `dodajPlikiZFileList`. Jest to działająca warstwa monkey-patch, nie niezależny adapter. Zmiana kolejności skryptów albo kolejna podmiana mogą zmienić zachowanie importu bez jawnego konfliktu kompilacji.

**Potwierdzona zbędna praca:** przy folderze mieszczącym się w limicie wrapper `dodajFolderZHandle` najpierw skanuje katalog przez `zbierzPlikiZKataloguHandle` (linia 67), a później wywołuje `originalFolder(handle)` (linia 75), gdzie pierwotna funkcja skanuje katalog ponownie. Oznacza to powtórny odczyt/skan katalogu na tej samej ścieżce wykonania (czas zależy od liczby plików). Wywołanie `originalFolder` pozostawić jako zgodność wyłącznie przejściowo.

**Naprawa:** w docelowym źródle `app.js` jedna odpowiedzialność za skan/wybór, jawna funkcja walidacji rozmiaru i zdarzenie `onImportProgress/onImportCancelled`; dodatek wyłącznie prezentuje komunikaty. Bez kolejnego globalnego wrappera.

### P1 / wysoki — cytaty są chronione słabiej niż porównanie folderów

**Plik:** `runtime_source/static/shared-content.js:42-102,130-174`.

Pobranie cytatów uruchamia `fetch` bez `AbortController` i używa `quoteBusy` + porównania `scope().key` dopiero po odpowiedzi. Gdy użytkownik w czasie oczekiwania zmieni zakres **A → B → A**, odpowiedź rozpoczęta dla A może zostać przyjęta jako aktualna, bo klucz ponownie pasuje. Przy wyborze B w trakcie pobrania `quoteScope` nadal jest `null`, więc samo `change` nie anuluje żądania. W tym samym pliku porównanie wspólnych fragmentów ma już `AbortController` i `activeKey`.

**Naprawa:** zastosować jednolity `request_id`/generację oraz `AbortController` także do cytatów, reset przy **każdej** zmianie grupy, konsekwentnie odblokować przyciski; w wynikach i eksporcie przechowywać zarówno `scope_key`, jak i rewizję ukończonych analiz.

### P1 / średni — wielu właścicieli stanu zaznaczenia i renderowania

**Pliki:** `static/app.js`, `full-database.js`, `shared-content.js`, `same-story-mobile.js`.

Wszystkie odczytują te same ukryte `select`, checkboxy i zmiany zakresu. `full-database.js` rejestruje **5 obserwatorów MutationObserver**, `same-story-mobile.js` kolejny obserwator tabeli. To NIE dowodzi automatycznie zapętlenia, ale zwiększa liczbę współbieżnych ścieżek odświeżania, autosave i przywracania po restarcie. Wyniki zależą od kolejności aktualizacji DOM i właściwości `.selected/.checked` (zmiana właściwości nie musi emitować zdarzenia).

**Naprawa:** jeden kontroler zakresu `selectionChanged({mode, groups, topic_id, revision})`; wszystkie dodatki tylko subskrybują zdarzenie; jeden autor aktualizuje checkboxy/select; obserwatory pozostają wyłącznie do zgodności ze starszym UI, a następnie znikają po testach E2E.

### P1 / średni — powtórzone warstwy renderowania jednej sprawy

**Pliki:** `static/app.js: renderujPorownanieBazyDo/renderujPorownanieMultiDo`, `static/same-story-mobile.js:render`.

Oryginalna tabela i karty mobilne osobno formatują część tego samego payloadu. To uzasadnione pod kątem układu, ale nie powinny niezależnie decydować o statusie aktualności danych. Karty powstają na podstawie `MutationObserver` tabeli. A1 chroni `topic_id` oraz nazwy redakcji, co trzeba zachować.

**Naprawa:** jeden walidowany model `ComparisonViewModel` (ID, zakres, metryki, status, provenance); oddzielne prezentacje `table` i `cards`. Test parytetu wszystkich metryk i cytatów w obu wariantach.

### P2 / niski — ewidentne powtórzenia UI i wspólnych funkcji pomocniczych

- `static/app.js:3872`: lista sekcji czyszczonych przez „Wyczyść” powtarza m.in. `candidateCategoriesSection`, `actorAgencyDashboardSection`, `humanChecklistSection`, `expertSummarySection`, `expertReportSection`. Ponowne czyszczenie tych samych elementów nie jest groźne, ale należy deduplikować tablicę.
- `static/full-database.js`, `shared-content.js`, `same-story-mobile.js`: własne funkcje escapingu, formatowania i eksportu. Część już wywołuje wspólne `pobierzPlik`; wspólną bibliotekę wydzielać tylko po sprawdzeniu kontraktów SAF i WebView2.
- `clean_core/shared_content.py` i `topic_matcher.py` mają własne tokenizatory; ich podobieństwo nazw nie oznacza równoważnej semantyki. **Nie scalać na podstawie samej nazwy.**

### Kontrola CSS/HTML

`style.css`, `full-database.css`, `shared-content.css`, `same-story-mobile.css` razem definiują setki reguł. Nie ustalono konfliktu kaskady wyłącznie na podstawie liczby selektorów; potrzebne zrzuty wizualne oraz test styli po przełączaniu Użytkownik/Ekspert i po otwarciu/ukryciu kart. **Brak powielonych statycznych ID HTML (197/197 unikalnych).**

## 4. Testy, które są i czego jeszcze brakuje

- Istnieją: `test_scope_integrity.mjs` (A1, 4xx/5xx i nieaktualne wyniki), `test_article_identity.mjs` (A2, identyfikacja dokumentu), `test_view_persistence.mjs`, `test_android.mjs`, `test_transfer.py`, `test_release_clean.py`, 257/257 GOLD.
- Brakuje celowanej regresji: cytaty A→B→A; kliknięcie folderu przy jednoczesnym przełączaniu trybu; dwa otwarcia pickera; cancel/escape podczas skanowania; jeden skan folderu na próbę; odtwarzanie WebView i przywracanie selection między modułami; pełny parytet tabel i kart; test porównania przy podmianie ukończonej analizy w SQLite w tym samym wyborze; CSS visual regression.
- W tym audycie **nie zmieniono kodu wykonywalnego i nie uruchomiono nowych testów E2E**. Zielone buildy dotyczą bazowej wersji 1.2.17, a nie tych planowanych zmian.

## 5. Priorytety

1. ZAMROZIĆ aktualny 1.2.17 jako punkt odniesienia, hash i testy, kopia eksportu baz, zero zmian CORE.
2. Zbudować test kolizji importu i cytatów bez zmiany kodu; odtworzyć obecny czas/stan; zapisać wynik bazowy.
3. Naprawić globalne nadpisywanie funkcji i powtórne skanowanie folderów w kanonicznym kodzie; nie zmieniać normalizacji danych.
4. Ujednolicić unieważnianie i anulowanie wszystkich żądań (scope + request generation + DB revision).
5. Zastąpić wielokrotne obserwatory spójnym kontrolerem zdarzeń, bez utraty działania po przywróceniu sesji.
6. Dopiero na końcu porządkować powtarzane helpere i tablice oraz wygląd CSS; kontrola kompletności metryk i dowodów.
7. Nowe APK/EXE dopiero przy zielonych testach na tym samym commicie, w tym PHONE↔PC TRANSFER, SQLite/WAL/SHM, brak powtórnego pobierania i GOLD.

**Nie stosować kolejnej łaty nadpisującej globalną funkcję.** Wszystkie poprawki wprowadzać do kanonicznego źródła `runtime_source`, aktualizować manifest, jawnie dokumentować regresje.