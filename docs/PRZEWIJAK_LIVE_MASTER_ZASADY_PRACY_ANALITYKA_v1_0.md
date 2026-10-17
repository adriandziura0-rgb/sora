# PRZEWIJAK LIVE — MASTER ZASAD PRACY NAD APLIKACJĄ ANALITYCZNĄ

**Wersja dokumentu:** 1.0 • **Data:** 2026-10-17  
**Status:** obowiązujący standard proponowany do wdrożenia; **nie jest raportem z audytu ani potwierdzeniem wykonanych testów**.  
**Zakres:** Przewijak LIVE / PHONE / PC; warstwa analityczna korzystająca z danych już zbieranych przez aplikację.  
**Priorytet:** bezpieczeństwo historii i CORE > prawidłowość danych > niezawodność > testowalność > wydajność > funkcje > wygląd.  
**Reguła przy konflikcie:** wyższy priorytet wygrywa; wyjątków nie wprowadza się „na chwilę” bez zapisu decyzji i dowodów.

---

## 0. Cel i definicja sukcesu

Tworzymy **warstwę analityczną nad istniejącym kolektorem**, a nie drugi kolektor. Produkt ma przekształcać surowe, udokumentowane obserwacje w audytowalne analizy, porównania i ostrożnie interpretowane prognozy. Musi jasno odróżniać fakty od inferencji i od braków danych. Nie może pogorszyć zbierania danych, stabilności telefonu lub PC ani utracić historii.

Sukces wymaga równocześnie: zachowania integralności CORE; spójności identyfikatorów i sesji; kompletnej ścieżki pochodzenia danych; rozliczenia utraty/braków; reprodukowalnych obliczeń; czytelnej analityki w języku polskim; dowodów z testów Android/Windows i bezpiecznego wydania CLEAN.

## 1. Reguły absolutne — STOP

**STOP-01 — AUDYT PRZED KODEM.** Najpierw opisz błąd, zasięg, przyczynę, skutki i dowody. Nie modyfikuj „na próbę” działających obszarów.

**STOP-02 — DAWCA → ODBIORCA.** Dla każdej zmiennej zinwentaryzuj źródło, DOM/format, parser, transport, odbiorcę, normalizację, zapis, odczyt, analitykę i ekran. Bez dowodu z obu końców nie deklaruj poprawnego przepływu.

**STOP-03 — NIE NARUSZAĆ CORE.** Collector, MASTER/SOURCE UID, transport/ACK, heartbeat, raw snapshots i `live_core.sqlite3` pozostają zamrożone. Wyjątek tylko po dowodzie winy CORE, decyzji, backupie, izolowanej gałęzi i regresji E2E.

**STOP-04 — NIE USUWAĆ HISTORII.** Zakazane kasowanie lub ciche nadpisywanie bazy, sesji, obserwacji i danych niezinterpretowanych. Retencję i ewentualne archiwizowanie projektuje się odrębnie, z walidacją odtworzenia.

**STOP-05 — NIE ZGADYWAĆ.** `brak danych ≠ 0`, `brak kursu ≠ kurs 0`, `brak FT ≠ zakończony`, `brak odczytu ≠ brak gola`, `ponowny mecz tych samych graczy ≠ ten sam MATCH UID`.

**STOP-06 — BRAK CZARNEJ SKRZYNKI.** Prognoza musi mieć czas, znane dane wejściowe, wersję algorytmu, próbę, ograniczenia i możliwość odtworzenia. Nie przypisuj jej pewności bez kalibracji.

**STOP-07 — JEDEN AUTORYTET NA RODZAJ DANYCH.** CORE odpowiada za obserwacje; quality/observer za ocenę jakości; analytics za obliczenia; UI za prezentację. Nie mnożyć konkurencyjnych „prawd”.

**STOP-08 — ZERO DANYCH Z PRZYSZŁOŚCI.** Przy analizie stanu z minuty X nie wykorzystywać wyników, zmian kursu ani etykiet znanych dopiero później.

**STOP-09 — TEST TELEFONU I PC.** Samo kompilowanie, test jednostkowy lub zielona lampka nie zastępują realnego testu zbierania, uśpienia, wznowienia, eksportu i poprawności danych.

**STOP-10 — COFNIĘCIE BEZ COFANIA HISTORII.** Wycofuje się kod/funkcję, nie legalnie zapisane nowe obserwacje. Każdy release ma procedurę rollbacku.

## 2. Architektura granic odpowiedzialności

```
STRONY/ŹRÓDŁA: Superbet | Fortuna | Betsport/Betcris
     ↓ konkretne obserwacje DOM / raw evidence
OBECNY KOLEKTOR / WEBVIEW / PARSER (CORE FROZEN)
     ↓ uporządkowany komunikat + identyfikator zdarzenia
BRIDGE / TRANSPORT / ACK / RECONNECT (CORE FROZEN)
     ↓ zapis z zachowaniem kolejności i idempotencji
live_core.sqlite3  [źródło prawdy: RAW, MASTER, SOURCE, sesje]
     ↓ tylko odczyt / spójny snapshot / wersjonowany adapter
QUALITY / OBSERVER [oddzielna baza; nie poprawia RAW]
     ↓ zatwierdzone rekordy + opis braków i jakości
ANALYTICS ENGINE [oddzielna baza, modele, statystyki]
     ↓ wersjonowane API / DTO
UI ANDROID / WINDOWS + RAPORTY
```

