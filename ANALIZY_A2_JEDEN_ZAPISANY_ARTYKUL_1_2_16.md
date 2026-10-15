# A2 SORA 1.2.16 — analiza pojedynczego zapisanego artykułu

Baza: `sora-full-analizy-a1-20261015` (`b8c6c8a`), bez zmian klasyfikatora, tabel SQLite i TRANSFER.

## Wdrożono
- Karta „Dokument z SQLite — tożsamość analizy i dowody”: ścieżka, ID, SHA-256 treści, `analysis_run_id`, `analyzed_at`, `app_version`, przykładowe karty relacji/cytatów i informacja „X z Y”. Pokazuje, czy fragment istnieje dosłownie w zapisanym tekście; nie uznaje automatycznych oznaczeń za zweryfikowane fakty.
- JSON/Markdown/PDF istniejącego artykułu używa tylko zapisanego wyniku pobieranego `GET /api/baza/dokument/<id>/wynik`; nie korzysta z `POST /api/raport`.
- Każdy eksport weryfikuje ID dokumentu, treść i SHA, `updated_at`, `analysis_run_id` oraz pełną zgodność obiektu zapisanego wyniku z tym na ekranie.
- Zmiana tekstu na ekranie, aktualizacja analizy po otwarciu albo przełączenie dokumentu podczas zapytania powodują czytelną odmowę eksportu.
- Stan dokumentu zapisywany jest w lokalnej sesji (bez duplikowania treści w dodatkowym polu) i weryfikowany po przywróceniu.
- Test `tools/test_article_identity.mjs` sprawdza eksport bez POST i odmowę dla różnych rodzajów nieaktualnego wyniku.

## Granice A2
- Wyświetlany podgląd pokazuje maksymalnie 8 kart; wszystkie pozostają w sekcjach analitycznych. Pełny przegląd dowodów i śledzenie P0–P5 we wszystkich grupach to dalsze A3–A4.
- Raport Markdown jest dokładnie tym, co zachowano w analizie; jeśli dokument nie zawiera Markdown, eksport JSON/PDF jest nadal możliwy, a interfejs informuje o braku zapisanej wersji Markdown.
- Testy 257/257 GOLD, Android WebView/SAF, Windows WebView2, transfer i zachowanie SQLite są wymagane przed uznaniem instalatora za zweryfikowany.

## Testy krytyczne
1. Otwórz zapisany artykuł; bez zmiany tekstu zapisz raport i pełny JSON. `wynik_analizy` musi być identyczny z `GET /api/baza/dokument/<id>/wynik`.
2. Zrestartuj backend oraz aplikację, przywróć sesję i wykonaj ten sam eksport. Nie może dojść do `POST /api/raport`.
3. Zmień jedno słowo w polu tekstu: odmowa eksportu bez kasowania danych.
4. Ponownie przeanalizuj dokument w osobnej sesji: stara karta odmawia eksportu i prosi o ponowne otwarcie.
5. W trakcie zapytania wybierz inny artykuł: stara odpowiedź nie może podmienić nowej analizy.
