# Drogowskazy Sora PC — natywna aplikacja Windows

Rozpakuj cały ZIP i uruchom Sora.exe. Pozostaw folder _internal obok EXE.
Nie musisz instalować Pythona, używać pliku BAT ani otwierać przeglądarki.
Windows 10/11, 64-bit. Wydanie nie ma podpisu wydawcy.

Interfejs jest natywny (Tk): tekst i analiza, sugestie, raport, import plików
oraz folderów z podfolderami, lista zapisanych dokumentów, wynik zbiorczy,
porównanie 2–10 grup/redakcji, lista wspólnych tematów, eksport JSON/TXT
i spójna kopia SQLite. Podwójne kliknięcie dokumentu otwiera zapisany wynik.
Widok wyników zawiera tabelę pól i pełną treść zaznaczonego pola.

Silnik nie jest przepisywany: EXE zawiera dokładnie drogowskazy-runtime.zip
używane przez APK w tym samym commicie repozytorium Sora. Reguły, wiedza,
analizator, kolejka i schemat SQLite są wspólne. PC wywołuje ten kod lokalnie,
bez uruchamiania serwera HTTP. Test budowy porównuje wyniki tych samych
tekstów z runtime telefonu i adaptera PC, pomijając tylko identyfikatory
uruchomienia i znaczniki czasu. To weryfikacja silnika, nie test fizycznego telefonu.

Dane są w %LOCALAPPDATA%\DrogowskazySoraPC\data\drogowskazy.sqlite3.
Aktualizacja EXE ich nie usuwa. Stan edytora zapisuje się w tym samym katalogu.
Baza telefonu pozostaje oddzielna. Nie kopiuj otwartej bazy między urządzeniami.
W tym wydaniu nie ma scalania PHONE ↔ PC ani importu ZIP TRANSFER.
Plik SILNIK_PHONE_PC.json podaje odcisk silnika oraz schemat bazy.

Analiza importu trwa po zminimalizowaniu okna. Zamknięcie programu czeka
na zakończenie kolejki. Wymuszone zamknięcie pozostawia rekordy w trwałej
kolejce do wznowienia po starcie. Zakończone rekordy nie są liczone ponownie.
Komputer musi pozostać włączony i nieuśpiony.

Natywne menu nie odtwarza wszystkich ekranów eksperckich HTML telefonu.
Oceny benchmarku/Gold i szczegółowe porównanie wybranego wspólnego tematu
nie mają jeszcze osobnych formularzy w PC. Nie zmienia to silnika analizy;
nie należy traktować tego wydania jako pełnej zgodności wszystkich ekranów.