**Reguły:** (a) obliczenia analityczne nie mają prawa zapisywać do CORE; (b) żadna metryka ani rekomendacja nie staje się surowym faktem; (c) parser źródła i identyfikacja meczów nie są „naprawiane” przez UI; (d) analityka może emitować *wniosek o zmianę parsera* do audytu, lecz nie zmienia parsera automatycznie; (e) rdzeń ma działać nawet przy wyłączonej analityce.

Zalecana izolacja logiczna: `live_core.sqlite3` → `observer.sqlite3` → `analytics.sqlite3`. Nazwy baz pomocniczych są propozycją architektoniczną; przed wdrożeniem sprawdzić aktualny układ repozytorium i nie tworzyć duplikatów istniejących modułów.

## 3. Obowiązkowy audyt DAWCA → ODBIORCA

Dla każdej zmiennej utwórz kartę:

| Pole | Co udokumentować |
|---|---|
| Nazwa logiczna | np. `goals_total`, `home_score`, `market_line`, `odds_over` |
| Dawca | źródło, strona/URL lub typ widoku, identyfikator bukmachera |
| Dowód RAW | minimalny fragment obserwacji, timestamp, hash, źródło |
| Selektor/parser | dokładna funkcja, wejście, wersja parsera, wynik |
| Typ i jednostka | int, decimal, sekundy/minuty, część meczu, linia O/U |
| Dostępność | kiedy zmienna może naturalnie zniknąć; stan zamkniętego rynku |
| Transport | nazwa komunikatu, `event_id`, kolejka, ACK, retry |
| Odbiorca | funkcja, endpoint, mapa pól, walidator |
| SQLite | tabela, kolumna, klucze, constraints, transakcja |
| Analiza | widok/algorytm, reguły wyłączenia i jakości |
| UI | ekran, tekst po polsku, interpretacja `null`, świeżość |
| Test | identyfikator testu potwierdzającego cały łańcuch |

**Prześledź obie strony:** wartość z parsowania porównaj z dokładnie odpowiadającym jej rekordem u odbiorcy i zapisem w SQLite. Sprawdź opóźnienie, powtórzenia, przestawioną kolejność i ucięte komunikaty. Nie wnioskuj z samych logów nadawcy, że baza przyjęła dane.

**Jednostka pracy:** jedna zmienna lub jeden łańcuch o wspólnej odpowiedzialności; nie zmieniać na raz parsera Superbet, normalizacji Fortuny, GUI i analityki.

## 4. Kontrakt zdarzenia / obserwacji

Każdy zapis obserwacji powinien dać się powiązać z następującymi informacjami (nie oznacza to dodawania kolumn do istniejącej bazy bez audytu):

```json
{
  "event_id": "unikalny_lub_deterministyczny_klucz_zdarzenia",
  "source_id": "superbet|fortuna|betsport",
  "source_match_uid": "id_meczu_u_źródła",
  "master_match_uid": "id_meczu_rzeczywistego",
  "session_id": "id_sesji_zbierania",
  "captured_at_utc": "ISO-8601",
  "received_at_utc": "ISO-8601",
  "persisted_at_utc": "ISO-8601",
  "match_clock": {"period": "1|2|extra|unknown", "minute": null, "status": "in_progress|suspended|ft_unconfirmed|ft_confirmed|unknown"},
  "score": {"home": null, "away": null, "state": "observed|missing|stale|parse_error"},
  "market": {"type": "total_goals", "line": null, "over": null, "under": null, "state": "available|closed|suspended|missing|parse_error"},
  "parser_version": "identyfikator_wersji",
  "raw_evidence_ref": "hash_lub_id_dowodu",
  "quality_flags": []
}
```

To jest **wzorzec kontraktu**, a nie deklaracja bieżącego schematu. Pole `event_id` musi mieć udokumentowaną semantykę idempotencji. `received_at` nie zastępuje `captured_at`: podczas przerw sieciowych te czasy mogą się znacznie różnić. Źródło powinno zachować RAW i stan interpretacji bez zmiany tego, co faktycznie zaobserwowano.

## 5. Niepewność, brakujące pola i końcówki meczów

Wyróżnij minimum: `OBSERVED`, `MISSING_AT_SOURCE`, `TEMP_UNAVAILABLE`, `MARKET_CLOSED`, `STALE`, `PARSER_ERROR`, `TRANSPORT_LOSS`, `UNCONFIRMED`, `CONFIRMED`. Nie przeprowadzać arbitralnej konwersji wszystkich stanów do `null` bez powodu; zachować kod przyczyny.

