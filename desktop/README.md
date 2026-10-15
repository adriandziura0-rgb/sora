DROGOWSKAZY SORA — WINDOWS 10/11 64-BIT
NATYWNY Sora.exe, ORYGINALNY PANEL TELEFONU, BEZ PYTHONNET I QT

URUCHOMIENIE
1. Rozpakuj cały ZIP do NOWEGO folderu (nie mieszaj z poprzednimi wydaniami).
2. Otwórz Sora/Sora.exe. Nie przenoś samego EXE; folder _engine jest wymagany.
3. Aplikacja otwiera natywne okno Windows C# z kontrolką Microsoft WebView2.
   To NIE jest karta przeglądarki i NIE jest osobny panel Tkinter.
4. Kliknięcie X albo Alt+F4 CHOWA Sorę do zasobnika obok zegara Windows.
   Backend nadal działa i może zapisywać analizy do SQLite.
   Dwuklik ikony Sory obok zegara lub ponowne uruchomienie Sora.exe
   otwiera istniejące okno zamiast uruchamiać drugi backend.
   Menu ikony: „Zakończ Sorę i zatrzymaj analizę” — to całkowite wyjście.
   Po awarii backendu watchdog uruchamia go ponownie, bez kasowania danych.
   Chwilowy brak odpowiedzi nie zabija pracującego silnika.
5. Wymagany jest Microsoft Edge WebView2 Runtime. Windows 11 zwykle już go ma.
6. Jeśli program nie ruszy, logi są w:
   %LOCALAPPDATA%\\DrogowskazySoraPC\\blad_okna_webview2.txt
   %LOCALAPPDATA%\\DrogowskazySoraPC\\blad_silnika_pc.txt

ARCHITEKTURA
• Sora.exe: samodzielny natywny host C# WinForms + WebView2.
• _engine/SoraSilnik/SoraSilnik.exe: niezmieniony silnik i panel PHONE Flask.
• Oryginalny interfejs HTML/CSS/JS z APK PHONE 1.2.13, nie uproszczona kopia.
• Obie części komunikują się tylko po 127.0.0.1, z prywatną sesją.
• Watchdog kontroluje /api/sora-pc/health (bez skanowania SQLite).
• Praca w zasobniku trwa przy zamkniętym oknie; nie działa podczas uśpienia
  komputera i nie przetrwa całkowitego zamknięcia Windows.
• Po awarii silnika można odczytać wcześniej zapisane wyniki SQLite,
  ale niezapisana w momencie awarii operacja nie jest automatycznie ponawiana.
• Brak tkinter, QtWebEngine i pythonnet / Python.Runtime.dll w uruchamianiu okna.
• Kopie i TRANSFER ZIP wybierają natywne dialogi Windows.

DANE
• Własna baza PC: %LOCALAPPDATA%\\DrogowskazySoraPC\\data\\drogowskazy.sqlite3
• Aplikacja PHONE ma osobną bazę; nie nadpisuj aktywnego pliku SQLite.
• TRANSFER ZIP PHONE → PC i PC → PHONE sprawdza zgodność silnika i schematu,
  tworzy kopię i scala dane. Przed pierwszym testem zachowaj eksport.
• Wydanie PC nie zmienia klasyfikatora, schematu SQLite ani zapisanych analiz.

KONTROLE
• TEST_OK_PRAWDZIWE_OKNO.json i PODGLAD_PRAWDZIWEGO_OKNA.png:
  tworzone WYŁĄCZNIE po inicjalizacji natywnego WebView2, wykonaniu JavaScript
  oraz znalezieniu wszystkich paneli PHONE w rzeczywistym oknie.
• GitHub sprawdza te operacje przed publikacją i powtarza je po rozpakowaniu ZIP.
• Pamiętaj: test na GitHubie nie zastąpi końcowego sprawdzenia na Twoim Windows.

JEŚLI WYSTĄPI BŁĄD
Zachowaj katalog danych. Prześlij blad_okna_webview2.txt lub
blad_silnika_pc.txt. Nie odinstalowuj telefonu ani nie czyść baz danych.

PORZĄDKI KODU — SORA CLEAN, ETAP 2
Ta paczka jest budowana wyłącznie z natywnego hosta C# WebView2 i backendu PHONE.
Historyczne okna Tkinter, Qt/pywebview, stare skrypty budowania i powiązane testy
nie są częścią bieżących źródeł. Zachowano raportowanie PHONE ↔ PC, testy
sesji localhost, SQLite, GOLD i TRANSFER. Bez zmian interfejsu i danych.

SORA 1.2.14 CLEAN
Instalacyjny ZIP nie zawiera plików PDB, dokumentacji bibliotek WebView2
ani testowych zrzutów okna. Są dostępne oddzielnie w artefakcie
Sora-WINDOWS-DIAGNOSTYKA danego przebiegu GitHub Actions.

SORA 1.2.15 — poprawka A1. Porównania i eksporty nie pokazują starych danych
po zmianie wyboru lub błędzie HTTP; backend PHONE/PC bez zmian.

SORA 1.2.16 A2: eksport pojedynczego zapisanego artykułu tylko z potwierdzonego
wyniku SQLite; brak automatycznego ponownego przeliczenia podczas eksportu.
