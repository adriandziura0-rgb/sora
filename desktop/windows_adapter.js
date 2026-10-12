/* Dopasowanie oryginalnego panelu PHONE do natywnego okna Windows. */
(() => {
  'use strict';
  function start() {
    if (window.__soraWindowsBridgeInstalled || !window.pywebview?.api) return;
    window.__soraWindowsBridgeInstalled = true;
    const api = window.pywebview.api;

    function handle(item) {
      if (item.kind === 'file') {
        return {
          name: item.name, kind: 'file',
          async getFile() {
            if (Number(item.size) > 2 * 1024 * 1024) {
              const rejected = new File([], item.name);
              Object.defineProperty(rejected, 'size', {value: Number(item.size)});
              return rejected;
            }
            const response = await api.read_file(item.root, item.path);
            const bytes = Uint8Array.from(atob(response.base64), x => x.charCodeAt(0));
            return new File([bytes], item.name);
          }
        };
      }
      return {
        name: item.name, kind: 'directory',
        async *entries() {
          const entries = await api.list_directory(item.root, item.path);
          for (const child of entries) yield [child.name, handle(child)];
        }
      };
    }

    // Oryginalny kod PHONE obsługuje uchwyty File System Access API.
    // Most zwraca taki sam interfejs, a folder wybiera natywne okno Windows.
    window.showDirectoryPicker = async () => {
      const selected = await api.select_folder();
      if (!selected) throw new DOMException('Anulowano wybór folderu.', 'AbortError');
      return handle(selected);
    };

    const wrap = (id, method, confirmation) => {
      const button = document.getElementById(id);
      if (!button) return;
      button.hidden = false;
      button.addEventListener('click', async event => {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (button.disabled) return;
        if (confirmation && !window.confirm(confirmation)) return;
        button.disabled = true;
        try {
          const result = await api[method]();
          if (!result?.cancelled) {
            window.alert(result?.message || 'Operacja zakończona.');
            if (result?.reload) window.location.reload();
          }
        } catch (error) {
          window.alert('Nie udało się wykonać operacji: ' + (error?.message || error));
        } finally {
          button.disabled = false;
        }
      }, {capture:true});
    };
    wrap('downloadDatabaseBtn', 'backup_database');
    wrap('restoreDatabaseBackupBtn', 'restore_database');

    const container = document.getElementById('databasePanel');
    if (container && !document.getElementById('soraWindowsTransfer')) {
      const panel = document.createElement('div');
      panel.id = 'soraWindowsTransfer';
      panel.style.cssText = 'margin:12px 0;padding:14px;border:1px solid #b9d9e4;border-radius:12px;background:#eaf5fa;color:#293b49';
      panel.innerHTML =
        '<strong>TRANSFER PHONE ↔ PC</strong>' +
        '<p style="margin:8px 0;font-size:.92rem;line-height:1.5">Zgodny pakiet ZIP z walidacją i scalaniem dokumentów. Baza PC pozostaje oddzielna od bazy telefonu.</p>' +
        '<div style="display:flex;flex-wrap:wrap;gap:8px">' +
        '<button type="button" id="soraWindowsTransferExport">Eksportuj na telefon · ZIP</button>' +
        '<button type="button" id="soraWindowsTransferImport">Importuj z telefonu · ZIP</button></div>';
      const summary = container.querySelector('summary');
      if (summary) summary.insertAdjacentElement('afterend', panel);
      else container.prepend(panel);

      for (const [id,method] of [
        ['soraWindowsTransferExport','export_transfer'],
        ['soraWindowsTransferImport','import_transfer']
      ]) {
        const button = document.getElementById(id);
        button.addEventListener('click', async () => {
          if (button.disabled) return;
          button.disabled = true;
          try {
            const result = await api[method]();
            if (!result?.cancelled) {
              window.alert(result?.message || 'TRANSFER zakończony.');
              if (result?.reload) window.location.reload();
            }
          } catch (error) {
            window.alert('Błąd TRANSFER: ' + (error?.message || error));
          } finally {
            button.disabled = false;
          }
        });
      }
    }

    // WebView2 uruchamia dokładnie ten sam HTML/JS/CSS co Android.
    // Niczego nie instalujemy ani nie przekazujemy do zewnętrznej przeglądarki.
    document.body.dataset.soraDesktopWindow = 'true';
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once:true});
  } else start();
  window.addEventListener('pywebviewready', start, {once:true});
})();