- Kursy i linie mogą zniknąć przed końcem meczu: zapisuj ostatni **rzeczywiście** odczytany kurs z czasem, ale nie przedstawiaj go jako bieżącego i nie przenoś na przyszłe minuty.
- Zablokowanie rynku albo brak kursów nie potwierdzają FT. `final_confirmed` wymaga jawnie udokumentowanego kryterium i dowodu.
- Gole liczymy na podstawie rzeczywistych zmian wyniku, z kontrolą cofnięć/korekt; nie sumować tego samego gola z trzech źródeł jako trzech goli.
- Minuta musi mieć źródło, format i regułę normalizacji (2×4, 2×5, inne formaty); nie dopowiadać przerw ani końca, jeśli źródło tego nie podało.
- Ekran powinien pokazać: `ostatni odczyt`, `ostatni poprawny kurs`, `bieżąca dostępność`, `wiek obserwacji`, `status potwierdzenia`.
- Brak danych stanowi mierzalną informację o jakości, ale nie podstawę do wymyślenia danych.

## 6. MASTER_MATCH_UID i SOURCE_MATCH_UID — polityka tożsamości

1. **Jeden rzeczywisty mecz = jeden MASTER_MATCH_UID**; różne źródła mogą mieć różne SOURCE_MATCH_UID przypięte do niego.
2. **Nowy mecz tej samej pary graczy = nowy MASTER_MATCH_UID**. Sama para nie jest kluczem meczu.
3. Ustanowionego MASTER nie przeliczamy po fakcie automatyczną zmianą tożsamości. Wyjątkowa korekta wymaga osobnego jawnego postępowania i historii decyzji.
4. Przy scalaniu porównuj identyfikatory źródłowe, format rozgrywki, czas startu z tolerancją wynikającą z dowodów, parę/graczy, wynik, oś czasu. Sam podobny wynik nie jest dowodem tożsamości.
5. Gdy brakuje wystarczających dowodów: `UNRESOLVED`; nie scalać „na siłę”.
6. Liczenie „niepowtarzalnych meczów” opiera się o MASTER, a nie na liczbie snapshotów lub unikatowych par.
7. Nie dopuszczać do sytuacji, w której dwa różne MASTER mają ten sam aktywny SOURCE_MATCH_UID w tej samej przestrzeni identyfikatorów i okresie źródłowym bez uzasadnionego wyjątku.
8. Każda deduplikacja ma raportować `przed`, `po`, `scalone`, `odrzucone`, `niepewne`, z przykładami i dowodami.

## 7. Kolizje, opóźnienia, replays i idempotencja

Testować co najmniej: podwójny pakiet; retry po utraconym ACK; pakiety w odwrotnej kolejności; restart odbiorcy w środku transakcji; dwa źródła jednego meczu; ten sam komunikat z dwóch sesji; utrata sieci; timeout przeglądarki; pełną kolejkę; niekompletne payloady; starszą odpowiedź wracającą po nowszej; timeout parsera przy zmianie strony.

**Zasady obsługi:** identyfikator wiadomości i stabilny dedupe key; ACK po trwałym zatwierdzeniu, nie po rozpoczęciu zapisu; retry bez mnożenia rekordów; zachowanie sekwencji per źródło/mecz lub jawna polityka reorder; backpressure i kolejka ograniczona pamięcią; timeouty i anulowanie; reconciliation po reconnect; niezależne liczniki `sent`, `received`, `accepted`, `duplicate`, `rejected`, `failed`, `persisted`; alarm, gdy różnicy nie można wyjaśnić.

Nie ukrywać utraty za licznikiem „pobrane”. Gdy transmisja jest co najmniej raz (`at-least-once`), stan końcowy musi być **idempotentny**.

## 8. Bezpieczeństwo SQLite / eksportu / importu

**CORE na żywo nie może być kopiowany zwykłym `cp` ani zastępowany inną bazą.** SQLite WAL może przechowywać zatwierdzone operacje poza głównym plikiem DB. Wykorzystuj online backup API lub świadomie zaplanowaną spójną migawkę. Nigdy nie usuwać pliku `-wal` lub `-shm` w ciemno.

**Eksport kontrolowany:** spójny snapshot → zamknięty pakiet → `manifest.json` zawierający `export_id`, źródło, wersję aplikacji, wersję schematu, UTC, liczbę rekordów/tabel, checksums, zakres czasu, ostatni event ID → archiwum z weryfikacją → test odczytu na kopii.

**Import kontrolowany:** sprawdzenie manifestu i checksums → walidacja schematu/zgodności → backup stanu odbiorcy → tryb podglądu (`dry-run`) z raportem zmian → decyzja o scaleniu → transakcja i weryfikacja wyniku → raport importu/konfliktów. Nigdy nie nadpisywać nowszych danych starszymi bez świadomej, odrębnej decyzji. Import identycznego ZIP dwa razy musi dać identyczny stan końcowy.

Dla analiz i testów korzystać ze spójnej migawki; analityka nie powinna blokować długimi transakcjami bieżącego kolektora. Testy muszą potwierdzić bezpieczeństwo w aktualnym trybie journal, rzeczywistym typie systemu plików i liczbie połączeń.

**Kontrola bazy:** `PRAGMA integrity_check`, spójność referencji, nieosierocone klucze, liczniki przed/po, próbki porównania checksum, możliwość odtworzenia backupu, wersja schematu. `integrity_check` nie zastępuje testu semantyki danych.

