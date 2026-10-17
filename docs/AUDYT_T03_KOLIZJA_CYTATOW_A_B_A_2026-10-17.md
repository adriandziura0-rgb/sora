# SORA 1.2.17 — T03, stara odpowiedź cytatów po zmianie A → B → A

**Data:** 2026-10-17  
**TASK_ID:** `SORA-T03-CYTATY-A-B-A`  
**Badany commit aplikacji:** `67f48a45a79c30e8e22e8a3cb6c2426685566b42`, gałąź `sora-full-html-snapshot-1.2.17-20261016`.  
**Blok kodu badany:** `runtime_source/static/shared-content.js`, Git blob SHA `c2618cd0182755131271f13adfdf5c9d288324d2`.  
**Test:** [`tools/test_t03_quote_scope_race.mjs`](../tools/test_t03_quote_scope_race.mjs), gałąź `sora-t03-kolizja-cytatow-20261017`.  
**Status:** **T03 WYKONANY na rzeczywistym JS w izolowanym V8; RED aplikacji, test odtwarzający PASS. Naprawa jeszcze NIE wdrożona.**

## 1. Zmienne i mapa DAWCA → ODBIORCA

1. **DAWCA:** zaznaczone foldery `databaseCompareGroups` / checkboxy grupy w `databaseComparePanel` oraz `databaseCompareMode`; `scope().key = JSON.stringify([mode,groups])`. W kolejnym wyborze A → B → A klucz wraca do pierwotnej wartości.
2. **Twórca zapytania:** `shared-content.js` przycisk `soraFindQuotesBtn`, `quoteBusy`, `chosen` pobrany jednorazowo; `fetch('/api/baza/cytaty_wybranych?...')` bez `AbortController.signal`.
3. **API:** w `runtime_source/app.py` `GET /api/baza/cytaty_wybranych` uruchamia `selected_quote_database` na już ukończonych analizach. API jest przeznaczone tylko do odczytu.
4. **ODBIORCA:** `const data=await resp.json()`; `if(scope().key!==chosen.key) return`. Nie ma **monotonicznego identyfikatora żądania ani rewizji zaznaczenia**. Powrót do A przechodzi kontrolę, mimo że żądanie dotyczyło poprzedniego cyklu A.
5. **Ekran i eksport:** `quotePayload=data`, `quoteScope=chosen.key`, `quoteDownload.disabled=false`, `quoteResults.innerHTML` + komunikat statusu. Sprawdzenie `quoteScope===scope().key` przy eksporcie również przepuszcza stare A.

**Inny tor kodu:** `/api/baza/wspolna_tresc` ma `AbortController` i sprawdza tożsamość kontrolera. **Nie udowodniono**, że wszystkie scenariusze A→B→A są tam poprawne, ale nie wolno mylić tej ścieżki z cytatami.

## 2. Reprodukcja (bez modyfikacji baz)

Pobrano z GitHub **niezmodyfikowany rzeczywisty tekst `shared-content.js`** podanym SHA. Uruchomiono go w izolowanym V8 z syntetycznym DOM, zaznaczeniem, odpowiedzią `fetch` rozwiązywaną ręcznie i stubem eksportu. Test dotyczy prawdziwego kodu event-handlerów; **nie jest to fizyczny WebView ani realny Flask/SQLite**.

| Scenariusz | Oczekiwana własność | Faktyczny wynik |
|---|---|---|
| A1 rozpoczęte, wybór B→A2, wraca odpowiedź A1 | A1 nie może aktualizować A2 | **FAIL: stary A1 zapisuje cytaty w UI** |
| Eksport po zaakceptowanym starym A1 | Nie można wyeksportować A1 jako A2 | **FAIL: stare dane dają się eksportować** |
| A1 rozpoczęte, wybór B i brak powrotu do A | Odrzucić odpowiedź A1 | **PASS** |
| A1→B→A2, wraca błąd starego HTTP | Stary błąd nie może dotyczyć nowego wyboru A2 | **FAIL: stary błąd jest wyświetlany** |
| A1 oczekuje, B→A2, użytkownik próbuje uruchomić A2 | A2 może rozpocząć nowe żądanie | **FAIL: `quoteBusy` blokuje drugie żądanie; `fetch_count=1`** |
| Sygnał anulowania żądania cytatów | Może zakończyć nieaktualne żądanie | **NIE MA `signal` w `fetch` cytatów** |

