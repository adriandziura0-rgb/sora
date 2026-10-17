/* Sora: odzyskiwanie po dużych folderach; tylko UI, bez zmian SQLite/CORE. */
(() => {
  'use strict';
  const limit = 1800 * 1024, maxFile = 2 * 1024 * 1024;
  const $ = id => document.getElementById(id);
  const host = $('operationProgress');
  if (!host || typeof dodajFolderZHandle !== 'function' || typeof importujPlikiDoBazy !== 'function') return;
  const actions = document.createElement('div');
  actions.id = 'soraImportRecoveryActions';
  actions.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-top:10px';
  actions.innerHTML = '<button type="button" id="soraImportCancel" class="secondary">Anuluj</button>' +
    '<button type="button" id="soraImportDatabase" class="secondary" hidden>Dodaj folder do bazy</button>' +
    '<button type="button" id="soraImportClose" class="secondary" hidden>Zamknij komunikat</button>';
  host.append(actions);
  const cancel = $('soraImportCancel'), database = $('soraImportDatabase'), close = $('soraImportClose');
  let pending = null, cancelled = false, scanning = false, token = 0;
  const originalStart = pokazPostepOperacji, originalDone = zakonczPostepOperacji;
  const originalError = bladPostepuOperacji, originalScan = zbierzPlikiZKataloguHandle;
  const originalFolder = dodajFolderZHandle, originalMany = dodajPlikiZFileList;
  const utf8 = text => new TextEncoder().encode(String(text || '')).length;
  function controls({busy=false, toDatabase=false}={}) {
    cancel.hidden = !busy; database.hidden = !toDatabase; close.hidden = busy;
  }
  function dismiss() {
    cancelled = true; pending = null; token += 1;
    host.hidden = true; controls(); ustawZajetoscOperacji(false);
    const status = $('fileLoadStatus');
    if (status) status.textContent = 'Zamknięto komunikat. Zapisana baza dokumentów pozostała bez zmian.';
  }
  function showOversize(entries, bytes) {
    pending = entries; cancelled = false; clearTimeout(timerUkryciaPostepu);
    host.hidden = false; host.classList.add('is-error'); host.classList.remove('is-done');
    const label = $('operationProgressLabel'), value = $('operationProgressValue');
    const detail = $('operationProgressDetail'), bar = $('operationProgressBar');
    if (label) label.textContent = 'Folder zbyt duży do jednej analizy';
    if (value) value.textContent = 'wybierz działanie';
    if (bar) bar.removeAttribute('value');
    if (detail) detail.textContent = 'Wybrano około ' + Math.round(bytes/1024) +
      ' KB. Limit pojedynczej analizy: 1800 KB. Nic nie usunięto. Dodaj dokumenty do bazy po jednym pliku albo zamknij komunikat.';
    ustawZajetoscOperacji(false); controls({toDatabase:true});
  }
  const inputSize = () => utf8($('textInput')?.value || '');
  const supported = entry => {
    const f = entry.file;
    return f && typeof f.name === 'string' && /\.(txt|md|markdown|csv|json|log|html|htm)$/i.test(f.name) &&
      Number(f.size || 0) <= maxFile && !entry.readError;
  };
  pokazPostepOperacji = (...args) => {
    cancelled=false; pending=null; token += 1;
    const value=originalStart(...args);
    const active=args[1]?.zajety !== false && /folder|plik/i.test(args[0] || '');
    controls({busy:active}); return value;
  };
  zakonczPostepOperacji = (...args) => { originalDone(...args); controls(); };
  bladPostepuOperacji = (...args) => { originalError(...args); controls(); };
  zbierzPlikiZKataloguHandle = async (handle,prefix='',onScan=null) =>
    originalScan(handle,prefix,(count,path)=>{
      if(cancelled) throw new Error('Anulowano skanowanie folderu.');
      onScan?.(count,path);
    });
  dodajFolderZHandle = async handle => {
    if(scanning) return;
    scanning=true;
    const progress=pokazPostepOperacji('Skanowanie folderu',{wartosc:null, szczegol:'Sprawdzam rozmiar plików…'});
    const own=token;
    try {
      const entries=await zbierzPlikiZKataloguHandle(handle,handle.name||'',(count,path)=>{
        aktualizujPostepOperacji(progress,{tekstWartosci:count+' pl.',szczegol:'Sprawdzam: '+path});
      });
      if(cancelled||own!==token) return;
      const accepted=entries.filter(supported);
      if(!accepted.length) return await originalFolder(handle,entries);
      const total=accepted.reduce((sum,entry)=>sum+Number(entry.file.size||0),0)+inputSize();
      if(total>limit) {showOversize(accepted,total);return;}
      return await originalFolder(handle,entries);
    } catch(e) {
      if(!cancelled) {
        const current=pokazPostepOperacji('Błąd wyboru folderu',{wartosc:0});
        bladPostepuOperacji(current,'Nie udało się wczytać folderu',e?.message||'Błąd skanowania');
      }
    } finally {scanning=false;}
  };
  dodajPlikiZFileList = async (fileList,preserve=false,description='') => {
    const list=Array.from(fileList||[]).filter(file=>supported({file}));
    const size=list.reduce((sum,file)=>sum+Number(file.size||0),0)+inputSize();
    if(size>limit) {
      showOversize(list.map(file=>({file,relativePath:(preserve&&file.webkitRelativePath)||('Pliki/'+file.name)})),size);
      return;
    }
    return originalMany(fileList,preserve,description);
  };
  cancel.addEventListener('click',dismiss);
  close.addEventListener('click',dismiss);
  database.addEventListener('click',async()=>{
    if(!pending?.length||importBazyAktywny)return;
    const entries=pending; pending=null; host.hidden=true; controls();
    const panel=$('databasePanel'); if(panel)panel.open=true;
    try{await importujPlikiDoBazy(entries);}
    catch(e){ustawStatusBazy(e?.message||'Nie udało się dodać folderu do bazy.',true);}
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&host.classList.contains('is-error')&&!host.hidden)dismiss();
  });
})();