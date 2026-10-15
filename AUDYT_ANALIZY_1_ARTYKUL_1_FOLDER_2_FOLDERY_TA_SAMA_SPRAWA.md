# SORA 1.2.14 — audyt analizy: 1 artykuł, 1 folder, 2 foldery, ta sama sprawa

**Data:** 15.10.2026. **Podstawa:** commit `2f4f1b9037d2d352b57ce19b34430ceea0c3fc19`, gałąź `sora-full-clean-stage4-20261015`. **Typ:** statyczny audyt kodu i zakresu istniejących automatycznych testów; nie jest to ocena trafności wyników na rzeczywistej prywatnej bazie 554 artykułów, do której ten audyt nie miał dostępu. Wersja CLEAN 1.2.14 pozostaje bez zmian.

## 1. Jeden artykuł

**Ścieżka:** `GET /api/baza/dokument/<id>/wynik` → `otworzWynikZBazy(id)` → `renderuj(data.wynik)`.
- Plus: otwierany jest wynik z zapisanej analizy SQLite wraz z tekstem źródłowym, identyfikatorem dokumentu i rozbudowanym widokiem P0–P5, TOP, relacji, podświetleń i audytów.
- Plus: nie ma potrzeby automatycznego ponownego liczenia przy samym otwarciu.
- **P1 — spójność eksportu:** `pobierzEksportRaportu()` w `runtime_source/static/app.js:2138-2170` woła `POST /api/raport` także po otwarciu zapisanego wyniku. Przy braku poprzedniego runu na backendzie może otrzymać nową analizę, a następnie `renderuj(exportedData)` nadpisuje widok. Użytkownik oczekujący eksportu *zapisanej analizy* powinien otrzymać dokładnie ten sam wynik (ID/hash), bez możliwości niejawnego przeliczenia w trakcie eksportu. Dodać ścieżkę „eksportuj ten zapisany wynik” i test restartu procesu.
- **P1 — licznik jakości:** brak jednego jawnego ekranu „wynik zapisany vs świeżo przeliczony” oraz potwierdzenia źródła każdej karty relacji. Dla audytu powinny być widoczne źródło, wycinek tekstu, status dowodu, review, źródłowy run ID i czas analizy.
- Testy: otwarcie istniejącego, brak analizy i 404; czyta tylko wskazany ID; eksport i PDF tego samego runu po restarcie; brak obcych artykułów w wynikach i odtworzeniu.

## 2. Jeden folder

**Ścieżka:** zaznacz dokładnie 1 folder → `GET /api/baza/analiza_wybranych?mode=folder&group=...` → `build_selected_database_overview()`.
- Plus: działa dla 1–10 grup, uwzględnia tylko ukończone artykuły, odrzuca pliki techniczne; wynik wyłącznie z zaznaczonego zakresu. Renderuje liczniki, /1000 słów, pokrycie P1–P5, P0, TOP aktorów/tematów, raport HTML/JSON.
- **P1 — dowody niepełne:** `database_overview.py:78-90,161` ogranicza listę źródłowych dokumentów do **12 ostatnich**. Łatwo błędnie uznać ją za kompletną listę artykułów folderu. Oddzielić „12 ostatnich” od „wszystkie dokumenty” z paginacją i przejściem do źródła.
- **P1 — etykiety:** w trybie folderu wartości `sources` agregowane są według *rozpoznanej redakcji* (`database_overview.py:64-76,93-95`) zamiast według folderu. Jest to uzasadnione dla podziału według redakcji, ale wymaga wyraźnego opisu: „Wybrany folder: X; rozpoznane redakcje: Y”.
- **P1 — pokrycie bazy:** raport bazuje na gotowych analizach i nie zna pełnej liczby oczekujących/błędnych rekordów w wybranym folderze; obecnie świadomie nie podaje fikcyjnych liczb. Dodać osobny *prawdziwy* raport statusów zakresu bez odczytu całej bazy jako gotowego wyniku.
- Testy: 1 folder z 1 artykułem, 1 folder z wieloma artykułami, puste/w toku/błędne, podfoldery, dwa źródła w jednym folderze, duplikaty, pełny indeks i eksport zakresu.