## 9. Schemat analityczny bez zanieczyszczania surowych danych

Wyliczone wyniki przechowywać osobno, np. logicznie:

- `analysis_run`: `run_id`, wersja kodu, schemat, dataset_snapshot_id, data odcięcia, konfiguracja, start/koniec, status.
- `input_selection`: użyte MASTER/SOURCE, zakresy dat, filtry, jakość, liczba uwzględnionych/odrzuconych.
- `quality_issue`: typ, źródło, event/MASTER, czas, stopień pewności, dowód.
- `feature_snapshot`: wyłącznie wartości dostępne **w chwili prognozy**.
- `prediction`: model/version, run, master, as_of, rynek/linia, prawdopodobieństwo, confidence/uncertainty, reguła ważności.
- `outcome`: niezależnie potwierdzony wynik, źródło potwierdzenia i czas jego poznania.
- `evaluation`: liczba ocenialnych przypadków, coverage, kalibracja, Brier/log loss, segmenty, ograniczenia.
- `report_artifact`: wersja widoku, zakres, użyty run i checksum raportu.

Przed implementacją porównaj te odpowiedzialności z istniejącymi tabelami i modułami. Nie tworzyć duplikatu tabeli o tej samej semantyce.

## 10. System analityczny: kolejność i wiarygodność

**A0. Audyt jakości danych:** kompletność wyniku/czasu/O-U/FT; luki; opóźnienia; świeżość; utrata źródła; rozbieżności; charakterystyki po źródłach i sesjach.

**A1. Opis rzeczywistych meczów:** unikalne MASTER, format, para, start/koniec potwierdzony lub nie, liczba snapshotów, liczba goli, czas i luki.

**A2. Zmiany podczas LIVE:** sekwencje wyników, zdarzenia goli, trajektorie linii i kursów, niedostępność rynku, porównanie źródeł oraz świeżości obserwacji.

**A3. Statystyka i profile:** N20/N50/N100/MAX; CURRENT vs LEGACY; średnia, mediana, rozkład, odchylenia, tail 8+/9+/10+; liczności i przedziały niepewności. Oddzielać formaty meczów oraz wersje źródeł.

**A4. Badanie prognostyczne:** offline; najpierw baseline i kalibracja, potem nowe modele; osobno PRE i LIVE; metryki jakości, a nie jedynie liczba trafień. Wersjonowanie i test out-of-sample.

**A5. Kokpit i raporty:** raport całości, raport pojedynczego meczu, pary/gracza, źródła, sesji, trendów i ograniczeń jakości. Wysoka czytelność i polskie etykiety.

**A6. Optymalizacja:** dopiero po potwierdzeniu niepogorszonej poprawności; profilowanie wąskich gardeł, cache z jawnie określoną świeżością, inkrementalne przeliczanie.

## 11. Walidacja modeli i ochrona przed fałszywymi wnioskami

Zawsze dokumentować: populację, okres i format, liczbę unikalnych meczów, odsetek kwalifikujących się do oceny, brakujące końce, decyzje o deduplikacji, definicje rynków O/U, moment dostępności kursu i moment predykcji.

Trening/walidacja/test powinny respektować czas: **train wcześniejsze → validation późniejsze → test najpóźniejsze**. Grupowanie po MASTER zapobiega przeciekowi snapshotów jednego meczu między zbiorami. Do predykcji LIVE dozwolone są jedynie dane obserwowane do `as_of`; końcowy wynik służy jako etykieta, nigdy jako wejście.

Raportować bazowy benchmark oraz właściwe metryki probabilistyczne (np. Brier i log loss przy potwierdzonych etykietach), krzywą kalibracji, wielkość próby i stabilność po źródłach/formatach. Zawsze wykazywać odsetek rekordów, które nie nadawały się do oceny. FT niepotwierdzone wykluczać z oceny zależnej od końcowego wyniku; zachować ich liczbę w statystyce braków.

Nie obiecywać gwarantowanej trafności ani zysku. Nie stosować niewalidowanych progów „68–72%” jako faktycznej skuteczności: każdy taki próg jest hipotezą do sprawdzenia na niezależnych danych, nie wynikiem.

## 12. Zasady samo-rozwoju i analizy inteligentnej

Obserwator ma prawo: znaleźć anomalie, wskazać selektory wymagające audytu, zbudować propozycję mapowania, oszacować niepewność, porównać działanie wersji, przygotować raport oraz test reprodukujący błąd.

Obserwator **nie ma prawa samodzielnie**: zmienić parsera/selektora produkcyjnego, przenieść MASTER, zmodyfikować surowego wyniku, dopisać „brakującego” gola, przepisać historię, nadpisać bazy ani wdrożyć zmiany bez testów. Każda sugestia staje się zadaniem audytowym (issue), nie automatycznym patchem.

Jeśli algorytm uczy się na nowszych danych, musi zapisać wersję zbioru uczącego, kryterium wyłączenia niedomkniętych meczów, datę, metryki i porównanie do poprzedniej wersji.

## 13. Czystość kodu i zapobieganie „łatkozie”

