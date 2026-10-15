# SORA CLEAN — etap 2: wycofanie martwych implementacji Windows

**Baza:** commit `a9cc297a044094a6619ba139d0eb4eda7b5058db` — wersja Android 1.2.13, oba buildy SUCCESS.
**Zakres:** wyłącznie źródła repozytorium i statyczny test zależności.

## Potwierdzone stare gałęzie aplikacji (usunięte z tej gałęzi)

- `desktop/sora_pc.py`: dawne okno Tkinter.
- `desktop/operations.py`: widgety i obsługa plików dla Tkinter.
- `desktop/gui_test.py`: test historycznego okna Tkinter.
- `desktop/build_windows.py`: nieaktywny build Python/Qt/pywebview.
- `desktop/sora_pc_webview.py`: nieaktywny host pywebview.
- `desktop/test_qt_unfrozen.py`: diagnostyka dawnego Qt.
- `desktop/test_phone_ui.py`: test związany z nieaktywnym hostem.

## Moduł odzyskany, NIE usunięty

`desktop/presentation.py` był importowany przez aktywny `desktop/test_engine.py`.
Treść pliku zachowano bez zmian w `desktop/report_projection.py`; jedyny
import testu został odpowiednio poprawiony. Nie należy usuwać funkcji
`materialize`, `readable_report`, `evidence_range` i `write_pdf`.

## Zabezpieczenia

- `tools/test_native_clean.py` działa w obu workflow i wykrywa powrót
  historycznych plików, importy starych modułów, brak aktywnych plików C#
  i brak testów bezpieczeństwa oraz parytetu kodu.
- `desktop/test_local_session.py` dołączony do testów Windows: ochrona
  lokalnego API, tokenu sesji i sprawdzenie nagłówka Origin.
- Uzupełnione `.gitignore`: bazy, WAL, SHM, klucze APK, logi, buildy,
  APK i tymczasowe pliki nie powinny trafić do repozytorium.

## Co celowo pozostaje

- `desktop/build_native_windows.py`, `desktop/engine.py`, `desktop/sora_backend.py`,
  `desktop/native/**`, `desktop/windows_adapter.js`, `desktop/local_session.py`.
- Zamrożony ZIP CORE, wszystkie moduły analizy, baza SQLite, WAL, SHM,
  eksport TRANSFER, build APK oraz Python testów jednostkowych.
- Skrypty patchujące runtime — będą uporządkowane w **etapie 3**.

## Kryterium zaliczenia

Na **jednym commicie**: Android APK SUCCESS, Windows EXE SUCCESS, parytet
PHONE ↔ PC, 257/257 GOLD, regresja SQLite i transferu, testy okna WebView2
na Windows i prawdziwego WebView/SAF na emulatorze Androida.
Bez tych wyników nie scalać do głównej gałęzi.
