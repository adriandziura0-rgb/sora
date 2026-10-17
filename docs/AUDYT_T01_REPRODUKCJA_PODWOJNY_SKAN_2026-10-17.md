# SORA T01 — wykonanie testu podwójnego skanowania folderu

**Data testu:** 2026-10-17  
**TASK_ID:** `SORA-T01-FOLDER-SCAN`  
**Status:** **TEST ODTWARZAJĄCY WYKONANY — CZERWONY / BŁĄD POTWIERDZONY.** Naprawa niewykonana.  
**Kod źródłowy:** SORA 1.2.17, `sora-full-html-snapshot-1.2.17-20261016` / commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.  
**Oddzielna gałąź T01:** `sora-t01-reprodukcja-skanu-20261017`.  
**Test do przyszłej regresji:** [`tools/test_t01_folder_scan.mjs`](../tools/test_t01_folder_scan.mjs).  
**CI T01:** [uruchomienie 39030648844](https://github.com/adriandziura0-rgb/sora/actions/runs/39030648844) zakończone `startup_failure` **przed uruchomieniem zadań (0 jobs)**. To NIE jest dowód przejścia ani błędu samego testu Node.

## 1. Dawca → odbiorca i potwierdzona przyczyna

1. Dawca: udający systemowy katalog File System Access API uchwyt `Folder` ze składowymi: `A.txt`, `B.txt` i `Podfolder/C.md`. Dostawca `entry.getFile()` ma licznik wywołań, zwraca dane syntetyczne.
2. Warstwa 1: `runtime_source/static/import-recovery.js:61–77` podmienia `dodajFolderZHandle` i uruchamia `zbierzPlikiZKataloguHandle` w celu przeliczenia rozmiaru pakietu.
3. Warstwa 2: dla małych folderów uruchamia **`originalFolder(handle)`**. Oryginalna funkcja z `runtime_source/static/app.js:2694–2727` rozpoczyna jeszcze jeden `zbierzPlikiZKataloguHandle`, co ponownie wchodzi do `entry.getFile()`.
4. Odbiorca: stub `dodajWielePlikow` otrzymuje jeden pakiet 3 dokumentów. W teście małego folderu `importujPlikiDoBazy` nie był wywołany, SQLite nie było otwierane.

## 2. Rzeczywiście wykonany test w izolowanym V8

Z repozytorium pobrano **rzeczywisty tekst**:
- `runtime_source/static/app.js`, blob SHA `7e898c0aede3c8f01b3b1d3898f0ad625cca0eee`; wykonywano **rzeczywiste deklaracje** `zbierzPlikiZKataloguHandle` i `dodajFolderZHandle` z tego pliku (bez innych części przeglądarkowego UI).
- `runtime_source/static/import-recovery.js`, blob SHA `264415fd3d278300d4cc180f8c13cf180b9fa352`; wykonywano **cały rzeczywisty skrypt** IIFE.
- Infrastruktura środowiska symulowana: `document`, kontrolki, `FileSystemDirectoryHandle`/`FileSystemFileHandle`, `getFile`, wyjście pakietu, postęp i limit. Nie uruchomiono fizycznej przeglądarki, SQLite, API ani Androida.

**Wynik z licznika `getFile()`:**

| Plik | Oczekiwane wywołania | Zaobserwowane |
|---|---:|---:|
| `Folder/A.txt` | 1 | **2** |
| `Folder/B.txt` | 1 | **2** |
| `Folder/Podfolder/C.md` | 1 | **2** |
| **RAZEM** | **3** | **6** |

**Dalsze kontrole:**

| Scenariusz | Oczekiwane | Wynik |
|---|---|---|
| Normalny folder, 3 pliki i podfolder | Każdy plik tylko raz | **FAIL: 6 wywołań zamiast 3** |
| Odbiorca po normalnym folderze | Jeden pakiet trzech dokumentów | **PASS: 1 × 3 dokumenty** |
| Mały folder — błąd zgłaszany przez UI | Brak niejawnego wyjątku | **PASS: 0 błędów w symulacji** |
| Duży folder: 1 plik `X.txt` 1900 KiB | Brak skierowania do analizy jednego tekstu >1800 KiB; możliwość przekazania do bazy | **PASS: skan 1×, przycisk „Dodaj folder do bazy” widoczny; 0 pakietów analizy** |
| Zamknięcie komunikatu dużego folderu | Nic nie trafia do `importujPlikiDoBazy` | **PASS: 0 wywołań importu, komunikat zamknięty** |
| Prawdziwa aplikacja Android/Windows (WebView/WebView2) | Brak podwójnego skanu i brak regresji | **NOT_RUN — wymagane po poprawce** |
| GitHub Actions uruchamia `node tools/test_t01_folder_scan.mjs` | Czerwony test przed zmianą, zielony po | **BLOCKED** przez `startup_failure`, 0 jobs |

**Istotne rozróżnienie:** kod czyta te same pliki dwukrotnie, ale w tym teście **nie** stwierdzono podwójnego dodawania dokumentów do odbiorcy ani uszkodzenia bazy. Realny koszt czasu/RAM jeszcze niezmierzony.

## 3. Przechwycona kolizja i czystość kodu

**Własność skanowania należy aktualnie do dwóch warstw:** skrypt `import-recovery.js` skanuje, a `app.js` w kanonicznym oryginalnym `dodajFolderZHandle` skanuje drugi raz. Jest to **duplikacja operacji, nie dowód duplikacji zapisu**. Dodatkowo `import-recovery.js` podmienia globalne funkcje postępu i importu; dokładanie trzeciego wrappera jest zabronione.

## 4. Następny minimalny zakres naprawy — jeszcze NIE wdrożony

1. Na osobnej gałęzi zmian, bez ingerencji w CORE/SQLite, zapewnić **jeden skan katalogu na jedną operację**. Właścicielem odczytu plików powinien być istniejący kanoniczny `app.js`, a dodatek recovery nie powinien uruchamiać własnego pełnego skanu przed kolejnym skanem kanonicznym.
2. Zachować semantykę `1800 KiB` limitu pojedynczej analizy, `2 MiB` na plik i trasę „Dodaj folder do bazy”, anulowanie, Escape, przywracanie klikalności kontrolek i raportowanie nieczytelnych/nieobsługiwanych plików.
3. Test `tools/test_t01_folder_scan.mjs` ma zakończyć się **PASS, `actual_file_reads=3` i dokładnie jedną paczką odbiorcy**; potem uruchomić istniejący `tools/test_import_recovery.mjs`, testy A1/A2, porównania, import do SQLite, Android/PC i pełną regresję; złapać podwójne handlery oraz stary kod.
4. Dodatkowe audyty: (a) wielokrotny klik, (b) równoczesne anulowanie, (c) brak plików, (d) zagnieżdżenie i błąd `getFile`, (e) cache/stan po powrocie z picker-a, (f) brak błędnego oznaczenia „dodano do bazy” po anulowaniu.
5. **STOP**: nie scalać do `main` ani wydania 1.2.17 bez zielonego testu, regresji i nowego AUDYT-PO.

## 5. Kryterium zakończenia i status

- [x] Audyt źródła: **tak**, oba końce.
- [x] Test reprodukcyjny wykonany na rzeczywistych funkcjach JS i rzeczywistym skrypcie recovery z odizolowanym DOM: **tak**.
- [x] Powód i liczba duplikowanych wywołań: **3 → 6**.
- [x] Zapisany test Node do przyszłego uruchomienia: **tak**, osobna gałąź.
- [ ] Test Node w CI: **nie**, GitHub `startup_failure`.
- [ ] Poprawka CLEAN: **nie**.
- [ ] Test w rzeczywistym WebView/Android/Windows: **nie**.

**Decyzja:** **GO do zaprojektowania minimalnej poprawki P0 skanera**, lecz **NO-GO dla wdrożenia i wydania**. Przed poprawką wskazać dokładną granicę między dawnym `app.js` a UI/recovery, aby nie powstała kolejna łatka. Kopia danych niewymagana na potrzeby tego wyłącznie syntetycznego testu; przed jakąkolwiek zmianą realnej bazy obowiązkowa kopia i rollback.