## 3. Dwa foldery

**Ścieżka:** zaznacz dokładnie 2 foldery → `GET /api/baza/porownanie?mode=folder&group=A&group=B`, ewentualnie „Pokaż analizę zaznaczonych” dla obydwu zakresów.
- Plus: `editorial_compare.py:530-570` zwraca niezależne metryki A/B, różnice i szczegółowe rozkłady mówców, tematów, źródeł przywołanych oraz P0–P5. Normalizacja /1000 słów i ostrzeżenia przy małych lub nierównych próbach ograniczają błędne wnioski.
- **P1 — inne wydarzenia w zbiorach:** dwa foldery są porównywane jako pełne zbiory, bez wymogu wspólnych tematów, dat i artykułów. To poprawny *przekrój redakcji*, ale NIE dowód różnic w relacjonowaniu tej samej sprawy. Oddzielić na ekranie „porównanie całości” i „porównanie wspólnych tematów”.
- **P1 — dowody do różnic:** rozkłady zawierają liczby i częstości, ale nie wszystkie przykłady dokumentów/fragmentów dla każdego wskaźnika; użytkownik nie może łatwo zweryfikować każdej delty. Dodać rozwijane źródła dla metryki, listę dokumentów i ślad do cytatu.
- **P1 — nieaktualny widok po błędzie:** `app.js:3112-3136` przy błędzie zeruje globalny ostatni wynik, ale nie czyści bezpośrednio `#databaseComparisonResult`. Upewnić się, że błąd nigdy nie pozostawia na ekranie starej tabeli z poprzedniego żądania.
- **P2 — symbole wartościowania:** `app.js:3255` oznacza dodatnią/ujemną deltę klasami CSS `positive`/`negative`; wzrost techniki P2 czy liczby relacji nie jest automatycznie dobry/zły. Stosować neutralne różnice.
- Testy: 2 równe grupy, 1 vs 100 dokumentów, różne tematy/daty, brak grupy, błąd w trakcie ponownego pobierania, czyszczenie poprzedniego zakresu, stałe ID dokumentów.

## 4. Ta sama sprawa w różnych redakcjach

**Ścieżka:** ręcznie uruchom `GET /api/baza/tematy` → wybierz wykryty temat i 2–10 redakcji → `GET /api/baza/temat/porownanie?topic_id=...&group=...` → karty mobilne oraz oryginalna tabela.
- Plus: `topic_matcher.py:306-363` wymaga spójności parowej, weryfikuje podobieństwo tytułu/leadów, daty, kotwic oraz konflikt profilu wydarzenia; zapobiega łączeniu tematów słabymi łańcuchami. To dopasowanie heurystyczne, nie gwarancja tożsamości sprawy.
- Plus: porównanie jest ograniczone do artykułów z wykrytego klastra, a nie całych folderów; dostępne są identyfikatory, tytuły, publikacje, daty, odnośniki, HTML i JSON.
- **P0 — przestarzały wynik po błędzie:** `app.js:3216-3237` w `catch` czyści HTML, lecz nie ustawia `ostatniePorownanieTejSamejSprawy=null`. `same-story-mobile.js:207-213` obserwuje zmianę DOM i może na nowo wyrenderować **poprzedni** payload dla tego samego `topic_id`. Po nieudanym żądaniu karta może więc nadal pokazywać stary wynik. Konieczna atomowa kontrola stanu, ID żądania i test odpowiedzi 500/404 oraz zmiany doboru redakcji.
- **P1 — limit źródeł bez ostrzeżenia:** `same-story-mobile.js:58-64` ucina źródła do 60, ale pokazuje ich liczbę jako liczbę artykułów i eksportuje tylko te źródła do `source_documents`. Powinno być „pokazano X z Y”, paginacja i pełny eksport powiązanych dokumentów.
- **P1 — cytaty bez pełnego eksportu:** `same-story-mobile.js:177-202` pokazuje na kliknięcie max 8 cytatów/opinii z jednego artykułu. Eksport HTML klonuje aktualny DOM (`:142-161`), nie pobiera wszystkich dowodów i nie obejmuje niewczytanych cytatów. Raport sprawy powinien mieć kontrolowany eksport *pełnego* zapisanego materiału dowodowego albo jawnie wskazywać, że eksport jest wyciągiem.
- **P1 — źródło/rola:** obok cytatów wymagany jest link do konkretnych fragmentów i relation_id / status przeglądu; nie sugerować, że cytat lub przypisanie mówcy są potwierdzone bez weryfikacji.
- **P1 — wydajność:** wyszukiwanie tematów wykonuje porównania parami (w przybliżeniu O(N²) dla pierwszego odczytu, `topic_matcher.py:324-331`), choć cache chroni kolejne zapytania. Dla większych baz potrzebne limity, pomiar czasu i czytelny komunikat postępu.
- Testy: podobny temat i inne zdarzenie, sprzeczne daty, bardzo podobne leady bez wspólnej sprawy, 2–10 redakcji, brak źródła, 61+ artykułów w temacie, 9+ cytatów w artykule, błędna odpowiedź serwera, HTML/JSON z pełnym śladem, zmiana zaznaczenia w trakcie odpowiedzi, restart WebView.

