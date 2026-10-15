# Instrukcja — Drogowskazy Sora APK + V4.5.10

1. Zainstaluj `Drogowskazy-Sora-debug.apk`.
2. Otwórz aplikację **Drogowskazy Sora**.
3. Wybierz ZIP `DROGOWSKAZY_RUNTIME_4_5_10_APK_CLEAN.zip`.
4. Poczekaj na komunikat, że projekt został zaimportowany.
5. Naciśnij **Uruchom w tle**.
6. Otwórz Drogowskazy z aplikacji. Backend działa lokalnie pod `127.0.0.1:5433`.

## Praca w tle

Po przekazaniu dokumentów do kolejki SQLite analiza jest wykonywana przez backend. Strona WWW nie musi być stale na pierwszym planie. Jeżeli backend zostanie ponownie uruchomiony, rekordy pozostawione jako `processing` są wznawiane.

Na Samsungu ustaw: **Ustawienia → Aplikacje → Drogowskazy Sora → Bateria → Bez ograniczeń**. Jeżeli dostępna jest lista aplikacji nigdy nieusypianych, dodaj Drogowskazy Sora.

## Aktualizacja bez utraty bazy

W aplikacji wybierz nowszy ZIP projektu. Mechanizm APK zachowuje aktualną `data/drogowskazy.sqlite3`, więc nie trzeba przenosić bazy ręcznie. Mimo tego przed większą aktualizacją warto pobrać kopię bazy z poziomu Drogowskazów.


## V4.5.12 — kontynuacja po restarcie
Po ponownym uruchomieniu wznawiane są wyłącznie rekordy `processing`. Rekordy `done` nie są ponownie analizowane. Pasek postępu korzysta z trwałych liczników SQLite, więc nie wraca do zera po odświeżeniu strony. Ręczna analiza tekstu nie uruchamia się już automatycznie przy starcie.
