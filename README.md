# Drogowskazy Sora 1.2.17

Android APK z wbudowanym analizatorem Drogowskazy 4.5.12. Po instalacji dotknięcie
ikony automatycznie przygotowuje program, uruchamia usługę i otwiera panel w aplikacji.
Nie trzeba instalować Termuxa ani wybierać osobnego ZIP-a z programem.

## Pliki i baza

Panel obsługuje systemowy wybór plików, całych folderów wraz z podfolderami
oraz miejsca zapisu wyników. Można wskazać folder udostępniony przez Android,
w tym katalog na karcie SD. JSON, Markdown, SQLite i druk do PDF używają
systemowych okien Androida.

Aktualizacja aplikacji zachowuje cały prywatny katalog `data`, w tym bazę
SQLite i pliki WAL. Do repozytorium oraz zasobów APK trafia wyłącznie program;
baza użytkownika pozostaje prywatna. Nowa instalacja tworzy pustą bazę, którą
można uzupełnić importem dokumentów albo przywrócić z kopii SQLite.

Wstecz w panelu otwiera dotychczasowy ekran ustawień, z przywracaniem kopii
bazy, ręczną aktualizacją programu i sterowaniem usługą.

W **Baza / porównania** użyj **Dodaj pliki do bazy**, aby wskazać jeden lub kilka
dokumentów z Pobranych albo karty SD. **Dodaj folder do bazy** wybiera katalog
z podfolderami. **Przywróć kopię SQLite** wybiera plik `.sqlite3` i zastępuje bazę
po sprawdzeniu jej integralności. Nieprawidłowa kopia nie zastępuje obecnej bazy.
Archiwum ZIP z dokumentami najpierw rozpakuj. Błąd odczytu jednego dokumentu
nie przerywa importu pozostałych, a podsumowanie błędów pozostaje widoczne.
Przycisk **Ustawienia aplikacji** daje bezpośredni dostęp do ekranu usługi.

## Praca w tle

Usługa foreground utrzymuje analizę kolejki po zgaszeniu ekranu i zamknięciu panelu.
Niedokończone rekordy są wznawiane z SQLite; zakończone pozostają zakończone.
Ustaw baterię aplikacji na **Bez ograniczeń**. Systemowe Wymuś zatrzymanie
wyłącza usługę do ponownego uruchomienia aplikacji.

APK używa tego samego identyfikatora i certyfikatu co Sora 1.2.1 STABLE.
Instaluj jako aktualizację. Panel zachowuje interfejs HTML/JavaScript poprzedniej
wersji we własnym WebView; analizator Python jest osadzony w APK przez Chaquopy.

## Kontrola wydania

GitHub Actions sprawdza instalację i aktualizację programu z zachowaniem danych,
odrzucanie uszkodzonych ZIP-ów, kontrakt folderów, start lokalnego serwera,
wznowienie trwałej kolejki oraz brak ponownego liczenia zakończonych rekordów.
Po budowie sprawdza podpis i obecność zasobów w wynikowym APK.
Testy zainstalowanego APK na emulatorze Androida uruchamiają prawdziwy WebView,
systemowe okna wyboru plików i folderów oraz zapis do SQLite. Raport testów
jest osobnym artefaktem przebiegu; aplikacja wydania zawiera tylko ABI arm64.

## Silnik 1.2.5 — optymalizacja porównywania redakcji

Naprawiono wielokrotne obliczanie par artykułów już obecnych w pamięci podręcznej.
Wynik rozpoznawania tej samej sprawy i 257 testów GOLD pozostają identyczne.
Poprawka dotyczyła wyłącznie `clean_core/topic_matcher.py` w starszych
buildach. Od etapu CLEAN 3 wszystkie aktualne pliki programu są zapisane
w `runtime_source/`, a ZIP powstaje deterministycznie przez
`tools/build_runtime_from_sources.py` pod kontrolą SHA-256.
Każda niezatwierdzona zmiana pliku zatrzyma budowanie. Pobieranie plików, wybór folderów, panel, format bazy i import
pozostają bez zmian. PHONE i PC muszą używać tego samego nowego wydania
przy przekazywaniu ZIP TRANSFER, ponieważ identyfikator silnika się zmienia.

## Wyniki wybranych materiałów obok zaznaczenia (1.2.8)

W **Użytkownik → Baza / porównania → Porównaj linie redakcyjne / foldery**
zaznacz od **1 do 10** folderów lub redakcji. Po kliknięciu
**„Pokaż analizę zaznaczonych”** zobaczysz wyniki WYŁĄCZNIE wybranych
materiałów. Dla dwóch i więcej grup przycisk **„Porównaj zaznaczone”**
pokazuje także dotychczasową szczegółową tabelę porównawczą.