Przed zmianą sprawdź: drzewko projektu, aktywne entrypointy Android/Windows, użycie modułów i importów, powielone parsery, `OLD`, `backup`, `copy`, `legacy`, martwe funkcje, tabele oraz niewykorzystywane endpointy. Ustal, co jest aktywne, a co tylko historyczne; nazwa `OLD` sama w sobie nie jest dowodem zbędności.

Jedna implementacja odpowiada za jedną regułę biznesową. Nie tworzyć drugiego `get_score`, `normalize_market` czy `merge_master` bez świadomego zastąpienia istniejącego i testów porównawczych. Łatka tymczasowa ma właściciela, numer issue, termin usunięcia i warunek zamknięcia.

Usuwanie kodu wyłącznie po: dowodzie braku użycia → testach pokrycia → ocenie wpływu na migracje/wsteczną zgodność → zatwierdzeniu → małym commicie → regresji. W pierwszym przebiegu **tylko inwentaryzacja**, bez kasowania.

Nie refaktoryzować równocześnie działającego CORE i nowego UI. Utrzymywać pojedyncze źródło wspólnych kontraktów PHONE/PC; platformowe adaptery oddzielać od reguł analityki.

## 14. Wydajność bez szkody dla źródła danych

Nie zwiększać częstotliwości odpytywania źródeł tylko dlatego, że analityka potrzebuje gęstszych danych. Nie dokładać zewnętrznych pobrań z nowej aplikacji, jeśli RAW jest już dostępny w istniejącym kolektorze. Zmierzyć najpierw: opóźnienia pobrania/transportu/persist, wielkość bufora, liczbę pakietów, koszty zapytań, RAM, CPU, baterię, liczbę write-locków i czas eksportu.

Wdrożyć w analityce: inkrementalne przeliczanie tylko zmienionych MASTER, paginację wyników, zapytania z limitami, indeksy uzasadnione planem zapytania, sensowny cache z TTL i invalidacją, osobne zadania eksportu, brak blokowania UI oraz kontrolę limitów pamięci. Nie włączać nowych indeksów czy PRAGMA do produkcyjnego CORE bez audytu i testu wpływu.

## 15. Android: praca w tle i utrata zasięgu

Na Androidzie nie zakładać, że proces będzie stale działał po zgaszeniu ekranu. Projektować według aktualnych ograniczeń systemu: poprawnie deklarowane usługi pierwszoplanowe tam, gdzie są rzeczywiście dozwolone i uzasadnione, widoczne powiadomienie, świadoma obsługa ubicia procesu, wznowienie i trwały checkpoint. Nie traktować WorkManager jako gwarancji ciągłego odczytu w sekundowym interwale.

Obowiązkowe scenariusze: ekran wyłączony, ekran włączony, aplikacja w tle, utrata/recovery sieci, zmiana Wi‑Fi/LTE, oszczędzanie energii, zamknięcie okna, ubicie procesu przez system, restart, niski poziom baterii, ograniczona pamięć, eksport podczas zbierania, ponowne uruchomienie, równoczesny import lub raport.

Wynik testu to liczby i spójność danych przed/po, a nie tylko informacja „aplikacja pozostała zielona”. Ograniczenia Androida i producenta trzeba komunikować w UI; nie obiecywać bezwarunkowej ciągłej pracy.

## 16. Windows/PC i PHONE — jeden kontrakt, dwie lokalne instancje

PHONE i PC powinny mieć tę samą semantykę CORE/MASTER/SOURCE, format eksportu i model wyników analitycznych, ale niezależne lokalne bazy robocze. Nigdy nie współdzielić jednego pliku SQLite przez synchronizację w chmurze lub zwykłe kopiowanie. Wspólny kontrakt danych, jawna wersja schematu i testy zgodności są ważniejsze niż identyczny UI.

Interfejs Windows może mieć własny host; backend lokalny musi mieć nadzorowany lifecycle, port, autoryzację i czytelny komunikat awarii. Nie wystawiać niezabezpieczonego endpointu na sieć publiczną ani nie pozostawiać osieroconych serwerów po zamknięciu okna. Przy każdej wersji testować start, wyłączenie, ponowne otwarcie, raport, transfer i zachowanie po wznowieniu.

## 17. Interfejs analityczny: obowiązkowa czytelność

Wszystkie napisy **po polsku**. Każdy ekran powinien odróżniać: `fakt`, `wniosek`, `prognozę`, `brak danych`, `niepotwierdzone`, `stare dane`, `błąd połączenia`. Analizę należy przedstawiać wprost, a nie ukrywać pod jedną zagadkową tabelą.

Zalecane widoki: Kokpit stanu LIVE; Lista unikalnych MASTER; Szczegóły meczu i osi czasu; Źródła i rozbieżności; Sesje i straty danych; Analiza N20/N50/N100/MAX; Analiza prognoz i ocena; Raporty/eksporty; Diagnostyka.

W każdej analizie pokazywać zakres czasu, liczbę meczów **i** snapshotów, liczbę wykluczeń, definicję metryki, wersję analizy, źródło danych, ostatnią aktualizację i ograniczenia. Statystyka bez próby i podstawy obliczenia nie jest raportem.

