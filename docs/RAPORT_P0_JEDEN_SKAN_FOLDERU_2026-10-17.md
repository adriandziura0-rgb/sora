# SORA P0 — naprawa pojedynczego skanu folderu

**Data:** 2026-10-17  
**TASK_ID:** `SORA-P0-JEDEN-SKAN`  
**Stan:** **KOD ZMIENIONY NA IZOLOWANEJ GAŁĘZI, LOKALNE TESTY JS PASS, MANIFEST RUNTIME ZWERYFIKOWANY, GITHUB ACTIONS BLOCKED**. Niepublikowane APK/EXE, nie ma potwierdzenia pracy na fizycznym Android/Windows.  
**Źródło prawdy przed zmianą:** `sora-full-html-snapshot-1.2.17-20261016` @ `67f48a45a79c30e8e22e8a3cb6c2426685566b42`.  
**Gałąź P0:** `sora-full-p0-single-scan-20261017`. Zmiana nie jest w `main` ani w powyższej bazowej gałęzi 1.2.17.

## 1. Audyt → przyczyna → najmniejsza zmiana

Wersja bazowa była identyczna bajtowo z [oryginalnym APK 1.2.17](https://github.com/adriandziura0-rgb/sora/actions/runs/38864600041) (Git blob `app.js=7e898c0aede3c8f01b3b1d3898f0ad625cca0eee`, `import-recovery.js=264415fd3d278300d4cc180f8c13cf180b9fa352`). Przed zmianą test rzeczywistych funkcji JS z symulowanym katalogiem wykazał dwie wizyty `getFile()` na każdy dokument, ponieważ:
- `import-recovery.js` skanował folder po to, by obliczyć rozmiar i zaoferować „Dodaj folder do bazy” dla dużego pakietu;
- następnie `originalFolder(handle)` w `app.js` **skanował ten sam katalog ponownie**.

**Zmiana minimalna (bez nowego modułu, bez drugiego kolektora, bez modyfikacji CORE/SQLite):**

1. [`runtime_source/static/app.js`](../runtime_source/static/app.js): istniejąca funkcja `dodajFolderZHandle(dirHandle, precollectedEntries=null)` przyjmuje opcjonalnie już zebrane `entries`; gdy parametru nie podano, **działa jak dawniej** i wykonuje własny skan; gdy przekazano listę, przetwarza ją bez ponownego wywołania `zbierzPlikiZKataloguHandle`.
2. [`runtime_source/static/import-recovery.js`](../runtime_source/static/import-recovery.js): dwa dotychczasowe wywołania `originalFolder(handle)` zastąpione `originalFolder(handle,entries)`. Ta sama lista `entries` wchodzi do dalszej walidacji.
3. [`tools/test_t01_folder_scan.mjs`](../tools/test_t01_folder_scan.mjs): promowano wcześniejszy test T01 na obecny branch, jako **bramkę: 3 pliki = 3 odczyty + jeden pakiet**. Dwa istniejące workflow ([Android](../.github/workflows/build-apk.yml), [Windows](../.github/workflows/build-windows.yml)) otrzymały **po jednej linii** uruchamiającej test po istniejącym `test_import_recovery.mjs`. Stare testy i pozostały kod bez zmian.

**Obrona przed regresją:** bez modułu recovery funkcja nadal akceptuje normalny `handle`; przy braku obsługiwanych plików `originalFolder` otrzymuje precollected listę i zgłasza istniejący błąd; nie dokładać wrapperów, monkey-patchy, starych kopii skanera ani równoległych ścieżek.

## 2. Dawca → odbiorca po zmianie

`showDirectoryPicker` → `zbierzPlikiZKataloguHandle(handle)` **1×** → `entries` z `relativePath` i `readError` → `import-recovery.js` (limit 1800 KiB, filtr rozmiaru 2 MiB/plik, przy dużych danych jawny wybór) → **`originalFolder(handle,entries)`** → `czyObslugiwanyPlik` / `odczytajPlikTekstowy` → `dodajWielePlikow(accepted)` → analiza lub ręczna ścieżka `importujPlikiDoBazy` → istniejący zapis SQLite (nietknięty).

Zestaw `entries` nie jest dodatkowo zapisywany ani cache'owany globalnie. Jeden owner odczytu plików: istniejący `zbierzPlikiZKataloguHandle`; wrapper kontroluje rozmiar, a istniejący `dodajFolderZHandle` przygotowuje pakiet do analizy.

## 3. Rzeczywiście wykonane testy

**Środowisko:** Node.js 22, izolowany V8/Node VM, `app.js` + kompletny `import-recovery.js` z oryginalnego APK 1.2.17 oraz dokładnie te same zmienione pliki JS z gałęzi; pliki i DOM syntetyczne. Nie wykonano sieciowych żądań, nie otwarto bazy użytkownika.

| Test | Przed (bazowy kod) | Po (zmiana P0) | Weryfikacja |
|---|---|---|---|
| 3 pliki i podfolder: liczba `getFile()` | **6** | **3** | PASS |
| Pakiet przekazany dalej | 1 pakiet/3 pliki | 1 pakiet/3 pliki | PASS |
| Folder z plikami nieobsługiwanymi i >2MiB | 6 odczytów/1 zaakceptowany | **3 odczyty/1 zaakceptowany** | PASS |
| Zbyt duży folder 1900KiB | wybór „Dodaj do bazy” | wybór, 1 skan, import 1 pakiet | PASS |
| Zbyt duży folder: „Zamknij” | brak zapisu | brak zapisu | PASS |
| Brak obsługiwanych plików | brak pakietu; UI sygnalizuje błąd | brak pakietu; UI sygnalizuje błąd | PASS z zachowaniem istniejącego zachowania |
| Podwójne kliknięcie w trakcie skanu | 2 odczyty, 1 pakiet | **1 odczyt, 1 pakiet** | PASS |
| Anulowanie podczas skanu | brak przekazania | brak przekazania | PASS |
| `node --check` obu JS + skrypt testu | — | składnia poprawna | PASS |
| Przed/po SHA źródła produkcyjnego | porównano z APK/Git | blob SHA `app.js=eb4d6392642903f240851c83672e9f5d38cb2f91`, `import-recovery.js=c70eea3d530e6023f4e6dec7aa3c90ed578a6c7c`, zgodne z Git | PASS |
| Historyczny `tools/test_import_recovery.mjs` na nowej gałęzi | wcześniej CI 1.2.17 SUCCESS | **NOT_RUN / czeka na CI** | BLOKADA |
| `tools/test_t01_folder_scan.mjs` bezpośrednio w Actions | dodany test automatyczny | **NOT_RUN — startup_failure przed uruchomieniem jobs** | BLOKADA |
| 257 GOLD, cały build APK/EXE, prawdziwy WebView/Android/Windows | historyczny stan 1.2.17 | **NOT_RUN** | BLOKADA |

**Uwaga:** w tym kroku wykonano rozszerzone testy lokalne i kontrolę kodu oraz odtworzono deterministyczne pakowanie zmienionego runtime. Nie wolno zamieniać historycznego PASS z 1.2.17 na PASS nowego commita P0.

## 4. Kod CLEAN / kontrola kolizji po

- Zmienione **tylko 2 pliki źródłowego JavaScript aplikacji**; ponadto **obowiązkowe metadane pakowania**: `runtime_source/zip_manifest.json`, stała `RUNTIME_SHA` w `tools/build_runtime_from_sources.py`, 1 test i 2 jednolinijkowe zmiany CI. Żadnych nowych endpointów, parserów, schematów SQLite, UID, analityki, UI/CSS, migracji ani zmian klasyfikatora.
- Nie dodano nowego wrappera; istniejący recovery jest tym samym właścicielem kontroli rozmiaru, główna logika budowania pakietu pozostaje w `app.js`.
- T01 potwierdza jednokrotne `getFile`, przekazanie dokładnie 1 pakietu, brak zapisów przy anulowaniu.
- **Nie twierdzimy**, że absolutnie wszystkie wyścigi w module importu zniknęły; nie zmieniano architektury anulowania poza poprawką duplikacji.
- Historyczne gałęzie, pliki `OLD`/stage i prywatna baza nietknięte. Pin `ENGINE_SHA` klasyfikatora oraz wszystkie 64 pozostałe pliki runtime **bez zmian**.

## 5. CI i zasada NO-GO

[Ostatnia próba uruchomienia Actions dla gałęzi P0](https://github.com/adriandziura0-rgb/sora/actions/runs/39036028710) ma status **`startup_failure`, zero wykonanych zadań** — to blokada uruchomienia CI, nie porażka testu T01 ani dowód poprawności. Również wcześniejsze automatyczne uruchomienia gałęzi zakończyły się `startup_failure`.

**Konieczne przed wydaniem APK/EXE:** sprawny CI (Android i Windows na tym samym SHA), `node tools/test_t01_folder_scan.mjs` i `node tools/test_import_recovery.mjs`, pełne regresje, testy zachowania UI na rzeczywistym telefonie/Windows oraz audyt po. Do tego czasu **NO-GO RELEASE**. Nie trzeba ponawiać statycznego T01 i audytu początku bez nowej zmiany kodu.

## 6. Następny jeden krok

**Zweryfikować przyczynę GitHub Actions `startup_failure` (brak jobs) i doprowadzić do rzeczywistego uruchomienia testów na gałęzi P0** — bez wymyślania kolejnych napraw kodu i bez dotykania działających artefaktów 1.2.17. Po zielonym CI: audyt końcowy P0, test E2E na urządzeniu, decyzja o wydaniu lub rollback. Następny niezależny problem P1 cytatów A→B→A jest już odtworzony, ale celowo nie mieszano go z P0.


## 7. Obowiązkowy audyt pakowania deterministycznego — po modyfikacji UI

**Odkryta blokada przed wydaniem:** sam dwupunktowy fix JS naruszał dotychczasowy `runtime_source/zip_manifest.json` i `tools/build_runtime_from_sources.py:RUNTIME_SHA`. Kanoniczny builder **musi** przerwać pracę przy każdym niezatwierdzonym bajcie w źródłach, a ZIP ma być bitowo identyczny z wcześniej sprawdzonym SHA. Dlatego uzupełnienie tych dwóch plików jest warunkiem budowy, nie „kolejną łatką”.

**Rozpoznanie i wyliczenie:**
- Oryginalny runtime ZIP wydobyty z APK 1.2.17: SHA-256 `a6f013effc57555009f13dc3ef63d6fdba2b0ca0a65b968c4a821f9b2b6ed2b2`.
- Odwzorowano dokładnie algorytm `tools/build_runtime_from_sources.py`: 66 rekordów, te same nazwy, kolejność i metadane ZipInfo, kompresja i zawartość. Ponowne złożenie 66 **oryginalnych** plików dało **identyczny bajtowo ZIP** (`original_rebuild == original=True`). Dzięki temu porównanie dla poprawki ma sens.
- Dwa zmienione pliki JS otrzymały SHA-256: `static/app.js` `59f6c8f7dc61c5b2adf06ebc399ebdab32be2d0c4111c964519ae64a66ee0140`, `static/import-recovery.js` `17acf3322dec1e2f65308a123ada16521e78c2e77dc6da67a4cecd20feeb8dbe`.
- **Nowy ZIP P0** z dokładnie tymi samymi 64 pozostałymi plikami i z zachowaniem całej struktury: SHA-256 `daa8ed53b0d77e4af449539b0f3f0fd4b09c306d34d3cf2c0da58f0b113c85df`. Drugi niezależny przebieg składania według manifestu dał **bajtowo identyczny ZIP**; SHA manifestu GitHub zgadza się z niezależnie zrekonstruowaną wersją `15803847e424fe4c346f21a388290055fca79329`.
- [`runtime_source/zip_manifest.json`](../runtime_source/zip_manifest.json) ma **tylko trzy zmiany SHA**: dwóch źródeł JS i całej paczki runtime. [`tools/build_runtime_from_sources.py`](../tools/build_runtime_from_sources.py) aktualizuje wyłącznie `RUNTIME_SHA`.
- **`ENGINE_SHA=acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e` POZOSTAJE NIEZMIENIONY.** Identyfikator silnika obejmuje `app.py`, `clean_core/`, `knowledge/` i `benchmark/`, nie pliki `static/`; wszystko z tego zakresu jest bajtowo nietknięte.
- Nowy SHA ZIP oznacza zmianę zasobu aplikacji; [`ProjectStore.java`](https://github.com/adriandziura0-rgb/sora/blob/67f48a45a79c30e8e22e8a3cb6c2426685566b42/app/src/main/java/pl/drogowskazy/sora/ProjectStore.java) identyfikuje instalację po wersji pakietu **oraz hash asset ZIP**, więc nie wymaga w tym P0 zmiany schematu danych.
- **Wykonano lokalny odpowiednik algorytmu deterministycznego pakowania, ale NIE uruchomiono prawdziwego `tools/build_runtime_from_sources.py` w GitHub Actions**. To nadal BLOCKED przez `startup_failure`. Nie nadawać statusu PASS dla pełnego workflow/buildu.

**Konkluzja:** w drzewie Git gałęzi P0 działa spójny kontrakt pakowania i nie naruszono zamrożonego silnika. Następny test CI ma zbudować runtime według nowego SHA, uruchomić regresje, a dopiero potem można generować APK/EXE. Żadnego ręcznego nadpisywania runtime ZIP w instalacji użytkownika.
