# SORA 1.2.13 — CLEAN, etap 1: aktualizacja bez utraty danych

Podstawa: `acac7c0cedaa677e7d9bb1da27570870eccb6405`, poprzedni zielony build Android i Windows.

- Identyfikator wdrożonego programu: `versionName` + SHA-256 zainstalowanego w APK `drogowskazy-runtime.zip`.
- Test regresji: identyczny numer wersji, zmieniony ZIP aplikacji, poprzednio gotowe dane niezmienione; uszkodzony ZIP ma zostać odrzucony.
- Nowe wydanie na Androidzie: `versionCode=16`, `versionName=1.2.13`. Obecny certyfikat podpisywania i applicationId pozostają niezmienione.
- Workflow Windows reaguje też na zmianę wbudowanego runtime'u i oznaczenia wydania; wspólny silnik PHONE ↔ PC nadal jest sprawdzany testami.
- Bez zmian w klasyfikatorze, schemacie SQLite, danych użytkownika, kodzie pobierania ani plikach starego hosta PC.
- Przed aktualizacją użytkownika: kopia TRANSFER/SQLite. Nie odinstalowywać starego APK.
- Do uznania etapu za zakończony wymagane zielone Android E2E + Windows na tym samym commit SHA i aktualizacja rzeczywistego urządzenia z zachowaniem bazy.

Etap 2: dopiero po zakończeniu testów, sprawdzić i wycofać nieużywane hosty Tk/Qt z bieżącego kodu.
