DROGOWSKAZY RUNTIME 4.5.11 SAFE UPDATE CLEAN

Zmiana etapu:
- trwała kolejka SQLite pozostaje bez zmian funkcjonalnych,
- dodano bezpieczne zatrzymanie workera przed podmianą ZIP-a przez APK Sora 1.1.0+,
- aktywny zapis może się dokończyć, a rekordy processing zostaną wznowione po restarcie,
- brak zależności od Termuxa.

Do zwykłej pracy używaj jak poprzedniego runtime. Przy aktualizacji wybierz nowy ZIP w Sora.


## V4.5.12 — kontynuacja po restarcie
Po ponownym uruchomieniu wznawiane są wyłącznie rekordy `processing`. Rekordy `done` nie są ponownie analizowane. Pasek postępu korzysta z trwałych liczników SQLite, więc nie wraca do zera po odświeżeniu strony. Ręczna analiza tekstu nie uruchamia się już automatycznie przy starcie.