Wyniki to nie jedna tabela: karty podsumowania, liczba artykułów i relacji,
pokrycie P1–P5, ranking redakcji według wskaźników normalizowanych,
TOP tematów, aktorów, targetów, źródeł i P0 oraz ostatnie dokumenty.
Na PC zaznaczenie jest po lewej, a wyniki po prawej; na telefonie
wyniki są bezpośrednio pod zaznaczeniem w tym samym widoku.

Endpoint `/api/baza/analiza_wybranych` bez listy grup zwraca błąd 400 —
nie istnieje automatyczna analiza całej bazy w tym ekranie. Odczyt
używa wyłącznie już gotowych zapisanych analiz i nie modyfikuje SQLite.
Pobieranie, katalogi/SD, import, format danych i stare porównania bez zmian.

### Widok mobilny 1.2.8
Porównanie 2–10 zaznaczonych grup pokazuje wszystkie metryki również w
pionowych kartach na telefonie. Żadna kolumna nie jest ucinana. Oryginalna
tabela pozostaje dostępna w programie (na komputerze) i nie zmieniono
pobierania, importu, bazy danych ani klasyfikatora.

## Etap 1: jednoznaczny wybór i wyświetlanie (1.2.8)

Widok **Baza / porównania** oznacza aktualnie zaznaczony zakres: nazwy
folderów/redakcji i ich liczbę. Komunikat o braku aktywnego artykułu
odróżniono od wyniku porównania. Przy zmianie wyboru poprzedni raport
jest ukrywany, a niezakończony odczyt anulowany; spóźnione wyniki nie
powinny wracać na ekran. Na telefonie wartości porównań pozostają
w pionowych kartach. To wyłącznie zmiany warstwy wyświetlania;
nie zmieniono silnika, SQLite, importu, folderów ani transferu.

## Android 1.2.9 — niezawodne uaktualnianie panelu

W wersjach 1.2.4–1.2.8 identyfikator wbudowanego programu
`4.5.12-inapp-2` nie zmieniał się przy kolejnych APK. Po aktualizacji
Android niekiedy uruchamiał poprzednie pliki HTML i JavaScript, dlatego
nie było widać „Aktualnego zakresu” i nowego panelu zaznaczonych.

Od 1.2.9 identyfikator wbudowanego pakietu wynika z wersji zainstalowanego
APK. Przy instalacji aktualizacji aplikacja bezpiecznie zatrzymuje
runtime, wypakowuje nowy interfejs i **zachowuje cały katalog data**
(w tym bazę SQLite, WAL, wyniki i pozostałe pliki użytkownika).
Przy nieudanym wdrożeniu wraca do poprzedniej wersji plików programu.
Przy kolejnych wersjach APK trzeba zwiększać `versionCode` i `versionName`.
Test automatyczny symuluje aktualizację 1.2.8 → 1.2.9 oraz
migrację z identyfikatora `4.5.12-inapp-2`. Silnik i pobieranie niezmienione.

## Trwałość widoku Baza / porównania (PR #3)

Przy ponownym otwarciu aplikacji ekran **Baza / porównania** przywraca ostatnio
wybrane 1–10 folderów/redakcji oraz raport lub porównanie, jeżeli były widoczne
przed zamknięciem. Stan wyboru przechowuje WebView w `localStorage`; **nie ma tam
tekstów artykułów, analiz ani kopii bazy**. Raport pobiera świeże wyniki z
istniejących zapisów SQLite i nie uruchamia ponownie analizy.

Ręczne kliknięcie **Ukryj wyniki** jest zapamiętywane. Jeśli folder nie istnieje
już w bazie, aplikacja nie pokazuje cudzych danych pod starym zaznaczeniem.
Wyłączenie lub wyczyszczenie pamięci WebView może usunąć wybór ekranu, ale
nie powinno usunąć prywatnej bazy SQLite. Nowy test `node
tools/test_view_persistence.mjs` oraz scenariusz w `tools/test_android.mjs`
weryfikują odtworzenie widoku bez zmiany artykułów.

**Uwaga wydaniowa:** te poprawki będą dostępne na telefonie dopiero po
zbudowaniu i zainstalowaniu nowego APK z bieżącej gałęzi PR. Przed aktualizacją
należy wykonać eksport TRANSFER oraz potwierdzić zielony build.

## SORA 1.2.13 — CLEAN, etap 1
APK `versionCode=16`. Identyfikator runtime to SHA-256 zawartości
`drogowskazy-runtime.zip` i `versionName`, nie sam numer wersji.
Aktualizacja nawet z identycznym numerem aktywuje zmieniony kod WebView
i pozostawia SQLite/WAL/SHM oraz katalog `data` nienaruszone.
Przed aktualizacją wykonaj eksport TRANSFER lub kopię SQLite.

## SORA CLEAN — etap 2 (15.10.2026)

