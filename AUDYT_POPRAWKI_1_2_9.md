# Sora 1.2.9 — poprawki bezpieczeństwa i testy regresji

Prace dotyczą gałęzi PR #3. Nie zmieniono klasyfikatora, pobierania artykułów, schematu SQLite ani formatu TRANSFER.

## Wdrożone poprawki

- **SQLite:** weryfikacja importowanej bazy przed podmianą; przed operacją kopie `drogowskazy.sqlite3`, `-wal`, `-shm` w folderze `data/backup-before-restore-<czas>`. Kopia zostaje zachowana także po udanym przywróceniu.
- **Przerwany restore:** znacznik `data/.restore-pending`; przy kolejnym starcie usługę można uruchomić dopiero po odzyskaniu oryginalnych plików. Nie usuwać tego znacznika ani folderu kopii ręcznie.
- **Android:** usługa sprawdza wersję wbudowanego programu po starcie/aktualizacji APK, zanim ponownie uruchomi Python, zamiast serwować stary panel. Stan uruchomienia jest odświeżany po udanym starcie.
- **Raport:** rzeczywiste liczniki ukończonych analiz bez fikcyjnych zer dla oczekujących/błędów/duplikatów; nazwy wybranych grup są deduplikowane bez rozróżnienia wielkości liter. Ostatnie 12 dokumentów utrzymywane jest w ograniczonej pamięci i sortowane po dacie analizy.
- **Testy:** przypadki błędnej kopii SQLite, zachowania DB/WAL/SHM, symulowanego przerwania przywracania, wybór jednej/dwóch grup, limit zaznaczenia, brak zapisów do bazy, lista ostatnich 12.

## Ograniczenia przed wydaniem

- Nowy raport nadal wykorzystuje `DOCUMENT_DATABASE.iter_completed_results(...)` i **przegląda zapisane ukończone analizy**; nie należy przedstawiać go jako zapytania SQL ograniczonego do wybranych grup. Przy bardzo dużej bazie wymaga to pomiarów i osobnej optymalizacji po audycie metod bazy.
- Kopia bezpieczeństwa bazy DB/WAL/SHM wymaga dodatkowego wolnego miejsca. Nie należy jej usuwać przed sprawdzeniem nowej bazy.
- Test JVM operuje na atrapach Android SQLite i sprawdza przepływ plików, a nie rzeczywistą spójność transakcyjną WAL. Weryfikacja rzeczywistego SQLite jest osobnym testem na Androidzie.
- **PR nie scalać bez potwierdzonego zielonego wyniku Build Android APK i Build Sora Windows native EXE**, a także prób na rzeczywistym telefonie.

## Kontrola wydania

1. Zrób ZIP TRANSFER z poprzedniego wydania i zachowaj go poza aplikacją.
2. Uruchom `python tools/test_project_store.py` po przygotowaniu środowiska JDK i zasobów APK.
3. Uruchom w workflow `python tools/patch_engine_runtime.py`, `python tools/patch_full_database_dashboard.py` i `python tools/test_full_database_overview.py`.
4. Zbuduj APK, sprawdź podpis i wersję. Aktualizuj **na istniejącej instalacji** z zachowaniem danych, bez odinstalowywania.
5. Sprawdź uruchomienie nowego panelu po zamknięciu, ponownym uruchomieniu oraz wymianie APK; na Androidzie sprawdź działanie usługi w tle i po utracie/odzyskaniu internetu.
6. Przetestuj przywracanie nieprawidłowej i prawidłowej bazy, kopiowanie WAL/SHM oraz odzyskiwanie po przerwaniu, najlepiej na danych testowych.
7. Sprawdź porównania jednej, dwóch i dziesięciu grup, usuwanie nieaktualnego widoku przy zmianie zaznaczenia i wygodę ekranu mobilnego.
8. Zbuduj Windows EXE oraz sprawdź zgodność analiz i TRANSFER między PHONE i PC.

Kod w PR jest etapem do testowania. Samo pojawienie się commitów nie potwierdza przejścia CI ani instalacji na telefonie.
