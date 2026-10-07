(() => {
  if (window.__drogowskazyNativeInstalled || !window.DrogowskazyAndroid) return;
  window.__drogowskazyNativeInstalled = true;
  const bridge = window.DrogowskazyAndroid;
  const waiting = new Map();
  let sequence = 0;
  const parse = raw => {
    const result = JSON.parse(raw);
    if (result.error) throw new Error(result.error);
    return result;
  };
  const handle = item => item.kind === 'file' ? {
    name: item.name, kind: 'file',
    async getFile() {
      if (Number(item.size) > 2 * 1024 * 1024 || !/\.(txt|md|markdown|csv|json|log|html|htm)$/i.test(item.name)) {
        const skipped = new File([], item.name);
        Object.defineProperty(skipped, 'size', {value: Number(item.size) || 0});
        return skipped;
      }
      const encoded = parse(bridge.readFile(item.uri)).base64;
      const raw = atob(encoded);
      const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
      return new File([bytes], item.name);
    }
  } : {
    name: item.name, kind: 'directory',
    async *entries() {
      const {entries} = parse(bridge.listChildren(item.uri));
      for (const child of entries) yield [child.name, handle(child)];
    }
  };
  window.showDirectoryPicker = () => new Promise((resolve, reject) => {
    const id = String(++sequence);
    waiting.set(id, {resolve, reject});
    bridge.pickFolder(id);
  });
  window.__drogowskazyFolderResult = (id, selected) => {
    const request = waiting.get(String(id));
    if (!request) return;
    waiting.delete(String(id));
    if (selected && selected.error) request.reject(new Error(selected.error));
    else if (!selected) request.reject(new DOMException('Anulowano wybór folderu.', 'AbortError'));
    else request.resolve(handle({...selected, kind: 'directory'}));
  };
  window.print = () => bridge.printPanel();
  const databaseDownload = document.getElementById('downloadDatabaseBtn');
  if (databaseDownload && typeof bridge.downloadDatabase === 'function') {
    // Systemowy zapis SQLite nie rozpoczyna nawigacji panelu.
    databaseDownload.addEventListener('click', event => {
      event.stopImmediatePropagation();
      bridge.downloadDatabase();
    }, {capture: true});
  }
  for (const [id, method] of [['appSettingsBtn', 'openSettings'], ['restoreDatabaseBackupBtn', 'restoreDatabaseBackup']]) {
    const button = document.getElementById(id);
    if (button && typeof bridge[method] === 'function') {
      button.hidden = false;
      button.addEventListener('click', () => bridge[method]());
    }
  }
})();
