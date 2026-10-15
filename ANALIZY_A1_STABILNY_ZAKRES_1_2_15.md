# SORA 1.2.15 — analizy A1: zabezpieczenie przed przestarzałymi wynikami

Podstawa: CLEAN 1.2.14, commit 2f4f1b9037d2d352b57ce19b34430ceea0c3fc19.

Wdrożenie tylko w `runtime_source/static/app.js` i `runtime_source/static/same-story-mobile.js`.

- Dwa foldery/redakcje: przed nową odpowiedzią stary wynik i eksport są unieważniane.
- Jedna sprawa: analogicznie, z dodatkową kontrolą `topic_id` i aktualnie wybranych redakcji.
- Poprzednie zapytania są anulowane `AbortController`; spóźnione odpowiedzi nie nadpisują nowej analizy.
- Żądanie anulowane nie jest fałszywie oznaczane jako awaria połączenia z backendem.
- Po HTTP 404/500 i zmianie wyboru panel wyniku jest czyszczony. Nie można pobrać starego JSON.
- Karty telefoniczne wymagają zgodności tematu **oraz wszystkich wybranych redakcji**.
- `tools/test_scope_integrity.mjs`: dynamiczne testy JavaScript obejmujące stale, HTTP 4xx/5xx, anulowanie, niedopasowany temat i brak starego eksportu.
- Nowa wersja Android 1.2.15, `versionCode=18`. Wymagane testy obu buildów, GOLD i TRANSFER.

Nie zmieniono `clean_core/**`, schematu SQLite, logiki importu, klasyfikatora, silnika PC ani źródeł dokumentów. Zmiany w wbudowanym ZIP dotyczą **tylko dwóch plików JavaScript** z 66; hash obrazu runtime: `126e057e18204aeef0592eaad894ad08026b939d3dcccd14ec440dbb37f86125`.

Rzeczywista baza użytkownika nie jest zmieniana; testy używają osobnych danych syntetycznych. Przed aktualizacją zachować kopię TRANSFER, instalować APK na poprzedniej wersji bez odinstalowywania.