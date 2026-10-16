# SORA — zasady pracy: najpierw AUDYT, potem ZMIANA, TESTY i ponowny AUDYT

**Ustalono:** 16.10.2026. **Dotyczy:** SORA Android/PHONE, Windows/PC WebView2, runtime, JS/HTML/CSS, API, importu, SQLite, eksportów, porównań, dodatków, CI i TRANSFER.  
**Punkt odniesienia:** SORA 1.2.17, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`. `main` nie jest bazą najnowszego wydania.  
**Status:** stały regulamin kolejnych prac; NIE jest dowodem, że opisane naprawy zostały wdrożone. Dokument nie zmienia działającego kodu ani danych.

## ZASADA NACZELNA: AUDYT → decyzja → działanie → testy → audyt końcowy

1. **AUDYT WSTĘPNY — BEZ ZMIAN**: zidentyfikuj dokładną gałąź/commit, istniejące zachowanie, źródła danych, architekturę, problem, zakres wpływu na PHONE i PC. Przeczytaj faktyczny kod, historię, zależności, testy i logi; nie opieraj się na samym opisie lub zielonym badge.
2. **MAPA DAWCA → ODBIORCA**: dla każdej ścieżki przepływu opisz producenta danych, odbiorcę, ich kontrakt, właściciela, status oraz możliwe kolizje. Sprawdź, czy istnieje już implementacja, aby nie tworzyć drugiej.
3. **AUDYT CZYSTOŚCI / REGRESJI**: zidentyfikuj duplikaty, OLD, martwe gałęzie, monkey-patche, event listenery, niezależne liczniki, skanowania i miejsca nadpisywania. Rozdziel problem potwierdzony od ryzyka i hipotezy. Wskaż dowód (plik, zakres linii, test odtwarzający).
4. **RAPORT PRZED ZMIANĄ**: co działa; co nie działa; co chronimy; minimalny zakres naprawy; ryzyko; koszt; plan testów; punkt powrotu. Nie nazywaj hipotezy błędem potwierdzonym.
5. **DOPIERO POTEM DZIAŁANIE**: wykonuj najmniejszą odizolowaną poprawkę w źródle kanonicznym i na osobnej gałęzi. Nie ruszaj silnika ani bazy bez osobnego uzasadnienia i zgody użytkownika. W razie niejasnego kontraktu — STOP i doprecyzuj.
6. **TESTY PO ZMIANIE**: test reprodukcji starego błędu, test negatywny, test współbieżności, pełne regresje, PHONE oraz PC na tym samym SHA, integralność transferu i brak wpływu na dane.
7. **AUDYT KOŃCOWY + PORZĄDKI**: porównaj przed/po; potwierdź, że stary kod nie wykonuje się równolegle, że nie ma nowych dubli/kolizji i że żadna funkcja nie zniknęła; podaj diff, commit, wyniki, ograniczenia i rollback.

**Brak mapy dawca–odbiorca albo audytu czystości BLOKUJE wdrożenie.** Same zielone buildy nie zamykają audytu funkcjonalnego.

## Obowiązkowa karta KAŻDEGO przepływu: dawca → odbiorca

Dla zmienianej funkcji utwórz kartę (osobno dla każdego istotnego przekazania danych):

| Pole kontrolne | Co trzeba jawnie zapisać / sprawdzić |
|---|---|
| Dawca | Plik, funkcja, proces, urządzenie, endpoint lub tabela, która produkuje dane; czy to źródło prawdy czy cache |
| Odbiorca | Plik, funkcja, endpoint, UI, baza lub eksport; kto zapisuje, kto tylko czyta |
| Właściciel kontraktu | Jedna kanoniczna implementacja; brak konkurencyjnego wrappera/listenera/renderer-a |
| Dane/typ/schemat | Nazwy pól, typy, jednostki, wymagane/opcjonalne, wersja, kodowanie; kompatybilność PHONE i PC |
| Identyfikacja | `document_id`, `analysis_run_id`, hash treści, ID relacji/cytatu, ID grupy/tematu; zasada deduplikacji |
| Zakres i czas | `mode`, `groups`, `topic_id`, wybrany dokument, `revision`, `request_id`, `updated_at`; timestamp po stronie właściwego źródła |
| Zanik/pustka | Brak pola ≠ `null` ≠ 0 ≠ stara wartość; brak redakcji, brak daty, brak cytatu i limit podglądu są wyraźne |
| Kolejność i współbieżność | Jedno/dwa zapytania? retry, anulowanie, A→B→A, restart, offline, timeout, odpowiedź spóźniona, dwa urządzenia |
| Odczyt/zapis/odpowiedzialność | Czy odbiorca ma prawo modyfikować dane? transakcja, WAL/SHM, backup, rollback, idempotencja |
| Ślad i test | Jak odtworzyć z danych wejściowych rezultat końcowy; test zgodności UI/JSON/HTML/PDF/SQLite i błąd kontrolowany |

**Przykładowe obowiązkowe łańcuchy kontroli (aktualizować po audycie kodu):**

- Android SAF / Windows picker → import JS / most natywny → parser → kolejka → SQLite; odróżnij *dodanie do bazy* od *analizy bieżącej*.
- Zaznaczenie folderów/redakcji i sprawy → API porównań → zapisane analizy SQLite → karty Android/tabele PC → HTML/JSON/PDF.
- Zapisany pojedynczy artykuł w SQLite → GET wyniku po ID → karta dowodów → eksport bez ukrytego POST/przeliczenia.
- Zapisane cytaty i relacje → endpoint cytatów → filtr grupy i rewizja wyboru → ekran/eksport; brak przenikania danych z innego zakresu.
- Runtime/manifest SHA → składanie APK i EXE → aktualizacja instalacji → zachowanie prywatnej bazy/WAL/SHM.
- PHONE baza lokalna → kontrolowany ZIP TRANSFER (manifest/suma/schema) → PC importer i odwrotnie; deduplikacja, mapowanie ID i zachowanie nowszych rekordów.

Każdy raport zmian ma podać liczbę zidentyfikowanych par **dawca–odbiorca**, par sprawdzonych, błędów, kolizji i par nadal niezweryfikowanych. Nie podawaj „0 kolizji”, jeżeli czegoś nie sprawdzono.

## Reguły czystości kodu — obowiązkowy AUDYT przed każdą poprawką

- **Jedno źródło prawdy i jeden właściciel funkcji.** Produkcyjny runtime wyłącznie w `runtime_source/`; nie przywracaj starych patcherów ani śledzonego gotowego ZIP. Jeden model wyniku może mieć kilka widoków.
- **Bez nowych łatek na łatkach.** Zakaz nowego monkey-patch, globalnego nadpisania funkcji, `old/fix2/final2`, niejawnego drugiego kontrolera, drugiego skanera, drugiej ścieżki zapisu czy drugiego liczenia metryk.
- **Czystość to nie automatyczne kasowanie.** Skanuj martwe importy, OLD, nieużywane entrypointy, zaległe migracje, duplikaty bajt-w-bajt (SHA) i logiczne (różny kod, ta sama rola), pliki wygenerowane/testowe w paczce, nieużywane helpery oraz podobne nazwy funkcji. Dla każdego kandydata: graf wywołań, użytkownicy, wartość historyczna, test przed/po. Zachowaj historię Git; nie usuwaj GOLD, kopii danych i archiwów użytkownika.
- **Żadnego cichego powrotu starej implementacji.** Po zastąpieniu fragmentu sprawdź wszystkie importy, zdarzenia, referencje i buildy; stary kod albo zostaje jawnie potrzebny, albo jest usunięty bez równoległego działania (z historią Git).
- **Sprawdź wielokrotne wykonania.** Nasłuchiwanie `addEventListener`, `MutationObserver`, `setInterval`, callbacki i wrappery analizuj pod kątem montażu/odmontowania i dublowania operacji; jeden folder nie powinien być skanowany dwukrotnie bez uzasadnienia.
- **Ogranicz małe zmiany.** Jeden cel na commit/PR, najmniejszy diff, test negatywny i przywrócenie; bez refaktoryzacji classifiera/SQLite równolegle z wyglądem UI.
- **Sprawdź kontrakty platform.** Nazwy API, liczniki, ścieżki, błędy, zapisy i struktura danych mają być zgodne Android/Windows; wszystkie komunikaty użytkownika po polsku.
- **Czysta paczka wydania.** Bez debug/test/dump/PDB/OLD w paczce użytkowej; diagnostyka osobno. Jeden SHA, identyczny runtime, prawidłowa wersja, podpis APK i instalacja aktualizacyjna.
- **Prawda o danych.** Brak danych/niepewny wynik nie może być zastąpiony zerem lub sugestią pewności. Wskaż X z Y, limity i pochodzenie każdej metryki.

## Ochrona bazy i CORE — bez wyjątków milczących

`classifier`, parsery semantyczne, schemat SQLite oraz kontrakt TRANSFER traktuj jako **FROZEN**. Nie zmieniaj bez osobnego audytu i jawnej zgody. Nie usuwaj projektów i baz, nie podmieniaj uruchomionej SQLite, nie kopiuj WAL/SHM „na żywo”. Eksport/import wyłącznie walidowany: kopia bezpieczeństwa, wersja schematu, hash, transakcja, idempotencja, wykrywanie kolizji ID, niepisanie starszymi rekordami po nowszych, rollback przy błędzie. Testy na kopii, nie na prywatnej aktywnej bazie.

## Obowiązkowa macierz kolizji i regresji

| ID | Scenariusz | Kryterium zaliczenia |
|---|---|---|
| K01 | Panel otwarty ponownie i przywrócona sesja | Brak podwójnych handlerów i eksportów |
| K02 | Cytaty: A→B→A podczas odpowiedzi API | Pierwsze A jest odrzucone, nie nadpisuje nowszego A |
| K03 | Porównanie 2 folderów, zmiana i 404/500 | Stary wynik i eksport unieważnione |
| K04 | Jedna sprawa, zmiana `topic_id` / redakcji | Wynik tylko dla bieżącej sprawy i pełnego zaznaczenia |
| K05 | Import folderu pod limitem, również podfoldery | Jeden skan bez podwójnego importu |
| K06 | Folder ponad limitem, Anuluj/Escape/restart | Brak zawieszenia i osieroconej operacji |
| K07 | Jednoczesny import, autosave, raport | Odbiorcy nie modyfikują cudzych danych |
| K08 | Dokument zmieniony po zapisaniu analizy | Eksport odmówiony albo zgodny z aktualnym run ID |
| K09 | 1 artykuł, 1/2 foldery, ta sama sprawa | Te same wartości, zakres, ID i pochodzenie w UI/API/raporcie |
| K10 | Telefon: ekran wyłączony, przerwa internetu, restart | Bezpieczne wznowienie bez duplikatów |
| K11 | TRANSFER w obie strony i aktualizacja | Brak utraty danych, duplikacji i downgrade'u |
| K12 | Start z nowego APK/ZIP | Poprawne SHA/wersje, bez przypadkowych artefaktów |
| K13 | Wszystkie regresje istniejące | GOLD 257/257; A1/A2; WebView/SAF; Windows WebView2 |
| K14 | Wygląd/etykiety/ID elementów | Brak zasłoniętych danych, duplikatów ID i błędów UX |
| D01 | Dawca znika/zmienia typ w trakcie pracy | Odbiorca nie pokazuje starej wartości jako świeżej |
| D02 | Zmieniony zakres podczas requestu i eksportu | Zakres, rewizja, ID dokumentu i dane muszą pasować |
| D03 | Pusta/null/zero/nieobecna zmienna | Rozróżniane konsekwentnie w API, UI, raporcie |
| D04 | Dwa źródła piszą ten sam rekord/ID | Zastosowana zdefiniowana reguła deduplikacji/konfliktu |
| D05 | Ten sam wynik w PC, telefonie i eksporcie | Parytet co do danych i pochodzenia, nie tylko podobny wygląd |
| C01 | Drzewo plików i graf importów przed/po | Zero nieautoryzowanych nowych OLD, dubli i martwych ścieżek |
| C02 | Wywołanie każdej operacji 2 razy | Brak duplikacji listenerów, kolejek, skanów, zapisów |
| C03 | Zmiana helpera/wrappera | Jedna aktywna implementacja, komplet testów w obu platformach |

## Kolejność etapów, bez omijania bramek

1. **ETAP AUDYT-0 (tylko odczyt):** pełna inwentaryzacja rzeczywistej gałęzi 1.2.17, mapy dawca–odbiorca, kolizje i czystość kodu; oznacz pewność ustaleń, wpisz ryzyka, pokaż plan napraw i testów. Dopiero wynik audytu zezwala przejść dalej.
2. **P0 — import/recovery:** test odtwarzający dwa skany i globalne nadpisania, jeden właściciel wyboru/skanowania, kontrola limitu i cancel; po poprawce powtórny audyt.
3. **P1 — cytaty i zmiany zakresu:** `AbortController` + monotoniczne `request_id` i rewizja; test A→B→A, spóźniona odpowiedź, 4xx/5xx; zachować A1.
4. **P1 — właściciel stanu i widoku:** jeden kontroler wyboru/model odpowiedzi; dodatki subskrybują, PC tabela i PHONE karty nie liczą osobno; regresje K01/K07/K09.
5. **P2 — CLEAN:** redukcja potwierdzonych duplikatów i martwych ścieżek dopiero po dowodach; żadne GOLD ani historyczne dane nie są kasowane; czysty build.
6. **A3:** pełny indeks 1 folderu i porównanie 2 folderów, paginacja, kompletne źródła, neutralne delty, ślad dowodowy i kontrola limitów.
7. **A4:** kompletne dokumenty i cytaty jednej sprawy, filtrowanie po temacie/redakcjach, odróżnianie dopasowania automatycznego od potwierdzenia, parytet eksportów.
8. **A5:** pełna bramka wydaniowa, test na kopii realnych danych, ta sama rewizja APK i EXE, potwierdzona aktualizacja bez usuwania aplikacji, kopia TRANSFER, opis rollback.

**Każdy etap ma oddzielny audyt przed, test w trakcie i audyt po; brak krytycznego testu = etap niezakończony.**

## Obowiązkowy szablon raportu przed/po

```text
REPO / GAŁĄŹ / COMMIT / WERSJA:
STATUS: DO AUDYTU | AUDYT POTWIERDZONY | PLAN | WDROŻONE BEZ TESTÓW | TESTY CZĘŚCIOWE | ANDROID+PC GREEN | RĘCZNIE POTWIERDZONE
CEL:
DAWCA → ODBIORCA: nazwy modułów, API/tabel/pól, typy, ID, zakres i prawa do zapisu
KONTRAKT: oczekiwane dane / puste / błędy / znikające zmienne / kolejność / wersja
AUDYT CZYSTOŚCI: duplikaty, OLD, martwy kod, monkey-patch, wywołania, artefakty
ZNALEZIONE KOLIZJE: potwierdzone / prawdopodobne / niezweryfikowane
CO DZIAŁA I CZEGO NIE WOLNO ZEPSUĆ:
DOWÓD BŁĘDU: plik:linia, test reprodukcji, log
PLAN POPRAWKI I ZAKRES DIFF:
TESTY: K01–K14, D01–D05, C01–C03, jednostkowe, E2E, SQLite, TRANSFER, GOLD, APK/EXE
WYNIKI: PASS/FAIL/NIE URUCHOMIONO i konkretne logi/run IDs
PORÓWNANIE PRZED → PO: regresje, numer wersji, SHA, właściciel kodu
ROLLBACK: commit / kopia / brak kasowania prywatnych danych
NIEDOMKNIĘTE RYZYKA I NAJBLIŻSZY KROK:
```

## Odesłania do udokumentowanych ustaleń

- Audyt kolizji 1.2.17: https://github.com/adriandziura0-rgb/sora/blob/audit-sora-kolizje-dodatkow-20261016/AUDYT_KOLIZJI_DUPLIKACJI_DODATKOW_SORA_1_2_17.md
- Poprzednie zasady R01–R16 i K01–K14: https://github.com/adriandziura0-rgb/sora/blob/audit-sora-kolizje-dodatkow-20261016/PLAN_ZASAD_PRACY_I_TESTOW_KOLIZJI_SORA.md
- Audyt drzewa: https://github.com/adriandziura0-rgb/sora/blob/main/docs/AUDYT_DRZEWA_SORA_2026-10-15.md
- Plan i stan projektu: [PLAN_PRAC_I_STAN_SORA_2026-10-16.md](PLAN_PRAC_I_STAN_SORA_2026-10-16.md)

**Zasada publikacji:** dokumentacje i plany są oddzielone od kodu; ich zapis nie nadaje statusu „naprawione” ani „wydane”. Żaden plik aplikacji, prywatnej bazy lub artefakt kompilacji nie jest zmieniany przez ten regulamin.
