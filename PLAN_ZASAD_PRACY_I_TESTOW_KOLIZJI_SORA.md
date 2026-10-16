# SORA — stały plan i zasady pracy nad dodatkami, kodem i regresjami

**Obowiązuje w następnych etapach** po 1.2.17 (podstawa `67f48a45`). Dotyczy Android PHONE, Windows WebView2, wszystkich dodatków analitycznych, UI, eksportów i transferu. Szczegółowe ustalenia: `AUDYT_KOLIZJI_DUPLIKACJI_DODATKOW_SORA_1_2_17.md`.

## Reguły obowiązkowe

**R01. Jeden właściciel funkcji i stanu.** Każde API, aktywny dokument, zaznaczenie, wynik porównania, eksport, import, scanner, walidacja i postęp mają jednego jawnego właściciela. Dodatki mogą subskrybować zdarzenia i czytać wyniki, nie redefiniować globalnych funkcji.

**R02. Zakaz nowych monkey-patchy, doraźnych wrapperów i nakładających się łatek.** Zmiany bezpośrednio w kanonicznym źródle. Istniejące nakładki oznaczyć jako dług techniczny, a następnie usunąć dopiero po testach zachowania. Nie tworzyć `_old`, `fix2`, `newFinal`, dubli klas ani alternatywnych entrypointów.

**R03. Zero loterii: deterministyczność.** Ten sam commit + wejście + ustawienia = te same wyniki semantyczne (moduły niedeterministycznych metadanych jawnie wyłączone z porównania). Wymagaj hashów silnika, runtime, schematu i identyfikatora builda; wymagaj powtarzalnego ZIP-a.

**R04. Zero cichego usuwania lub przywracania starego kodu.** Lista usuwanych/przenoszonych plików, graf importów, opis zachowania, test równoważności oraz możliwość odzyskania z historii Git. Nie usuwać użytkownikowi projektów, analiz, baz, plików pomocniczych i archiwów.

**R05. Zamrożony CORE i bazy.** Bez jawnej zgody nie zmieniać classifier/relacji/SQLite schema/TRANSFER/MASTER. Dane użytkownika tylko przez zaprojektowany eksport/import, kopia bezpieczeństwa, ochrona WAL/SHM, brak nadpisywania nowszych danych starszymi.

**R06. Jeden aktualny zakres i unieważnianie.** Każdy odczyt ma `scope = mode + groups + topic_id + selected_document_id + revision`, `request_id` i `AbortController`. Każda zmiana zakresu anuluje stare żądania, usuwa stare dane z widoku i blokuje ich eksport. Warunek A→B→A nadal unieważnia stare żądanie.

**R07. Jeden model wyniku — wiele widoków.** Telefoniczne karty, tabelki PC, PDF, HTML, JSON i zapisana sesja muszą bazować na tym samym modelu; widoki mogą różnić się prezentacją, nie liczbami, źródłami ani identyfikatorem analizy. Nie tworzyć drugiej ścieżki liczenia w UI.

**R08. Bez niejawnego przeliczania artykułu.** Dla zapisanego dokumentu odczyt i eksport mają zachować `document_id`, hash tekstu, `updated_at`, `analysis_run_id`. Wyjątki tylko za jawną zgodą użytkownika.

**R09. Zdarzenia UI zamiast wyścigu obserwatorów.** Przed dodaniem `MutationObserver`, `setInterval`, `addEventListener` sprawdzić, czy ktoś już obsługuje ten element. Nowe obserwatory muszą mieć uzasadnienie, lifecycle i test wielokrotnego otwarcia/wyjścia. Nie dopinać anonimowego handlera drugi raz bez kontroli.

**R10. Jednokrotny skan/import.** Jedno wybranie folderu = jeden przewidywalny skan i jeden typ operacji, albo jawnie opisane dwie fazy z testem liczby odczytów. Żadne ukryte ponowne skanowanie, importowanie, wznawianie i podwójne żądania do backendu.

**R11. Jeden kontrakt eksportu.** `pobierzPlik` / natywne mosty zapewniają zapis Android SAF i Windows; spójne pliki, nazwy, kodowanie i odmowy przy nieaktualnym wyniku. Nie wprowadzać obocznych Blob-downloadów bez weryfikacji.

**R12. Zgodność zakresu i dowodów.** W analizie 1 artykułu, 1/2 folderów i tej samej sprawy zawsze wiadomo: co wybrano, ile rekordów zakończonych, czego nie objęto limitami, dokument źródłowy, cytat, relacja i review. Brak źródła = komunikat, a nie fikcyjny dowód.

**R13. Żadnego udawania zaliczonego testu.** Zawsze rozdzielić: audyt kodu, testy jednostkowe, testy E2E na emulatorze, uruchomienie natywnego EXE, oraz manualny test prywatnej bazy/telefonu. Zielony build nie dowodzi trafności dopasowania „ta sama sprawa”.

**R14. Wszystkie nazwy i komunikaty dla użytkownika po polsku.** Nie usuwać dostępnych funkcji ani informacji analitycznych wyłącznie dla uproszczenia UI. Zmiany CLEAN muszą zachować wszystkie metryki P0–P5.

