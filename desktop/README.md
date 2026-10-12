DROGOWSKAZY SORA — WINDOWS 10/11 (64-bit) · TEN SAM PANEL CO W APK

JAK URUCHOMIĆ
1. Rozpakuj cały ZIP, nie przenoś samego pliku EXE.
2. Otwórz folder Sora, uruchom Sora.exe.
3. Windows wyświetla oryginalny interfejs PHONE w natywnym oknie Chromium QtWebEngine.
   Nie jest to karta przeglądarki internetowej ani inna, uproszczona aplikacja.
4. QtWebEngine jest dołączony do paczki. Nie wymaga pythonnet ani .NET Framework.
   Jeśli pojawi się błąd, sprawdź blad_startu.txt w katalogu danych.

ZGODNOŚĆ TELEFON ↔ WINDOWS
• Te same pliki HTML/CSS/JS wbudowane w aplikację Android:
  Użytkownik / Ekspert, baza i foldery, analizowanie dokumentów, P0–P5,
  porównania, Ta sama sprawa, wspólne treści i różnice, benchmark/GOLD,
  raporty, eksport, podglądy artykułów i analiza zaznaczonych.
• Ten sam silnik Python ze wspólnego runtime ZIP — bez zmiany klasyfikatora.
• Na PC dodatkowo natywne okna Windows do wskazania folderu, wykonania
  spójnej kopii SQLite, przywrócenia SQLite oraz TRANSFER ZIP.
• Program otwiera własne okno Sora.exe (QtWebEngine), a lokalny serwer słucha wyłącznie
  na 127.0.0.1:43847. Nie udostępnia panelu w internecie.
• Dane PC: %LOCALAPPDATA%\DrogowskazySoraPC\data\drogowskazy.sqlite3.
  Aktualizacja EXE nie usuwa tych danych.
• Historia zaznaczonych folderów i stan interfejsu są zapisywane
  w lokalnej pamięci WebView2, także po ponownym uruchomieniu.

PRZENOSZENIE DANYCH
Aplikacje PHONE i PC mają oddzielne lokalne bazy.
Aby przenieść dane z telefonu, wykonaj na telefonie EKSPORT TRANSFER ZIP;
na komputerze wybierz Baza → TRANSFER PHONE ↔ PC →
„Importuj z telefonu · ZIP”. Eksport na telefon działa odwrotnie.
Importer weryfikuje wersje, integralność i scala rekordy bez kopiowania
na żywo plików SQLite. Nie odinstalowuj starej aplikacji tylko po to,
aby zainstalować nowszą. Zachowaj swoją ostatnią kopię TRANSFER.

EKSPORT
Pobieranie raportów HTML, JSON, MD i PDF korzysta z panelu PHONE.
WebView2 ma włączoną obsługę pobieranych plików. Natywne okna dialogowe
wybierają foldery i miejsca zapisania kopii oraz pakietu TRANSFER.

BEZPIECZEŃSTWO
Nie kopiuj aktywnej bazy ani całego katalogu aplikacji między urządzeniami.
Przywracanie pojedynczego SQLite zastępuje bazę PC (po stworzeniu kopii);
TRANSFER ZIP bezpiecznie scala dokumenty. Przed pierwszym testem zrób kopię.
Analizy porównawcze tylko czytają zapisane wyniki, bez ich przeliczania.

W paczce:
  Sora.exe — prawdziwa aplikacja Windows z oknem WebView2
  _internal/ — wymagane biblioteki; nie usuwaj
  TEST_OK.json — test zasobów panelu, silnika, API i natywnego adaptera
  TEST_GUI_WYMAGANY.txt — przypomnienie o teście na interaktywnym Windows

UWAGA: GitHub Actions testuje uruchomienie rzeczywistej kontrolki
QtWebEngine z paczki EXE po rozpakowaniu. Test bez interaktywnego pulpitu
nie potwierdza jednak wszystkich przycisków. Po instalacji sprawdź
wybór folderu, analizę jednego artykułu, porównania i TRANSFER ZIP.
Pobranie i skompilowanie EXE nie jest jeszcze pełnym testem interfejsu.
  SILNIK_PHONE_PC.json — zgodność silnika