Nie ukrywać stanu błędu przez spinner bez końca. Nie przeprowadzać ciężkich operacji w wątku UI. Obsługiwać anulowanie i komunikat o skutkach. Zmiany interfejsu bez prośby nie powinny przebudowywać zatwierdzonych ekranów.

## 18. Bezpieczeństwo techniczne i dostęp

Ograniczyć uprawnienia dostępu do CORE do czytania dla analiz; odrębne konta/role lub izolacja procesu tam, gdzie możliwe. Walidować importy i rozmiary archiwów, zabezpieczyć przed path traversal i ZIP bomb, ograniczyć maksymalne rozmiary i liczbę plików, odrzucać niezgodne schematy. Nie logować sekretów, tokenów ani pełnych wrażliwych payloadów.

Logi diagnostyczne mają wystarczająco dużo danych do odtworzenia błędu, ale nie powinny przechowywać haseł/sesji. Jeżeli istnieje lokalne API — bind domyślnie do loopback, ochrona przed przypadkowym dostępem z zewnątrz i weryfikacja żądań. Zależności pinować i kontrolować; nie pobierać ani nie uruchamiać niezweryfikowanych skryptów w buildzie.

Nowe źródła danych: respektować warunki usług i limity dostępu; na 403/429/CAPTCHA stosować obsługę błędu i ograniczenia, nie automatyczne obchodzenie blokad. Każde nowe źródło przechodzi osobny audyt kontraktu.

## 19. Zasady GitHub i organizacji zmian

### Repozytorium i gałęzie
- Zweryfikować aktualny repozytorium/branch/commit przed pracą. Nie zakładać, że lokalny ZIP jest identyczny z HEAD.
- `main`/stabilna gałąź chroniona. Każdy etap w krótkiej gałęzi z nazwą zadania, jednym celem i możliwością porównania diff.
- Utrzymać `ZASADY_PRACY.md`, `ARCHITEKTURA_DANYCH.md`, `KONTRAKTY_ZMIENNYCH.md`, `AUDYT/`, `TESTY/`, `CHANGELOG.md`, `PLAN_ETAPOW.md` (nazwa i struktura do sprawdzenia z repo przed dodaniem).
- Nie usuwać projektów/repozytoriów, historii ani archiwów tylko z powodu porządkowania drzewka.

### Commity i przegląd
- Jedno zagadnienie na commit/PR; rozdzielić test reprodukcyjny od fixu i cleanupu.
- W opisie: objaw → przyczyna → miejsce DAWCA/ODBIORCA → zakres → ryzyko → dowód testowy → rollback.
- Automatyczne CI ma obejmować lint/type/tests/contract/integration/build (w zakresie realnie dostępnym); test E2E z realnymi źródłami wymaga oznaczenia, gdy nie został wykonany.
- Nie scalać PR tylko dlatego, że test jednostkowy przechodzi; warunki akceptacji są obowiązkowe.

## 20. Zasady testów i scenariusze obowiązkowe

| ID | Test | Dowód akceptacji |
|---|---|---|
| T01 | Inwentaryzacja bez modyfikacji | porównanie plików i baz przed/po bez zmiany |
| T02 | Superbet DAWCA→ODBIORCA | RAW → parser → bridge → SOURCE_UID → SQLite; zgodne wartości i czasy |
| T03 | Fortuna, Betsport/Betcris | to samo dla każdego źródła; izolacja formatów |
| T04 | Łączenie MASTER | dwie strony jednego meczu to jeden MASTER; nowy mecz tej samej pary ma inny MASTER |
| T05 | Powtórzona wiadomość | dokładnie jeden stan końcowy, raport duplikatów |
| T06 | Opóźniony/stary pakiet | brak regresji bieżącego statusu i historii; zachowany dowód |
| T07 | ACK lost/reconnect | brak cichej utraty, brak podwójnego zapisu |
| T08 | O/U znika w końcówce | `market_closed/unavailable`, brak dopisanego kursu i fałszywego FT |
| T09 | Brak potwierdzonego FT | pozostaje niepotwierdzony, poza metryką wymagającą FT |
| T10 | Gole z wielu źródeł | ten sam gol nie jest policzony wielokrotnie |
| T11 | Długie zbieranie | opóźnienie, liczniki, RAM i baza bez narastającego problemu |
| T12 | Ekran wyłączony/Android | mierzona ciągłość i wznowienie zgodnie z limitami systemu |
| T13 | Zerwany internet | po reconnect wiadomo, co jest utracone/powtórzone/przyjęte |
| T14 | Eksport w czasie collectora | spójny snapshot, brak zerwania transakcji, raport zgodności |
| T15 | Import dwa razy | idempotencja i brak nadpisania nowszych danych |
| T16 | Stary/nowszy schemat | jawna zgodność/odrzucenie; backup i rollback |
| T17 | Analityka przy wyłączonym CORE | nie udaje live; raport historyczny działa na snapshotach |
| T18 | CORE przy wyłączonej analityce | collector działa normalnie; brak zależności odwrotnej |
| T19 | Test predykcji bez przecieku | dane dostępne tylko do `as_of`, split grupowy/czasowy |
| T20 | Raport i ekran w polskim UI | próby, braki, zakresy, pochodzenie i niepewność widoczne |
| T21 | Windows i Android CLEAN | build, otwieranie, wznowienie, eksport, zgodność kontraktów |
| T22 | Rollback | poprzednia wersja uruchamia się bez utraty danych |
| T23 | Kontrola repo i CLEAN | brak przypadkowego `OLD`, martwych kopii, binariów i sekretów |
| T24 | Odtworzenie backupu | odzyskana baza przechodzi integralność i zgodność liczników |