**R15. Jeden commit, oba systemy.** APK i EXE dla użytkownika muszą być zbudowane i zweryfikowane na tym samym SHA. Nie podawać plików do pobrania bez potwierdzenia ich pochodzenia, istnienia, zawartości i integralności. Zmieniać numer wersji/versionCode przy wydaniu.

**R16. Ograniczenie zakresu poprawek.** Najpierw naprawa P0, potem P1, potem kosmetyka P2. Nie mieszać zmiany silnika, parsera, importu i wyglądu w jednym commicie. Każdy etap ma kryterium wejścia, mały diff, scenariusz wycofania, test i raport.

## Macierz testów kolizji — obowiązkowa przy każdej zmianie dodatków

| ID | Operacja | Co ma zostać zweryfikowane |
|---|---|---|
| K01 | Załadować panel 2 razy i przywrócić sesję | Brak podwójnych handlerów, obserwatorów i eksportów |
| K02 | Cytaty A→B→A w trakcie `fetch` | Stare A nigdy nie zastępuje nowego wyniku A |
| K03 | Porównanie folderów A/B → A/C oraz HTTP 404/500 | Stara tabela i JSON nie wracają; A1 nie ma regresji |
| K04 | Jedna sprawa, zmiana tematu i redakcji w trakcie `fetch` | Tylko identyczny `topic_id` + grupa + rewizja |
| K05 | Import folderu pod limitem | Jeden pełny skan; bez podwójnego przekazania pliku |
| K06 | Folder ponad limit; anuluj, Escape, zamknij/wznów | Brak zablokowanego postępu, brak duplikatów w kolejce |
| K07 | Import, autosave i raport równocześnie | Żadna operacja nie kasuje/nie zastępuje cudzych wyników |
| K08 | Jeden artykuł, zmiana tekstu i restart | JSON, HTML, Markdown, PDF zgodne z zapisanym run ID albo odmowa |
| K09 | Jedna grupa, dwie grupy, ta sama sprawa | P0–P5, liczby, filtry, nazwy i źródła parytet UI ↔ JSON |
| K10 | Wiele folderów, pauza i ponowne otwarcie Androida | Praca w tle i wznowienie, brak podwójnego importu |
| K11 | Transfer PHONE↔PC i aktualizacja | Nie traci SQLite/WAL/SHM, idempotencja importu, brak konfliktu UID |
| K12 | Uruchom wydanie z czystego ZIP/APK | Brak OLD, ślepych plików, niezgodnej wersji, wad podpisu |
| K13 | Wszystkie testy istniejące | 257/257 GOLD, A1/A2, renderowanie przycisków, emulator, WebView2 |
| K14 | CSS i polskie etykiety na obu urządzeniach | Brak przesłoniętych kart, pustych okien, powielonych ID i błędów dostępności |

## Etapy obowiązujące odtąd

**0. Bazowy punkt odniesienia:** zamrozić i zapisać wersję 1.2.17; kontrola SHA, eksport danych próbnych, macierz testów.

**1. Import/recovery (P0):** najpierw test K05/K06, potem scalenie 6 globalnie nadpisywanych funkcji z kanoniczną logiką i wyeliminowanie ponownego skanu. Bez zmiany trwałej bazy.

**2. Cytaty i asynchroniczne porównania (P1):** wspólny `request_id`, `AbortController`, pełna rewizja wyboru, test A→B→A oraz K02–K04.

**3. Kontroler zakresu i wyświetlania (P1):** jedno zdarzenie zmiany wyboru; redukcja nadmiarowych obserwatorów; wspólny model kart, tabel i eksportu; K01/K07–K09.

**4. Duplikacja pomocnicza i UI (P2):** deduplikować identyczne listy ID, ujednolicić bezpieczne helpery, usunąć nieużywane/OLD dopiero po dowodzie braku zależności; pełny K14.

**5. Wydanie dopiero po pełnej regresji (gate):** K01–K14, GOLD, SQLite/TRANSFER, Android WebView/SAF, Windows WebView2 i manualny test na prywatnych materiałach. Raport każdego niepowodzenia bez maskowania.

## Szablon każdej zmiany

- **Przed:** wersja/commit, pliki, właściciel stanu, zaobserwowany błąd, test reprodukcji.
- **Zmiana:** co zastępujemy i dlaczego, które stare linie/kody wycofano, zakres baz i API (bez zmian lub jawne).
- **Po:** diff, SHA, wynik testu automatycznego, E2E i manualnego, liczba nierozstrzygniętych ryzyk.
- **Rollback:** wskazany commit bazowy, bez kasowania bazy i bez niejawnych migracji.
- **Status:** `W PLANIE`, `WDROŻONE BEZ TESTÓW`, `TESTY CZĘŚCIOWE`, `AP​K + EXE ZIELONE`, `RĘCZNIE POTWIERDZONE`. Nigdy nie oznaczać samego commitu jako „naprawiono” bez dowodu.

**Stan obecny:** audyt i zasady zapisane. Żadna z proponowanych napraw P0/P1 nie została jeszcze wdrożona w tym zadaniu. Nie ruszono działającej 1.2.17 ani danych.