## Ocena testów i ryzyka

- Potwierdzone w CI CLEAN 1.2.14: Android i Windows SUCCESS, 257/257 GOLD, testy odczytowe wybranych grup, porównania i podstawowy scenariusz mobilny tej samej sprawy.
- `tools/test_android.mjs:448-468` sprawdza powstanie kart, obecność minimum dwóch dokumentów i istnienie pobranych plików HTML/JSON, ale nie sprawdza **kompletności dowodów, prawdziwości cytatów, wszystkich wartości w kartach, reakcji na błędy i liczników po limitach**.
- To nie jest test zgodności semantycznej na całej prywatnej bazie. Bez realnej bazy nie podaje się procentowej trafności przypisań.
- Zmiany proponowane dotyczą najpierw UI i odczytowej warstwy raportów. **CORE, classifier, SQLite i TRANSFER pozostają zamrożone.**

## Plan wdrożenia po audycie

1. **A1 — bezpieczny stan wyników:** napraw przestarzały wynik po błędzie dla dwóch folderów i tej samej sprawy; anulowanie żądań, zakaz wyświetlania payloadu ze starego wyboru; scenariusze 4xx/5xx, timeout i restart.
2. **A2 — jeden artykuł:** pełny odczyt dokumentu i eksport dokładnie tego zapisanego wyniku, widoczne ID analizy, dowody/fragmenty i ostrzeżenia o braku źródła.
3. **A3 — jeden i dwa foldery:** kompletne listy dokumentów z paginacją; przejścia od metryki do artykułów, porównanie prób /1000 słów bez wartościujących kolorów; wyraźne rozdzielenie „całość folderów” i „te same tematy”.
4. **A4 — ta sama sprawa:** pełny zakres źródeł i cytatów, limit + licznik pełności, HTML/JSON dokumentujące ID, analizę, fragment, redakcję i ostrzeżenia; wydajność, testy błędów i fałszywych dopasowań.
5. **A5 — regresja:** 257/257 GOLD, testy Android i Windows, import/eksport, SQLite/WAL/SHM, kontrola danych niepowiązanych, transfer PHONE ↔ PC; dopiero wtedy nowe APK/EXE.

**Wniosek:** SORA ma działające cztery przepływy, lecz w ich *prezentacji i śledzeniu dowodów* istnieją konkretne luki. Nie oznaczać wyników „ta sama sprawa” jako zweryfikowanych bez testów na rzeczywistych artykułach.