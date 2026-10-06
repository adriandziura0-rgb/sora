# Drogowskazy Sora — Android APK bez Termuxa

To repozytorium buduje prawdziwą aplikację Android (`APK`), która uruchamia lokalny silnik Drogowskazów bez Termuxa.

## Jak działa

1. Instalujesz APK z GitHub Actions.
2. Przy pierwszym uruchomieniu wybierasz swój ZIP `DROGOWSKAZY_PHONE_ANDROID_...zip`.
3. Aplikacja bezpiecznie kopiuje projekt do prywatnej pamięci Androida.
4. Wbudowany Python (Chaquopy) uruchamia `app.py` na `127.0.0.1:5433`.
5. Interfejs otwiera się w zwykłej przeglądarce, więc wybór folderów działa tak jak w wersji Termux.
6. Foreground Service + WakeLock pilnuje pracy po wygaszeniu ekranu i podczas przechodzenia do innych aplikacji.

Przy późniejszym wgraniu nowszego ZIP-a aplikacja zachowuje obecną `data/drogowskazy.sqlite3`, żeby aktualizacja kodu nie skasowała danych użytkownika.

## Budowanie

Workflow `.github/workflows/build-apk.yml` uruchamia się automatycznie po pushu do `main` i można go też uruchomić ręcznie w **Actions → Build Android APK → Run workflow**.

Gotowy plik znajduje się w artefakcie **Drogowskazy-Sora-APK** jako `Drogowskazy-Sora-debug.apk`.

## Wymagania telefonu

- Android 7.0 (API 24) lub nowszy.
- Architektura ARM64 (`arm64-v8a`).
- Dla najpewniejszej pracy w tle ustaw dla aplikacji **Bateria → Bez ograniczeń**.

## Bezpieczeństwo danych

- Program nasłuchuje wyłącznie na `127.0.0.1`, więc serwer nie jest wystawiany do sieci lokalnej ani Internetu.
- ZIP jest rozpakowywany z ochroną przed `Zip Slip` oraz limitem liczby i rozmiaru plików.
- Baza użytkownika pozostaje w prywatnym katalogu aplikacji.


## Bezpieczna aktualizacja runtime

Od wersji APK **1.1.0** aktualizacja ZIP-a najpierw zatrzymuje lokalny serwer i – jeśli runtime udostępnia odpowiedni hook – czeka na zakończenie aktywnego workera kolejki SQLite. Dopiero potem podmieniane są pliki projektu. Rekordy pozostające w stanie `processing` są wznawiane po ponownym uruchomieniu runtime.
