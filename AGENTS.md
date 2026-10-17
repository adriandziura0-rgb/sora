# AGENTS.md — bezwzględne zasady pracy przy tym projekcie

**Zakres:** zadania wykonywane przez ludzi i asystentów programistycznych. **Język opisów, interfejsu, raportów i komunikatów: polski.**

## Kolejność pracy (nie pomijać)
1. **AUDYT**: najpierw potwierdź repozytorium, gałąź, commit, wersję, reprodukcję problemu, wpływ na inne funkcje i istniejące testy. Nie zmieniaj kodu zanim zrozumiesz przyczynę.
2. **DAWCA → ODBIORCA**: prześledź każdą istotną daną od źródła/DOM/pliku, przez parser, normalizację, transport, odbiór, walidację, zapis w bazie, obliczenia, API, do widoku/eksportu. Weryfikuj rzeczywisty odbiór i zapis, nie tylko nadawanie.
3. **KOLIZJE I RÓWNOLEGŁOŚĆ**: sprawdź unikalne identyfikatory, deduplikację, transakcje, wyścigi, stare odpowiedzi, retry, brakujące pola, zmianę kolejności, restart, uśpienie i przerwanie połączenia.
4. **CZYSTOŚĆ KODU**: zidentyfikuj OLD/legacy, nieużywane pliki/funkcje, nakładające się implementacje, martwe ścieżki, prowizoryczne łatki, zbędne zależności i działania. Usuwaj wyłącznie po potwierdzeniu braku użycia, testach i zabezpieczeniu historii. Naprawiaj u źródła, nie doklejaj równoległych silników.
5. **OCHRONA CORE I BAZY**: nie ruszaj sprawdzonych kolektorów, parserów, transportu, schematu SQLite, historii ani identyfikatorów bez udokumentowanego dowodu konieczności. Analityka czyta spójne snapshoty, a swoje oceny zapisuje osobno. Nigdy nie podmieniaj aktywnej bazy SQLite.
6. **KONTRAKT I PLAN**: zapisz cel, wersję przed/po, pliki do zmiany, zakres i wpływ, dowody, plan testów, backup i rollback. Zmiana możliwie najmniejsza, w izolacji od obszarów stabilnych.
7. **TESTY I PORÓWNANIE**: jednostkowe, integracyjne, migracje, E2E, regresja, import/eksport, utrata połączenia, wielokrotne zapisy i realne testy środowiska docelowego (telefon/Windows), gdy dotyczy. Oddziel wynik symulowany od pomiaru na urządzeniu.
8. **WYDANIE CLEAN**: nie dokładaj starego kodu, przypadkowych plików, sekretów, artefaktów kompilacji ani baz użytkownika. Udokumentuj commit, wersję, testy, ograniczenia, punkt cofnięcia i niezweryfikowane obszary.
9. **ODBIÓR I RAPORT**: przedstaw co potwierdzono, co zmieniono, co zostało nietknięte, które testy wykonano, jakie dane sprawdzono i czy istnieje ryzyko regresji. Bez dowodu nie pisz „naprawione”, „przetestowane” ani „działa”.

## Warunki STOP
- Brak potwierdzonej przyczyny błędu lub brak dowodu przepływu dawca→odbiorca.
- Ryzyko usunięcia/nadpisania historii lub migracji bez kopii i procedury odtworzenia.
- Niewyjaśnione duplikaty, różne identyfikatory tego samego obiektu, wyścigi lub znikające zmienne.
- Próba zmiany zamrożonego CORE bez osobnej decyzji i izolowanego testu.
- Zgadywanie brakujących danych (NULL to nie 0; brak potwierdzenia końca to nie status zakończony).
- Test pokazuje uruchomienie, lecz nie dowodzi poprawnego odbioru/zapisu.
- Zmiana miesza niepowiązane funkcje lub nie ma planu cofnięcia.
- Wnioski analityczne ujawniają dane z przyszłości, nie mają proweniencji lub mylą prognozę z faktem.

## Reguły zespołu i AI
- Nie usuwaj projektu, gałęzi, baz, danych testowych i poprzednich działających wersji bez wyraźnej decyzji.
- Nie uruchamiaj niezamówionych refaktorów, automatycznych napraw produkcyjnych ani modyfikacji interfejsu.
- Nie używaj losowego „próbuj aż zadziała” jako metody naprawy; każdy eksperyment ma hipotezę i wynik.
- Nie przedstawiaj kompilacji jako testu E2E; nie dopisuj nieprzeprowadzonych testów.
- Zmiany w istniejącym, działającym obszarze wymagają wyjaśnienia wpływu i regresji.
- Zachowuj kompatybilność baz, identyfikatorów, danych i eksportów PC↔PHONE, jeśli projekt je obsługuje.
- Nowe projekty zaczynaj od tego AGENTS.md i instrukcji współpracy. Nie zakładaj, że GitHub automatycznie dziedziczy ten plik.

## Dokument szczegółowy
- [MASTER zasad dla Przewijak LIVE / warstwy analitycznej](docs/PRZEWIJAK_LIVE_MASTER_ZASADY_PRACY_ANALITYKA_v1_0.md).
- Ten MASTER opisuje specyficzny dla Przewijak LIVE system meczów i zamrożony CORE. **Nie wolno na siłę implementować sportowych elementów w innych projektach.** Zasady audytu, bezpieczeństwa i jakości są wspólne dla wszystkich.

## Profil projektu: Drogowskazy Sora
- W tym repozytorium obowiązują ogólne zasady audytu, jakości, bezpieczeństwa danych i czystości kodu. Sportowe identyfikatory MASTER/SOURCE UID z dokumentu Przewijak LIVE nie są wymaganiami Sory.
- Rozdziel silnik klasyfikacji artykułów, bazę i analizę porównawczą od prezentacji. Zmiany panelu nie mogą po cichu zmieniać klasyfikatora.
- Testuj widok analizy jednego artykułu, jednego folderu, wielu folderów oraz wybranych rekordów, zachowanie danych i przejrzystość wyników.
- Pilnuj wyboru katalogów/SD, importu, SQLite/WAL, limitów żądań, usługi lokalnej i ponownego otwierania Android/Windows.
- Nie zakładaj, że domyślna gałąź main jest najnowszym wydaniem; sprawdź aktywny branch, commit, PR i punkt cofnięcia przed działaniem.
