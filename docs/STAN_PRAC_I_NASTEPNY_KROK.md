# STAN PRAC I NASTĘPNY KROK — Drogowskazy SORA — analizy artykułów

**Utworzono:** 2026-10-17 • **TASK_ID:** `SORA-AUDYT0-001` • **Status:** `AUDYT / DALSZE TESTY NIEURUCHOMIONE`  
**Repozytorium:** https://github.com/adriandziura0-rgb/sora  
**HEAD kodu sprawdzany PRZED dodaniem dokumentacji:** `main` @ `28f5b698105e522c7d2658776a2382f46bc1e7b9`. Ten SHA jest **punktem odczytu**, nie dowodem najnowszego działającego produktu.  
**Standard uniwersalny:** [UNIWERSALNY STANDARD v1.0](https://github.com/adriandziura0-rgb/przewijarka-app/blob/main/docs/UNIWERSALNY_STANDARD_PRACY_I_KONTYNUACJI_v1_0.md). Dodatkowo obowiązuje lokalny `AGENTS.md`; MASTER LIVE tylko w odpowiedniej domenie.

## 1. Co sprawdzono i co wiadomo

`main` w repozytorium nie jest aktywną gałęzią rozwojową. Ostatni zweryfikowany kod produktu wskazany w planie to **1.2.17** na gałęzi `sora-full-html-snapshot-1.2.17-20261016`, commit `67f48a45a79c30e8e22e8a3cb6c2426685566b42`. Odrębna gałąź dokumentacyjna: `sora-plan-prac-20261016`.

**Dowody i dokumentacja:** [Audyt-0 — DAWCA/ODBIORCA/CLEAN](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/AUDYT_0_SORA_1_2_17_DAWCA_ODBIORCA_CZYSTOSC_2026-10-16.md), [plan A1–A5](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/PLAN_PRAC_I_STAN_SORA_2026-10-16.md), [lokalne zasady](https://github.com/adriandziura0-rgb/sora/blob/sora-plan-prac-20261016/ZASADY_PRACY_SORA_AUDYT_DAWCA_ODBIORCA_CZYSTOSC.md).

## 2. Stan zadania

- **Zakończone/dowiedzione:** Audyt statyczny 11 ścieżek zapisany; poprzednie CI Android/Windows dla 1.2.17 zielone. **Bez nowych testów odtwarzających i bez fixu.**
- **Otwarte / BLOKADA:** Wg audytu: podwójny skan folderu; niejednoznaczny model identycznej treści w dwóch folderach; cykl żądań cytatów A→B→A; niepełne listy 12/60.
- **Testy uruchomione w tej operacji:** **ŻADNE**; prace dotyczą dokumentacji, nie są wdrożeniem aplikacji.
- **DAWCA → ODBIORCA:** do potwierdzenia na rzeczywistym torze podanym w kroku poniżej; nie udawać, że wszystkie ogniwa już sprawdzono.
- **Kolizje i CLEAN:** istniejące hipotezy/raporty trzeba prześledzić do SHA i testu; żadnego kasowania `OLD` ani automatycznej przebudowy.
- **CORE, baza, historia, program:** **nietknięte**. Nie nadpisano SQLite, schematu, par wyników ani skryptów produktu.

## 3. Jeden następny krok — zaczynać TUTAJ

**Nie rozpoczynać A3 ani refaktoru. Na kopii/syntetycznych danych wykonać **T01: licznik skanów importu**; potem T02 duplikat treści A/B i decyzja semantyczna, następnie T03 cytaty A→B→A; reużyć dotychczasowy audyt, nie odtwarzać go od początku.**

**Kryterium GO/NO-GO:** T01–T03 mają logi PASS/FAIL i minimalny plan. Zmiana schema SQLite tylko po osobnej decyzji i rollback.

**Punkt powrotu:** ostatni potwierdzony commit **kodu aplikacji** i oddzielna spójna kopia danych użytkownika przed przyszłą zmianą; nie cofać zapisanej historii. Bez wskazanego testu i kopii nie wdrażać poprawki.

## 4. Zasada kontynuacji bez powtórzeń

Przy następnej rozmowie przeczytać **ten rejestr → lokalny AGENTS.md → wskazany plan/audyt → HEAD/zmienione pliki**. Zmienić status dopiero po wykonanym zadaniu i wyniku testu. Jeżeli SHA aplikacji się nie zmienił, **nie ponawiać całego audytu**: sprawdzić tylko konkretną lukę lub nowy dowód. Każde kolejne wykonane zadanie aktualizuje wpis lub dopisuje nowe TASK_ID, nie tworzy konkurencyjnego `PLAN_FINAL_2`.

## 5. Szablon wpisu kończącego następny test

```text
TASK_ID:
KOD: repo / branch / SHA / wersja:
DAWCA → ODBIORCA: dowód na obu końcach:
DIAGNOZA: fakt / hipoteza / niezweryfikowane:
CLEAN: stare/nowe implementacje, zależności, brak nowej duplikacji:
TESTY: PASS / FAIL / BLOCKED / NOT_RUN + log:
ZMIANY: (brak lub diff, osobny commit):
DANE / CORE: stan przed/po, backup:
DECYZJA: GO / NO-GO / ROLLBACK:
NASTĘPNY JEDEN KROK:
```

**Uwaga:** ten dokument jest początkową migawką wiedzy, nie automatycznym monitoringiem GitHuba. Każda kolejna osoba/asystent musi zweryfikować faktyczny branch, kod i datę przed aktualizacją.
