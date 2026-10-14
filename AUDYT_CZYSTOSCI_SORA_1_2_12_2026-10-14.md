# SORA 1.2.12 — audyt czystości kodu (14.10.2026)

## Zakres i stan bazowy
- Repozytorium: `adriandziura0-rgb/sora`.
- Audytowany HEAD: `acac7c0cedaa677e7d9bb1da27570870eccb6405`, gałąź `sora-full-database-dashboard-20261010`.
- `main`: `5cd9516e57416a42536b37bbf84b7be4bd09902f`, rozwój 188 commitów do przodu (0 do tyłu).
- Ostatnie testy tego HEAD: Android run `38554425716` — SUCCESS, Windows run `38554425809` — SUCCESS.
- Sprawdzono listę plików GitHub, aktywne workflow, skrypty publikacji, `ProjectStore.java`, kod Tk/Qt/WebView2, strukturę finalnego APK i ZIP Windows, oraz źródła runtime'u wbudowane w rzeczywisty APK.
- Nie usunięto żadnego pliku projektu, danych, SQLite, WAL ani SHM. Niniejsza gałąź zawiera jedynie audyt.

## Werdykt
**Nie jest to jeszcze repozytorium CLEAN.** Działające pakiety są względnie czyste, lecz źródła mają historyczne implementacje PC, dwustopniowy system łatek modyfikujących ZIP na etapie budowy, duplikację narzędzi UI i niepełny porządek wersji/CI. Nie należy usuwać plików bez identyfikacji aktywnego grafu zależności i zielonych testów.

## P0 — krytyczne do naprawy przed kolejnymi wydaniami

1. **Aktualizowanie APK bez zmiany wersji może zostawić stary kod interfejsu.** `app/src/main/java/pl/drogowskazy/sora/ProjectStore.java`, metoda `bundledVersion()`, zwraca wyłącznie `apk-runtime-` + `packageInfo.versionName`; `needsBundledInstall()` porównuje jedynie tę wartość. Wszystkie ostatnie modyfikacje są nadal oznaczone `versionName '1.2.12'`, `versionCode 15` w `app/build.gradle`. Wynik: przy instalacji kolejnego APK 1.2.12 pliki nowego WebView mogą nie zostać wypakowane. **Naprawa:** identyfikator oparty również na sumie SHA-256 zasobu `drogowskazy-runtime.zip` (z kontrolą aktualizacji), a przy właściwym wydaniu zwiększać wersję Androida. Wymagane testy: aktualizacja **z inną zawartością, ale identycznym numerem APK**, zachowanie SQLite + WAL/SHM, przerwanie aktualizacji, rollback.
2. **Brak automatycznej przebudowy Windows przy samej zmianie wbudowanego silnika.** `.github/workflows/build-windows.yml` używa `push.paths` ograniczonego do `desktop/**`, `app/src/main/python/data_transfer.py`, `tools/**` i samego workflow. Brakuje `app/src/main/assets/drogowskazy-runtime.zip`. Dodanie tej ścieżki zapobiega przypadkowemu rozjazdowi PHONE ↔ PC.
3. **Niedomknięte zasady tożsamości wydania.** Wiele różnych commitów daje instalator o tym samym `1.2.12`; wymagany weryfikowalny `build_id`, hash runtime'u, hash UI i numer APK. Testy muszą rozpoznawać dokładnie uruchomioną paczkę, nie tylko `versionName`.

