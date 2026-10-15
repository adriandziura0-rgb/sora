# SORA — audyt drzewa GitHub i regresji (15.10.2026)

## Zakres i sposób sprawdzania
Repozytorium: https://github.com/adriandziura0-rgb/sora. Odczytano referencje Git, porównania commitów, pełne drzewa plików (bez ucięcia), dwa workflow GitHub Actions oraz szczegółowe logi Android/Windows. **Stan gałęzi poniżej jest migawką**, nie automatycznie aktualizowaną listą. Nie otwierano prywatnej bazy użytkownika, niczego nie usuwano ani nie przesuwano do `main`.

## Trzy punkty odniesienia
| Rola | Gałąź | Commit | Testy / decyzja |
|---|---|---|---|
| Domyślna, historyczna | `main` | `5cd9516e5741` | Kod 1.2.5; NIE jest najnowszym instalatorem |
| Ostatnie potwierdzone CLEAN | `sora-full-clean-stage4-20261015` | `2f4f1b9037d2` | Android SUCCESS #38689333134 i Windows SUCCESS #38689333054; punkt powrotu 1.2.14 |
| Kandydat po poprawce A2 | `sora-full-a2-audyt-regresji-20261015` | `049bdf9c7462` | Android SUCCESS #38760801803, Windows SUCCESS #38760801786, to samo SHA; PR #4 oczekuje na scalanie |

**Nie mieszać artefaktów różnych commitów**: Windows z A2 nie może zostać opisany jako para z Androidem CLEAN lub poprzednim błędnym A2.

## Inwentaryzacja istniejących 17 gałęzi
| Gałąź | Status porządkowy | Co z nią zrobić |
|---|---|---|
| `main` | domyślna / starsza 1.2.5 | zachować, przygotować kontrolowaną aktualizację osobnym PR |
| `sora-full-clean-stage4-20261015` | **CLEAN 1.2.14**, referencyjna | ZACHOWAĆ |
| `sora-analizy-a1-spojne-wyniki-20261015` | ten sam SHA co CLEAN etap 4 | pozostawić jako alias historyczny; nie rozwijać równolegle |
| `sora-full-analizy-a1-20261015` | 1.2.15 A1, przetestowana | zachować jako odtwarzalny etap |
| `sora-full-analizy-a2-20261015` | 1.2.16 A2 przed poprawką | NIE publikować jako zielonego Androida; błąd testu |
| `sora-full-a2-audyt-regresji-20261015` | A2 po poprawce; PR #4 | kandydat do dalszych prac, dopiero po przeglądzie PR |
| `sora-full-clean-stage1-20261014` | historia CLEAN 1 | archiwum historii, bez nowych buildów |
| `sora-full-clean-stage2-20261015` | historia CLEAN 2 | archiwum historii |
| `sora-full-clean-stage3-20261015` | historia CLEAN 3 / źródła kanoniczne | zachować do audytu pochodzenia runtime |
| `audit-sora-clean-20261014` | osobny audyt poprzedniego stanu | zachować, nie traktować jak instalatora |
| `audit-sora-analizy-4-tryby-20261015` | wyłącznie dokument audytu 4 trybów | zachować jako dokumentację |
| `sora-full-database-dashboard-20261010` | historyczny przodek CLEAN 4, PR #3 nadal otwarty | nie scalać automatycznie; ocenić PR #3 podczas aktualizacji main |
| `desktop-native-20261007` | historyczne prace Windows/TRANSFER | zachować historię, bez równoległego wydania |
| `desktop-native-transfer-20261008` | dokładnie ten sam SHA co `desktop-native-20261007` | alias historyczny; nie rozwijać |
| `desktop-native-sora-engine-cache-20261009` | historia optymalizacji, PR #2 scalony | zachować dla porównań |
| `native-v1-m1` | odrębny eksperyment/prototyp | nie używać do buildów CLEAN |
| `sora-pdf-diagnostics` | historyczna diagnostyka PDF | nie używać do buildów CLEAN |

Nowa gałąź dokumentacyjna `audit-sora-porzadki-20261015` została utworzona **po** tej migawce, dlatego zwiększa licznik gałęzi; nie należy jej mylić z kodem produkcyjnym.

## Potwierdzony problem i naprawa
Przed poprawką na A2 1.2.16: build APK i weryfikacja podpisu były zielone, ale test pełnego Android WebView przerwał się z `ReferenceError: persisted is not defined`. Zmienna `persisted` była dostępna w Node.js, nie w kontekście WebView wykonywanym przez `page.waitForFunction`. W PR #4 przekazano jawnie `persisted.id` do predykatu. Zmiana tylko w `tools/test_android.mjs`; żadnych zmian w klasyfikatorze, `runtime_source/` ani SQLite.

