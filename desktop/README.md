DROGOWSKAZY SORA — APLIKACJA NA WINDOWS 10/11 (64-bit)

Rozpakuj cały ZIP. Otwórz folder Sora i uruchom Sora.exe.
Zachowaj folder _internal obok programu. Python i przeglądarka nie są potrzebne.

Natywne okno: Dokument, Wynik analizy, Baza dokumentów, Porównania,
Ta sama sprawa, Kontrola jakości (benchmark i GOLD), Raport i eksport.
Wyniki mają czytelne karty wypowiedzi, aktorów i źródeł oraz fragmenty tekstu.
Widok Ekspert udostępnia sekcje silnika i sygnały P0.
Raport można zapisać jako Markdown, PDF lub JSON.
Foldery są dodawane do trwałej kolejki, duplikaty rozpoznaje wspólny silnik.

Silnik jest pobierany bez zmian z zasobu aplikacji Android w tym repozytorium.
SILNIK_PHONE_PC.json zawiera odcisk. TEST_OK.json opisuje testy gotowego EXE.
PODGLAD.png przedstawia rzeczywiste okno z testu Windows.

Dane PC są przechowywane w %LOCALAPPDATA%\DrogowskazySoraPC.
Aktualizacja programu nie usuwa tej bazy. Zamknięcie kończy rozpoczętą pracę.
Kopia SQLite używa spójnego mechanizmu kopii bazy.
Przywrócenie sprawdza schemat, silnik i integralność; zachowuje poprzednią bazę.
Przywrócenie zastępuje bazę — nie scala rekordów dwóch urządzeń.
Wersjonowany transfer ZIP PHONE↔PC ze scalaniem nie jest jeszcze wdrożony.
Nie kopiuj aktywnej bazy ani katalogu aplikacji między urządzeniami.