**Wynik testu powtarzalnego:**
- `--audit`: **PASS** — zachowanie starego błędu i test negatywny A→B potwierdzone.
- `--gate`: **FAIL** (celowo czerwony do czasu naprawy; pierwsza asercja zgłasza `stare A1 nadpisało nowe A2`).
- Oba tryby wykonane na tych samych rzeczywistych instrukcjach `shared-content.js`, bez zmian do SQLite i kodu produkcyjnego.
- Github Actions na wcześniejszej izolowanej gałęzi T01 kończył się `startup_failure` przed startem pracy (0 jobs); **nie twierdzić, że T03 zaliczył Actions/CI**.
- Test fizycznego telefonu/Windows: **NOT_RUN**.

## 3. Potwierdzone przyczyny i czystość kodu

**Problem:** `scope().key` identyfikuje *zestaw wybranych grup*, ale nie *iterację* wyboru. A1 i A2 mają identyczny klucz. Dodatkowo `quoteBusy` żyje do zakończenia pierwotnego żądania; onChange nie unieważnia aktywnego pobrania cytatów, jeśli `quoteScope` jest jeszcze `null`.

**Reguła CLEAN:** nie dodawać drugiego równoległego mechanizmu „cytaty-wyniki” ani monkey-patcha globalnego `fetch`. Poprawka w jednym właścicielu stanu cytatów powinna integrować `request_id`/rewizję i `AbortController`, reset danych, błędów i `quoteBusy`; wszystkie ścieżki sukcesu/błędu/`finally` powinny odrzucać starszą generację. Nie zmieniać klasyfikatora, parsera cytatów ani schematu SQLite dla czysto prezentacyjnego race condition.

## 4. Kryteria przyjęcia przyszłej poprawki

- `node tools/test_t03_quote_scope_race.mjs --gate` → **PASS**, `--audit` historycznie pozostaje opisem poprzedniego błędu (nie traktować jego oczekiwań jako docelowej semantyki).
- Równoległe kliknięcia, wybór A→B→A, błąd 404/500, anulowanie, eksport JSON i zmiana trybu folder/redakcja — brak starego wyniku lub fałszywego komunikatu.
- Ponowić `tools/test_scope_integrity.mjs`, `tools/test_import_recovery.mjs`, `tools/test_quote_database.py`, test A1/A2 oraz regresję UI PHONE/PC. Dopiero po całym CI/urządzeniu można twierdzić E2E.
- Kontrola po: dokładny diff, czy jedna obsługa eventu, czy nie ukryto nowych danych, brak nowej duplikacji, czy anulowanie nie dotyka bazy.

## 5. Stan pozostałych etapów

T01: czerwony test skanowania 3→6, przygotowany w osobnej gałęzi, poprawka nie wdrożona.  
T02: wcześniej SQL-projekcja potwierdzała zaniżanie liczby folderów; **późniejsza próba z 2026-10-17 wykonała również realne moduły `DocumentDatabase`, `editorial_compare`, `database_overview` wydobyte z oryginalnego APK 1.2.17**, na czterech nowych, usuwanych bazach SQLite. Potwierdzono A=1/B=0 w kolejności A→B, odwrotnie B→A, A=B=1 dla różnego tekstu oraz narastanie `import_events` dla powtórek. Weryfikacja Git blob SHA modułów zgodna z bieżącym commitem. Wszystkie `PRAGMA integrity_check` i `foreign_key_check` przechodzą. Test ten nie jest fizycznym E2E aplikacji. Należy zaktualizować dokument T02 i rejestr postępu, bez zgadywania co do preferowanej definicji "artykuł".
T03: **reprodukcja RED gotowa do minimalnej naprawy P1, bez modyfikacji programu.**

**Decyzja:** GO na projekt małych napraw po ustaleniu kontraktu T02. **NO-GO** na przebudowę bazy/CORE, usuwanie kodu bez audytu i publikację nowej wersji do użytkownika. Zapisane testy i wyniki są punktem wznowienia; nie powtarzać ich przy tym samym SHA bez nowego celu.
