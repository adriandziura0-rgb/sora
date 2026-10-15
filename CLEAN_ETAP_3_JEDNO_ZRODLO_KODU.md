# SORA CLEAN — etap 3: jeden kanoniczny kod bez łatek

- Zastosowano dokładnie wcześniej zaliczony runtime 1.2.13.
- Jednorazowa migracja z `94f44d2` → `e2a0025` skopiowała 66 plików programu do `runtime_source/`.
- Manifest przechowuje hash każdego pliku i metadane ZIP. `tools/build_runtime_from_sources.py` generuje archiwum bajt w bajt identyczne z działającą wersją etapu 2.
- **Zamrożony runtime SHA-256:** `bee4fd3c9f67131e8d49cbf2789bce46fdfcde25610aeeb4e3566529e44cffd8`
- **Zamrożona tożsamość CORE/TRANSFER:** `acd41f077f31df1d1f7bfa6584f529d22ca886a2a0faaef17561f1493288032e`.
- Usunięto historyczny ZIP źródłowy, 2 skrypty tekstowych łatek i 11 kopii modułów z `tools/overview_assets/`.
- W CI obu platform generowany jest ZIP z kanonicznych plików, a test `tools/test_canonical_runtime.py` musi potwierdzić identyczność bajtów.
- Nie wykonano zmian w klasyfikatorze, schemacie SQLite, plikach danych ani TRANSFER.
- Dopiero po dwóch zielonych buildach Android/Windows **tego samego commitu** etap CLEAN 3 jest zaliczony.

## Rozwój kolejnych funkcji
Zmiany `runtime_source/*` są celowo blokowane do czasu jawnej aktualizacji manifestu i kontrolowanych
testów. Nie obchodzić kontroli SHA, nie dodawać potajemnych łatek po stronie CI.