**Próg dla błędów krytycznych:** 0 niewyjaśnionych zmian MASTER, 0 utraconych już potwierdzonych zapisów, 0 nadpisanych rekordów historycznych, 0 domyślnie dopisanych FT/kursów/goli, 0 nieautoryzowanych zmian CORE. Dla wydajności i coverage progi ustala się na podstawie pomiaru stanu bazowego; nie wymyślać arbitralnej liczby.

Testy dzielić na: statyczne → jednostkowe → kontraktów → integracyjne → replay danych → E2E realnego źródła → smoke Android/Windows → endurance → regresja → odzyskanie/rollback. Udokumentować wersję, urządzenie, wersję systemu, start/koniec, liczniki i dowód w paczce TEST. Brak testu na fizycznym urządzeniu oznacza `NIEZWERYFIKOWANE`, a nie `ZALICZONE`.

## 21. Proces pracy nad jednym zadaniem — nie przeskakiwać

**BRAMKA 0: IDENTYFIKACJA.** Ustalenie wersji, repo/commita, zakresu, celu i ograniczeń. Wynik: karta zadania.

**BRAMKA 1: AUDYT READ-ONLY.** Pliki, runtime, architektura, D→O, stan baz, logi, przypadki reprodukcji, czystość kodu. Wynik: raport z dowodami i listą przyczyn potwierdzonych/podejrzanych.

**BRAMKA 2: KONTRAKT I TEST PRZED NAPRAWĄ.** Definicje danych, oczekiwane invariants, scenariusz czerwony, metryki stanu bazowego, ocena wpływu. Wynik: minimalny plan z kryteriami akceptacji.

**BRAMKA 3: BACKUP I IZOLACJA.** Spójny backup, checksum, osobna gałąź, feature flag, plan cofnięcia, żadnych eksperymentów na żywej bazie.

**BRAMKA 4: MINIMALNA ZMIANA.** W jednym miejscu, bez równoległego przepisywania CORE i UI. Każdy zmieniony plik ma uzasadnienie; nie dodawać plików tylko jako kopii starych wersji.

**BRAMKA 5: TESTY.** Od reprodukcji przez regresje, po urządzenia i połączenia realne. Wynik: test report z tabelą PASS/FAIL/BLOCKED/NOT_RUN.

**BRAMKA 6: DRUGI AUDYT.** Ponowna kontrola DAWCA/ODBIORCA, różnic kodu, niezamierzonych skutków, integralności baz i UX.

**BRAMKA 7: WYDANIE CLEAN.** Wersja, hash, changelog, pliki artefaktów, instrukcja użycia, test aktualizacji i rollback. Brak publikacji do stabilnej gałęzi przy otwartym regresie krytycznym.

**BRAMKA 8: OBSERWACJA PO WYDANIU.** Dane ze środowiska rzeczywistego, potwierdzenie poprawnego importu/odczytu; nowy etap tylko po świadomej akceptacji bramki poprzedniej.

## 22. Etapy tworzenia warstwy analitycznej

| Etap | Zakres | Gotowe, kiedy… |
|---|---|---|
| ET-A0 | Audyt rzeczywistego repo, baz i przepływu | lista aktywnych modułów, danych i ryzyk zweryfikowana |
| ET-A1 | Kontrakt READ-ONLY i eksport spójnej migawki | nie ma zapisu do CORE, snapshot sprawdzony |
| ET-A2 | Quality monitor i wykrywanie luk | rozliczone stany `missing/stale/closed/unknown`, testy T02–T10 |
| ET-A3 | MASTER cockpit, sesje, timeline i źródła | każdy ekran ma UID, zakres, liczniki, status danych |
| ET-A4 | Statystyka CURRENT vs LEGACY, N20/N50/MAX | odtwarzalne wyniki, właściwa deduplikacja i próby |
| ET-A5 | Model badawczy PRE/LIVE | walidacja czasowa, brak leakage, potwierdzone etykiety |
| ET-A6 | Raporty i eksport PHONE/PC | wersjonowanie, odporność na błąd, polski UX |
| ET-A7 | Endurance, regresja, rollback, CLEAN | testy na urządzeniach i odtworzenie kopii |
| ET-A8 | Rozszerzenia i automatyczna diagnoza | propozycje zmian, lecz bez samoczynnej mutacji CORE |

**Uwaga operacyjna:** wcześniejsze ET3/ET4 związane z pozyskiwaniem i transportem LIVE są oddzielnym torem. Nie uznajemy ich za zaliczone testami E2E na podstawie samego zamknięcia administracyjnego. Nowa analityka nie może zamaskować nierozwiązanej usterki w danych wejściowych.

