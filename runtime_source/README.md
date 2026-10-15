# Drogowskazy V4.5.10 APK CLEAN

**Build:** `4.5.10-apk-clean-background-20261006`

Ta paczka jest przeznaczona do aplikacji **Drogowskazy Sora APK**. Nie wymaga Termuxa.

## Co zawiera

- analizator i interfejs Drogowskazy,
- trwałą bazę SQLite,
- trwałą kolejkę importu dokumentów,
- automatyczne wznowienie pozycji `processing` po ponownym uruchomieniu backendu,
- porównania 2–10 grup/redakcji,
- moduł „Ta sama sprawa” dla 2–10 redakcji,
- autosave interfejsu,
- analizę po stronie lokalnego serwera w APK.

## Ważne

APK uruchamia własny Python 3.13/Flask na `127.0.0.1:5433`. Nie uruchamiaj żadnych skryptów Termuxa — w tej wersji ich nie ma.

Przy aktualizacji projektu APK zachowuje istniejącą bazę użytkownika. Baza dołączona do ZIP-a służy jako baza startowa przy pierwszej instalacji projektu.

Dla stabilnej pracy w tle ustaw aplikacji **Drogowskazy Sora** tryb baterii **Bez ograniczeń**. Android może zatrzymać usługę po ręcznym „Wymuś zatrzymanie”.


## V4.5.12 — kontynuacja po restarcie
Po ponownym uruchomieniu wznawiane są wyłącznie rekordy `processing`. Rekordy `done` nie są ponownie analizowane. Pasek postępu korzysta z trwałych liczników SQLite, więc nie wraca do zera po odświeżeniu strony. Ręczna analiza tekstu nie uruchamia się już automatycznie przy starcie.