Przed: https://github.com/adriandziura0-rgb/sora/actions/runs/38751326243 (FAILURE).
Po: https://github.com/adriandziura0-rgb/sora/actions/runs/38760801803 (SUCCESS Android).
Po: https://github.com/adriandziura0-rgb/sora/actions/runs/38760801786 (SUCCESS Windows).
PR: https://github.com/adriandziura0-rgb/sora/pull/4 .

Log Android po poprawce: **257/257 GOLD**, 16 scenariuszy integracyjnych, 110 przycisków panelu objętych audytem, import SQLite, aktualizacja/odzyskiwanie, poprawny eksport artykułu A2, wybór grup 1–2, porównanie wspólnej sprawy, PDF i transfer PHONE–PC. To nie jest gwarancja braku błędów w każdym prawdziwym materiale.

## Czystość kodu: konkretna kontrola
- `main`: 35 plików Git (bloby), zawiera stary `app/src/main/assets/drogowskazy-runtime.zip` i `tools/patch_engine_runtime.py`; **nie kopiować ich do CLEAN**.
- CLEAN 1.2.14: 119 plików Git; poprawiona linia A2: 123. W zbadanych pełnych drzewach obu tych wersji brak par plików o dokładnie takim samym SHA Git.
- CLEAN etap 2 wycofał nieaktywne hosty Tkinter/Qt/pywebview i stare budownicze. Czynny host to C# WinForms WebView2 + backend; `desktop/report_projection.py` zachowuje potrzebne funkcje raportowe.
- CLEAN etap 3 ma kanoniczny kod w `runtime_source/`: 66 źródłowych zasobów runtime + manifest. Usunął patchery, dawne kopie `tools/overview_assets/` i śledzony gotowy ZIP. Obie platformy składają ZIP w CI na podstawie hashy.
- `gold_current_cases.json`, `gold_benchmark.py`, `effectiveness_gold.py` to **testy GOLD**, a nie przypadkowe katalogi `old`. Nie kasować ich.
- Brak identycznych SHA wyklucza tylko duplikaty bajt-w-bajt w konkretnych drzewach; **nie wyklucza** podobnych funkcji o różnej implementacji.
- Brak baz `.sqlite3` w ostatnim drzewie Git **nie dowodzi** stanu danych w instalacji użytkownika; te dane muszą pozostać prywatne.

## Otwarte sprawy i ryzyka
1. `main` nadal 1.2.5: opis wydania i najnowsza gałąź to różne rzeczy. Wymagany osobny proces promocji CLEAN/A1/A2.
2. PR #3 jest otwarty pomimo tego, że jego gałąź jest przodkiem CLEAN 4. Nie scalać starego kodu ponad aktualną wersją; PR można zamknąć jako zastąpiony **dopiero po** ustaleniu docelowego wydania i sposobu aktualizacji `main`.
3. Nie ma oficjalnego tagu lub GitHub Release 1.2.14/1.2.16; zielony artifact Actions nie jest automatycznie opublikowanym wydaniem.
4. Dokumentacyjne aliasy i stare eksperymenty wydłużają listę; nie usuwamy ich bez osobnej decyzji i zabezpieczonej referencji Git.
5. Sprawdzać rzeczywisty ekran na telefonie i PC z prawdziwymi danymi (jednego artykułu, 1 folderu, 2 folderów i tej samej sprawy). Test syntetyczny nie zastępuje akceptacji użytkownika.

## Bramka wydania
Wymagane: dwa buildy Android/Windows **SUCCESS z tego samego SHA**, zgodny certyfikat aktualizacji APK i rosnący `versionCode`, kontrola manifestu runtime i identyfikatora silnika, 257/257 GOLD, SAF/SD, eksporterzy JSON/MD/PDF, kolejka i wznowienie, TRANSFER import/eksport i deduplikacja, test SQLite/WAL/SHM, brak nadpisywania nowszych danych starszymi i zero niezamówionej analizy całej bazy. Po zaliczeniu: osobny tag/release, jego artefakty i jawna gałąź źródłowa. W razie awarii — powrót do sprawdzonego CLEAN 1.2.14 i zachowanie danych.

**W tym audycie nie wykonano:** usunięcia gałęzi, scalania PR, przepisywania historii, zmiany silnika, czyszczenia prywatnych baz ani publikacji Release.