## P1 — nadmiarowy/stary kod źródłowy PC (kandydaci, NIE kasować bez testu)
Obecny CI uruchamia wyłącznie `desktop/build_native_windows.py`, `desktop/sora_backend.py`, `desktop/engine.py`, `desktop/native/Program.cs`, `desktop/windows_adapter.js` i zależne pliki. Historyczne ścieżki do wycofania po potwierdzeniu braku importów:
- `desktop/sora_pc.py` — stare główne okno Tkinter.
- `desktop/operations.py` — operacje zależne od Tkinter.
- `desktop/presentation.py` — dawny moduł prezentacji dla Tk/GUI testu.
- `desktop/gui_test.py` — test starego okna Tkinter.
- `desktop/build_windows.py` — alternatywna ścieżka PyInstaller + pywebview / zależności Qt; NIE jest aktualnym buildem natywnym.
- `desktop/sora_pc_webview.py` — historyczny host pywebview, inny niż obecny C# WebView2.
- `desktop/test_qt_unfrozen.py` — diagnostyka QtWebEngine.
- `desktop/test_phone_ui.py` — test historycznego hosta `sora_pc_webview.py`.

**Nie usuwać** `desktop/local_session.py` (chroni lokalne API), `desktop/test_local_session.py` (warto podłączyć do CI), `desktop/windows_adapter.js` (używany przez natywny host), `desktop/engine.py`, `desktop/sora_backend.py`, `desktop/build_native_windows.py`, `desktop/native/**`.

## P1 — łaty w trakcie builda (źródło długu technicznego)
- `tools/patch_engine_runtime.py` modyfikuje `clean_core/topic_matcher.py` wewnątrz `app/src/main/assets/drogowskazy-runtime.zip`, przed zbudowaniem APK/EXE.
- `tools/patch_full_database_dashboard.py` ponownie modyfikuje ZIP, w tym `app.py`, `static/app.js`, `templates/index.html` i dodaje pliki z `tools/overview_assets/**`.
- Zależność obu workflow od sekwencji patchowania jest krytyczna. Nie jest to duplikacja plików ZIP w finalnym APK, ale **dwa poziomy kodu**: zapisany bazowy ZIP i ten rzeczywiście uruchamiany w aplikacjach.
- **Docelowo:** zamienić wbudowany ZIP w wynik deterministycznego procesu budowy z jawnego katalogu utrzymywanych źródeł, przenieść zastosowane poprawki do docelowych plików źródłowych, dodać porównanie hashów i testy równoważności. Dopiero po akceptacji porównań usunąć skrypty patchujące.
- Nie wykonywać jednorazowo zmian w parserze, klasyfikatorze, importach i migracjach. CORE pozostawić FROZEN do osobnego audytu.

## P1 — wspólne fragmenty UI, do scalania BEZ zmiany zachowania
- `static/app.js`, `static/full-database.js`, `static/shared-content.js`, `static/same-story-mobile.js` obsługują odrębne, ale częściowo powtarzające się stany zaznaczonych grup, odświeżanie i eksport.
- Export `pobierzPlik` jest już w `static/app.js`; nowsze moduły mają własne pomocnicze funkcje pobierania i podobne przyciski HTML/JSON. Wspólne funkcje powinny stać się jedną biblioteką UI ze stabilnym kontraktem Android/Windows.
- `static/full-database.js` synchronizuje checkboxy przez kilka `MutationObserver`; istnieje ryzyko stanów niespójnych przy wznowieniu po restarcie. Zastąpić je jednym zdarzeniem wyboru zakresu tam, gdzie jest to bezpieczne.
- Oryginalne tabele i metryki P0–P5 muszą pozostać widoczne i porównywalne. Żadnego usuwania analiz tylko dlatego, że nowa karta ma mniej pól.