## 23. Raport z każdego etapu — obowiązkowy wzór

```
ETAP / WERSJA / REPO / COMMIT:
CEL I ZAKRES:
CZEGO NIE WOLNO DOTYKAĆ:
STAN PRZED (hash/backup/liczniki):
DAWCA → PARSER → TRANSPORT → ODBIORCA → SQLITE → ANALIZA → UI:
WYKRYTE PROBLEMY I DOWODY:
PRZYCZYNA POTWIERDZONA / HIPOTEZA / NIEWIADOMA:
RYZYKO KOLIZJI I DUPLIKACJI:
RYZYKO DLA CORE/MASTER/SOURCE/BAZ:
INWENTARYZACJA OLD/MARTWYCH FUNKCJI/DUPLIKATÓW:
ZMIANA (pliki/funkcje/diff):
TESTY (PASS / FAIL / BLOCKED / NOT_RUN):
POMIARY I PORÓWNANIE PRZED/PO:
INTEGRALNOŚĆ BAZ PRZED/PO:
NIEPRZETESTOWANE ELEMENTY:
DECYZJA: GO / NO-GO / ROLLBACK:
ARTEFAKTY + CHECKSUMS:
NASTĘPNY NAJMNIEJ RYZYKOWNY KROK:
```

## 24. Kryteria natychmiastowego zatrzymania

Wstrzymaj zmianę lub rollout, jeżeli wystąpi choć jeden z poniższych warunków: znikające wcześniej zapisane rekordy; rozrywanie lub niejawna zmiana MASTER; brak możliwości wyjaśnienia różnicy między ACK a SQLite; podwójne naliczanie goli; automatyczne uznawanie FT z braku kursu; analiza wykorzystuje przyszły wynik; backup jest nieodtwarzalny; nowy ekran blokuje zbieranie; zaobserwowany regres pracy w tle; niejawna mutacja CORE; brak śladów do odtworzenia zdarzenia.

Reakcja: wyłączyć tylko nową funkcję/gałąź, zachować dane i logi, utworzyć diagnostyczny raport, wrócić do audytu. Nie stosować czyszczenia historii jako szybkiego „lekarstwa”.

## 25. Minimalna karta decyzji architektonicznej (ADR)

Każda poważna decyzja wymaga zapisania: problem, kontekst, warianty, wybrany wariant, uzasadnienie, wpływ na dane wsteczne, zagrożenia, testy, osoby/wersje zatwierdzające i procedurę odwrotu. Szczególnie dotyczy to zmiany MASTER, schematu baz, trybu pracy w tle, importu i parserów.

## 26. Zasada produktywności: pracujemy szybko, ale tylko w małych partiach

Nie oznacza to 26 oddzielnych wielotygodniowych faz. Krótkie, zakończone dowodem iteracje są szybsze niż jednorazowy, ogromny patch. Priorytetem jest usuwanie pojedynczej *potwierdzonej* przyczyny, a nie mechaniczne naprawianie objawów. W każdym zadaniu równolegle można przygotować testy, dokumentację i izolowaną analitykę, ale nie mieszać kilku modyfikacji produkcyjnego CORE w jednym eksperymencie.

**Praktyczna zasada dzienna:** jedna jasna hipoteza → jeden czerwony test → najmniejszy możliwy fix → zielony test + test sąsiednich funkcji → wpis do changelog. Jeśli nie da się wykazać poprawy liczbowo lub reprodukcją, zadanie nie jest zamknięte.

## 27. Krótki kontrakt dla każdego programisty i asystenta

> Nie zmieniam kodu ani baz przed audytem. Każdą zmienną prowadzę od DAWCY do ODBIORCY. Weryfikuję brak kolizji, duplikatów, brakujących pól, opóźnionych i nieaktualnych wyników. Chronię CORE, MASTER_MATCH_UID, SOURCE_MATCH_UID, RAW i historię. Zmiany analityczne umieszczam poza CORE. Najpierw przygotowuję test dowodowy, potem minimalną poprawkę i ponowny audyt. Bez testu Android/Windows nie deklaruję powodzenia E2E. Utrzymuję czystość kodu bez nieudokumentowanego kasowania. Nie zgaduję danych. Nie wdrażam do stabilnej wersji bez raportu, kopii, możliwości cofnięcia i akceptacji bramki.

---

## Źródła techniczne i standardy do weryfikacji przy implementacji

- SQLite Online Backup API — https://www.sqlite.org/backup.html
- SQLite WAL — https://www.sqlite.org/wal.html
- Android: ograniczenia uruchamiania foreground service — https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
- Android: zmiany zasad foreground services w kolejnych wersjach — https://developer.android.com/develop/background-work/services/fgs/changes

**Końcowa uwaga:** dokument definiuje zalecane zasady i docelowe granice architektury. Przed jakąkolwiek zmianą produkcyjnego kodu trzeba potwierdzić rzeczywisty stan bieżącego repozytorium, konkretnego ZIP/commita, wersji baz i urządzenia. Żaden zapis nie upoważnia do samodzielnego przebudowania zamrożonego CORE.