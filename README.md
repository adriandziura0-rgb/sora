# Drogowskazy Sora 1.2.9

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
Poprawka dotyczy wyłącznie `clean_core/topic_matcher.py` w trakcie budowy
APK i PC (`tools/patch_engine_runtime.py`). Oryginalny ZIP jest objęty
kontrolą SHA-256; build przerwie się, jeżeli silnik został nieoczekiwanie
zmieniony. Pobieranie plików, wybór folderów, panel, format bazy i import
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
