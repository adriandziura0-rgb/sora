// T01: test reprodukcyjny SORA 1.2.17 — *celowo czerwony*, jeżeli folder jest skanowany więcej niż raz.
// Uruchomienie: node tools/test_t01_folder_scan.mjs
// Zero zapisu do produkcyjnej bazy/CORE; czyta oryginalne app.js i import-recovery.js z TEGO SAMEGO commita.
// Stan bazowy: trzy pliki, jeden podfolder, getFile() wywołane sześć razy zamiast trzech.
// Akceptacja po poprawce: 3 odczyty, 1 pakiet analizy; duży folder tylko 1 skan, bez automatycznego importu.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../runtime_source/static/app.js', import.meta.url), 'utf8');
const patch = readFileSync(new URL('../runtime_source/static/import-recovery.js', import.meta.url), 'utf8');
const marker = 'async function zbierzPlikiZKataloguHandle(';
const begin = source.indexOf(marker);
const end = source.indexOf('\nasync function otworzFolder(', begin);
assert.ok(begin >= 0 && end > begin && patch.includes('const originalFolder = dodajFolderZHandle'),
  'Zmieniło się API importu: STOP, przeprowadź nowy audyt przed zmianą testu');
const originalFunctions = source.slice(begin, end);

function makeContext() {
  const elements = new Map();
  const handlers = new Map();
  const handedOff = [];
  let done = 0, errors = 0, dbWrites = 0;
  function makeElement(id) {
    return {
      id, hidden: true, open: false, value: '', textContent: '', style: { cssText: '' }, events: {},
      classList: {
        data: new Set(),
        add(x) { this.data.add(x); },
        remove(x) { this.data.delete(x); },
        contains(x) { return this.data.has(x); }
      },
      addEventListener(k, fn) { this.events[k] = fn; },
      removeAttribute() {},
      setAttribute() {},
      click() { return this.events.click?.(); },
      append() { for (const key of ['soraImportCancel','soraImportDatabase','soraImportClose']) {
        elements.set(key, makeElement(key));
      }}
    };
  }
  for (const id of [
    'operationProgress', 'operationProgressLabel', 'operationProgressValue',
    'operationProgressDetail', 'operationProgressBar', 'fileLoadStatus', 'textInput', 'databasePanel'
  ]) elements.set(id, makeElement(id));
  const document = {
    getElementById: id => elements.get(id) || null,
    createElement: () => makeElement('actions'),
    addEventListener: (type, fn) => handlers.set(type, fn)
  };
  const env = {
    document, TextEncoder, clearTimeout: () => {}, timerUkryciaPostepu: 0,
    importBazyAktywny: false, MAKSYMALNY_ROZMIAR_PLIKU: 2 * 1024 * 1024,
    aktualizujPostepOperacji: () => {}, ustawZajetoscOperacji: () => {}, ustawStatusBazy: () => {},
    czyObslugiwanyPlik: f => /\.(txt|md)$/i.test(f.name),
    odczytajPlikTekstowy: async f => ({ name: f.name, text: 'test' }),
    naprawMojibakePolski: s => s, odmienPliki: () => 'pl.',
    onDone: () => { done++; }, onError: () => { errors++; },
    onBatch: xs => handedOff.push(xs),
    onImport: () => { dbWrites++; }
  };
  const actualCode = `
  let pokazPostepOperacji = () => 1;
  let zakonczPostepOperacji = () => env.onDone();
  let bladPostepuOperacji = () => env.onError();
  let dodajPlikiZFileList = async () => {};
  let importujPlikiDoBazy = async () => env.onImport();
  let importBazyAktywny = false;
  let timerUkryciaPostepu = 0;
  let MAKSYMALNY_ROZMIAR_PLIKU = env.MAKSYMALNY_ROZMIAR_PLIKU;
  const document = env.document, TextEncoder = env.TextEncoder, clearTimeout = env.clearTimeout;
  const ustawZajetoscOperacji = env.ustawZajetoscOperacji;
  const aktualizujPostepOperacji = env.aktualizujPostepOperacji;
  const ustawStatusBazy = env.ustawStatusBazy;
  const czyObslugiwanyPlik = env.czyObslugiwanyPlik;
  const odczytajPlikTekstowy = env.odczytajPlikTekstowy;
  const naprawMojibakePolski = env.naprawMojibakePolski;
  const odmienPliki = env.odmienPliki;
  const dodajWielePlikow = async xs => env.onBatch(xs);
  ${originalFunctions}
  ${patch}
  globalThis.runFolder = handle => dodajFolderZHandle(handle);
  `;
  const ctx = { env };
  runInNewContext(actualCode, ctx, { filename: 'SORA-actual-app+import-recovery.js' });
  return { elements, handlers, handedOff, runFolder: ctx.runFolder, state: () => ({ done, errors, dbWrites }) };
}

function folder(name, files, subfolders, counts) {
  return { name, kind: 'directory', async *entries() {
    for (const f of files) yield [f.name, { kind: 'file', getFile: async () => {
      counts[f.name] = (counts[f.name] || 0) + 1;
      return f;
    }}];
    for (const child of subfolders) yield [child.name, child];
  }};
}

const normal = makeContext();
const reads = {};
const nested = folder('Podfolder', [{ name: 'C.md', size: 130 }], [], reads);
const top = folder('Folder', [{ name: 'A.txt', size: 100 }, { name: 'B.txt', size: 200 }], [nested], reads);
await normal.runFolder(top);
assert.equal(normal.handedOff.length, 1, 'Przekazano więcej niż jeden pakiet');
assert.equal(normal.handedOff[0].length, 3, 'Przekazano nieprawidłową liczbę dokumentów');
assert.equal(normal.state().dbWrites, 0, 'Sam wybór małego folderu nie powinien zapisywać SQLite');
assert.equal(normal.state().errors, 0, 'Błąd importu przy małym folderze');
const total = Object.values(reads).reduce((sum, count) => sum + count, 0);
console.log(JSON.stringify({
  test: 'T01_FOLDER_SMALL', documents: 3, expected_file_reads: 3,
  actual_file_reads: total, per_file: reads, handed_off: normal.handedOff[0].length
}, null, 2));

const large = makeContext();
const largeReads = {};
const oversized = folder('DuzyFolder', [{ name: 'X.txt', size: 1900 * 1024 }], [], largeReads);
await large.runFolder(oversized);
assert.equal(largeReads['X.txt'], 1, 'Duży folder powinien zostać odczytany raz');
assert.equal(large.handedOff.length, 0, 'Duży folder nie może zostać przesłany do analizy');
assert.equal(large.elements.get('soraImportDatabase').hidden, false, 'Brakuje bezpiecznej opcji przekazania do bazy');
large.elements.get('soraImportClose').click();
assert.equal(large.elements.get('operationProgress').hidden, true, 'Przycisk Zamknij musi działać');
assert.equal(large.state().dbWrites, 0, 'Zamknięcie bez działania nie może zapisywać bazy');
console.log('PASS: oversized guard, Close, no SQLite writes');

if (total !== 3) {
  console.error('FAIL T01: podwójny skan plików — 3 oczekiwane odczyty, ' + total + ' rzeczywistych');
  process.exitCode = 1; // celowy czerwony test regresyjny przed naprawą
} else {
  console.log('PASS T01: jeden skan każdego pliku — poprawka może przejść regresje');
}