## P2 — higiena wydania i repozytorium
- `README.md` nadal zaczyna się od wersji **1.2.9**, choć `VERSION.txt` i `app/build.gradle` deklarują **1.2.12**. Należy wydzielić bieżący opis produktu od historii zmian.
- `desktop/README.md` ma dwa punkty „5.”. Drobne, ale potwierdza dokumentacyjny dryf.
- Gotowy ZIP Windows zawiera m.in. `Sora.pdb`, 3 pliki `Microsoft.Web.WebView2.*.xml` (dokumentacja API), `PODGLAD_PRAWDZIWEGO_OKNA.png` i `TEST_OK_PRAWDZIWE_OKNO.json`. Zostawić EXE i wymagane biblioteki, a symbole/testy przenieść do osobnego artefaktu diagnostycznego. Nie usuwać DLL ani folderu `_engine`!
- `.gitignore` nie obejmuje `dist/`, `*.sqlite3`, `*.sqlite3-wal`, `*.sqlite3-shm`, `*.apk`, `*.keystore`, `.venv/`, `__pycache__/`. Obecny Git tree nie zawiera kopii prywatnych baz, ale zabezpieczenie przed przypadkowym commitowaniem jest zbyt słabe.
- Historyczna gałąź `main` ma wersję 1.2.5, a rozwój 1.2.12 jest 188 commitów do przodu; nie scalać bez podpisanych testów i jawnego planu wydania.
- `desktop/test_local_session.py` testuje ochronę sesji HTTP i Origin, lecz nie jest wywoływany w aktualnym workflow Windows. Podłączyć do CI.

## Co zostało zweryfikowane pozytywnie
- Finalny APK: 37 wpisów ZIP, bez powtarzających się ścieżek; zawarty runtime: **66 wpisów, bez duplikatów ZIP**.
- W rozpakowanym runtime: nie znaleziono plików `.bak`, `OLD` ani zdublowanych globalnych definicji funkcji i klas Python.
- Finalny ZIP Windows: 470 wpisów, bez podwójnych nazw archiwum; prawdziwe `Sora.exe` i `_engine/SoraSilnik/SoraSilnik.exe`.
- Potwierdzono identyczny kanoniczny hash silnika APK i metadanych EXE:
  `acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e`.
- Automatyczne testy audytowanego commitu zaliczyły Android i Windows. **Nie zastępuje to testu na rzeczywistym telefonie i PC**.

## Kolejność bezpiecznych etapów CLEAN

1. **P0: aktualizacja i identyfikacja paczki (odrębna gałąź):** hash zasobu zamiast samej wersji, jednoznaczny build ID, test aktualizacji bez utraty danych; równocześnie naprawa workflow Windows dla zmian w assets.
2. **P1: repozytorium i stare źródła:** zebrać graf importów i przetestować natywną ścieżkę; usunąć potwierdzone martwe entrypointy PC z nowej gałęzi, zachowując ich dostępność w historii Git (nie w aplikacji).
3. **P1: konsolidacja łatek:** jeden katalog kanonicznego kodu + deterministyczna budowa runtime ZIP; porównania hashów, 257/257 GOLD, transfer PHONE ↔ PC, brak zmian schematu lub wyniku klasyfikatora.
4. **P1/P2: konsolidacja UI i wydanie CLEAN:** wspólne narzędzia zakresu i eksportu, polskie etykiety, czytelność mobilna i wszystkie metryki; rozdzielić symbole/debug od użytkowego EXE.
5. **Regresja końcowa:** testy aktualizacji telefonu (w tym identyczne `versionName` i nowa zawartość), import/eksport, utrata połączenia, ekran wyłączony, Android SAF/SD, spójność SQLite/WAL, 257 GOLD, otwieranie natywnego Windows, watchdog, raporty, PDF, HTML/JSON, cytaty, porównanie jednej sprawy, zgodność TRANSFER, test świeżo rozpakowanego EXE. Dopiero wtedy scalić wydanie.

## Zasady nienaruszalne
- Nie usuwać ani nie wymieniać użytkownikowi bazy `drogowskazy.sqlite3` na żywo.
- Nie usuwać danych, archiwalnych analiz, anotacji GOLD, plików TRANSFER, WAL i SHM.
- Silnik/classifier i schema SQLite pozostają FROZEN. Każda ich zmiana wymaga niezależnego audytu.
- Stare pliki źródłowe usuwać z bieżącej gałęzi dopiero po wykazaniu braku zależności; w Git historycznie pozostają dostępne.
- Bez zielonego Android i Windows na **tym samym commit SHA** nie oznaczać wydania jako CLEAN.