Natywne wydanie Windows działa przez C# WinForms WebView2 i `SoraSilnik.exe`.
Na gałęzi CLEAN etap 2 usunięto wyłącznie potwierdzone, nieaktywne źródła
starych aplikacji desktopowych (Tkinter, Qt/pywebview, ich stare budownicze i testy).
Moduł `presentation.py`, którego używał test poprawności raportu, zachowano
bez zmian treści jako `desktop/report_projection.py` z poprawionym importem testu.
Usunięte pliki nadal są dostępne w historii Git; nie usunięto żadnych plików
APK/SQLite/TRANSFER ani zamrożonego CORE. CI sprawdza brak importów martwego
kodu i wykonuje dodatkowo ochronę prywatnej sesji Windows. Baza użytkownika
pozostaje nietknięta.

## SORA 1.2.13 — CLEAN etap 3: pojedyncze źródło kodu
Kanoniczne pliki całego programu znajdują się w `runtime_source/`
(66 plików + manifest, bez baz użytkownika). Wbudowany ZIP
`app/src/main/assets/drogowskazy-runtime.zip` **nie jest śledzony w Git**:
obydwa workflow budują go wyłącznie przez
`python tools/build_runtime_from_sources.py`.

Bajty gotowego ZIP muszą być identyczne z zaliczonym silnikiem z etapu 2
(SHA-256 `bee4fd3c9f67131e8d49cbf2789bce46fdfcde25610aeeb4e3566529e44cffd8`).
Zmienione źródła wymagają osobnego, świadomie zatwierdzonego wydania:
samo narzędzie CLEAN **nie** wprowadza nowych funkcji ani nie
patchuje programu w ciemno.

Zniknęły stare skrypty `patch_engine_runtime.py`,
`patch_full_database_dashboard.py` i kopie `tools/overview_assets`.
Kryteria zaliczenia: bitowa zgodność runtime, 257/257 GOLD,
identyczny identyfikator silnika PHONE i PC, transfer, SQLite,
raporty, a następnie pełne testy Android/Windows na tym samym commicie.

## SORA 1.2.14 CLEAN — etap 4 (15.10.2026)

Finalny pakiet PHONE i PC jest budowany z jednego katalogu `runtime_source/`;
aktualizacja zachowuje bazę SQLite, WAL i SHM. Raport zaznaczonych grup
używa wspólnego eksportu `pobierzPlik`, tak jak raporty spraw i cytatów.
Symbole PDB, dokumentacja WebView2 XML i testowe zrzuty ekranu są
publikowane wyłącznie jako osobny artefakt diagnostyczny Windows,
nie w instalacyjnej paczce CLEAN. Nie usuwaj aplikacji na telefonie:
najpierw wyeksportuj TRANSFER, a nowy APK zainstaluj jako aktualizację.
Zalecana weryfikacja: `python tools/test_release_clean.py`, 257/257 GOLD,
testy transferu PHONE↔PC, pełny test Android SAF oraz natywny Windows EXE.

## SORA 1.2.15 — Analizy etap A1 (15.10.2026)
Porównanie 2–10 folderów/redakcji oraz jednej sprawy nie pokazuje nieaktualnego wyniku po HTTP 4xx/5xx, zmianie wyboru czy spóźnionej odpowiedzi. Eksport jest dostępny wyłącznie dla bieżącego zakresu. Jednostkowa regresja: `node tools/test_scope_integrity.mjs`. Android i Windows wymagają zielonych buildów z tego samego SHA. CORE, SQLite i transfer pozostają bez zmian.

## SORA A2 — analiza jednego zapisanego artykułu (1.2.16)

Po otwarciu dokumentu z bazy rozwijana karta pokazuje jego ID, ścieżkę,
SHA-256 treści, identyfikator i datę zapisanego przebiegu oraz do ośmiu
fragmentów/dowodów wraz z jawną informacją o pełnej liczbie kart.
Eksport raportu, pełnego JSON i PDF odczytuje ten sam dokument przez GET
`/api/baza/dokument/<id>/wynik`, sprawdzając tożsamość przebiegu.
Po zmianie tekstu lub podmianie analizy w SQLite eksport jest blokowany,
a użytkownik może ponownie otworzyć zapisany artykuł. Nie następuje ciche
`POST /api/raport` ani przeliczenie classifiera. Dane i schemat SQLite bez zmian.

## SORA 1.2.17 — samodzielny raport HTML dla zaznaczonych grup

- Eksport `Pobierz raport HTML` zapisuje **statyczny, samowystarczalny** raport. Wszystkie 8 metryk porównania widoczne bez zmiany wskaźnika, bez JavaScript i bez kontaktu z SQLite.
- Ostatnie dokumenty są pozycjami tekstowymi z informacją o pochodzeniu — nie udają przycisków otwierających artykuł, które nie działają poza aplikacją.
- Panel w aplikacji pozostaje interaktywny, JSON zachowuje oryginalny kontrakt, CORE `ENGINE_SHA`, schemat SQLite, zakres wybranych grup i TRANSFER bez zmian.
- Regresja Android: eksport HTML nie może zawierać martwych kontrolek, a wszystkie 8 wskaźników muszą być widoczne.
