/* Niezależne, ręczne porównywanie treści z już zapisanych artykułów. */
(() => {
  'use strict';
  const button = document.getElementById('findSharedContentBtn');
  const status = document.getElementById('sharedContentStatus');
  const output = document.getElementById('sharedContentResults');
  const groupsSelect = document.getElementById('databaseCompareGroups');
  const picker = document.getElementById('databaseComparePanel');
  const modeChoice = document.getElementById('databaseCompareMode');
  if (!button || !output || !status || !groupsSelect) return;

  const html = x => String(x ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[ch]));
  const scope = () => {
    const checked = [...(picker?.querySelectorAll('#databaseCompareGroupList input[data-compare-group]') || [])]
      .filter(el => el.checked && !el.disabled);
    const groups = picker?.querySelectorAll('#databaseCompareGroupList input[data-compare-group]')?.length
      ? checked.map(x => x.dataset.compareGroup || x.value).filter(Boolean)
      : [...groupsSelect.selectedOptions].map(x => x.value).filter(Boolean);
    const mode = modeChoice?.value || 'folder';
    return {groups,mode,key:JSON.stringify([mode,groups])};
  };
  // Widoczne w trybie Użytkownik, nie tylko w narzędziach eksperckich.
  const sharedPanel=document.getElementById('sharedContentPanel');
  const summary=sharedPanel?.querySelector('summary');
  if(summary)summary.textContent='Baza cytatów, wspólne treści i różnice między redakcjami';
  const quoteBar=document.createElement('div');
  quoteBar.className='sora-quote-controls';
  quoteBar.innerHTML='<h3>Cytaty i wypowiedzi z zaznaczonych materiałów</h3>'
    +'<p>Odczytuję zapisane karty „opinia cytowana” i „cytat przypisany”. '
    +'Porównanie identycznego brzmienia wymaga tego samego przypisanego mówcy. '
    +'Nie jest to weryfikacja autentyczności wypowiedzi.</p>'
    +'<button type="button" id="soraFindQuotesBtn" class="secondary strong-action">'
    +'Pokaż bazę cytatów zaznaczonych</button> '
    +'<button type="button" id="soraDownloadQuotesBtn" class="secondary" disabled>'
    +'Pobierz bazę cytatów JSON</button>'
    +'<p id="soraQuotesStatus" role="status" aria-live="polite">Wybierz od 1 do 10 grup i naciśnij przycisk.</p>'
    +'<div id="soraQuotesResults" class="sora-shared-results"></div>'
    +'<hr><h3>Porównanie dosłownych fragmentów artykułów</h3>';
  button.parentNode.insertBefore(quoteBar,button);
  let quotePayload=null, quoteScope=null, quoteBusy=false;
  const quoteBtn=quoteBar.querySelector('#soraFindQuotesBtn');
  const quoteDownload=quoteBar.querySelector('#soraDownloadQuotesBtn');
  const quoteStatus=quoteBar.querySelector('#soraQuotesStatus');
  const quoteResults=quoteBar.querySelector('#soraQuotesResults');
  function clearQuotes(){
    quotePayload=null;quoteScope=null;
    quoteDownload.disabled=true;
    quoteResults.replaceChildren();
  }
  quoteBtn.addEventListener('click',async()=>{
    if(quoteBusy)return;
    const chosen=scope();
    if(chosen.groups.length<1||chosen.groups.length>10){
      quoteStatus.textContent='Zaznacz od 1 do 10 folderów lub redakcji powyżej.';
      return;
    }
    quoteBusy=true;quoteBtn.disabled=true;clearQuotes();
    quoteStatus.textContent='Odczytuję zapisane cytaty. Nie zmieniam bazy danych…';
    try{
      const params=new URLSearchParams({mode:chosen.mode});
      chosen.groups.forEach(g=>params.append('group',g));
      const resp=await fetch('/api/baza/cytaty_wybranych?'+params.toString());
      const data=await resp.json();
      if(scope().key!==chosen.key){quoteStatus.textContent='Zmieniono wybór. Uruchom porównanie ponownie.';return;}
      if(!resp.ok||!data.ok)throw Error(data.szczegoly||'Nie udało się pobrać cytatów.');
      quotePayload=data;quoteScope=chosen.key;
      quoteDownload.disabled=false;
      const summary=(data.per_group||[]).map(v=>'<div class="sora-shared-diff"><strong>'
        +html(v.group)+'</strong><p>'+html(v.quotes)+' cytatów/przypisanych opinii w '
        +html(v.documents)+' artykułach</p></div>').join('');
      const matches=(data.same_statement_across_groups||[]).slice(0,40).map(row=>
        '<article class="sora-shared-card"><h4>'+html(row.speaker)+'</h4>'
        +'<blockquote class="sora-shared-quote">'+html(row.statement)+'</blockquote>'
        +'<p>Redakcje/foldery: '+html(row.groups.join(', '))+'</p>'
        +'<small>To samo brzmienie w '+html(row.appearances)+' zapisanych kartach. '
        +'Porównaj oryginały przed wyciąganiem wniosków.</small></article>').join('');
      const preview=(data.records||[]).slice(0,25).map(row=>
        '<div class="sora-shared-card"><strong>'+html(row.group)+' · '+html(row.speaker)+'</strong>'
        +'<p>'+html(row.statement)+'</p><small>'+html(row.classification)
        +' · dokument #'+html(row.document_id)+'</small></div>').join('');
      quoteResults.innerHTML='<div class="sora-shared-differences">'+summary+'</div>'
        +'<h4>Identyczne wypowiedzi między grupami</h4>'
        +(matches||'<p>Nie wykryto identycznych cytatów tego samego mówcy pomiędzy wybranymi grupami. '
        +'Nie wyklucza to parafraz.</p>')
        +'<h4>Przykładowe zapisane cytaty (maks. 25)</h4>'+preview;
      quoteStatus.textContent='Przejrzano '+data.scanned_documents+' artykułów. '
        +'Zapisanych cytatów/opinii: '+data.quote_count+'. Wspólnych brzmień między grupami: '
        +(data.same_statement_across_groups||[]).length+'.'
        +(data.truncated?' Uwaga: ograniczono liczbę rekordów do bezpiecznego limitu.':'');
    }catch(e){quoteStatus.textContent='Błąd bazy cytatów: '+(e.message||'nieznany błąd');}
    finally{quoteBusy=false;quoteBtn.disabled=false;}
  });
  quoteDownload.addEventListener('click',()=>{
    if(!quotePayload||quoteScope!==scope().key)return;
    const name='Sora_baza_cytatow_'+new Date().toISOString().slice(0,10)+'.json';
    if(typeof window.pobierzPlik==='function'){
      window.pobierzPlik(name,JSON.stringify(quotePayload,null,2),'application/json;charset=utf-8');
    }
  });
  let controller = null;
  let activeKey = null;
  const render = response => {
    if (!response.matches?.length) {
      output.innerHTML = '<p class="sora-shared-empty">Nie znaleziono wystarczająco podobnych fragmentów w wybranych grupach. '
        + 'To nie dowodzi, że artykuły nie opisują tych samych wydarzeń. '
        + 'Zmień wybór folderów albo sprawdź osobno „Ta sama sprawa”.</p>';
      return;
    }
    output.innerHTML = response.matches.map((pair,i) => {
      const common = (pair.shared || []).map(x=>'<blockquote class="sora-shared-quote">'
        + html(x.text) + ' <small>('+ html(x.words) +' wspólnych słów)</small></blockquote>').join('');
      const different = (items,label) => '<div class="sora-shared-diff"><strong>'+html(label)+'</strong>'
        + (items?.length ? items.map(x=>'<p>'+html(x)+'</p>').join('') : '<p>Nie znaleziono wyraźnie innego fragmentu w przeszukiwanej części tekstu.</p>')
        + '</div>';
      return '<article class="sora-shared-card"><h4>'+ (i+1) + '. ' + html(pair.match_kind) + '</h4>'
        + '<div class="sora-shared-titles"><div><strong>'+html(pair.left.group)+'</strong><p>'
        +html(pair.left.title)+'</p><small>Dokument #'+html(pair.left.id)+'</small></div>'
        + '<div><strong>'+html(pair.right.group)+'</strong><p>'
        +html(pair.right.title)+'</p><small>Dokument #'+html(pair.right.id)+'</small></div></div>'
        + '<h5>Wspólna treść</h5>'
        + (common || '<p>Podobny temat lub tytuł; brak potwierdzonego dosłownie wspólnego fragmentu.</p>')
        + '<h5>Fragmenty różniące się sformułowaniem</h5>'
        + '<div class="sora-shared-differences">'
        + different(pair.only_left,pair.left.group) + different(pair.only_right,pair.right.group)
        + '</div></article>';
    }).join('');
  };
  button.addEventListener('click',async()=>{
    if (controller) return;
    const chosen = scope();
    if (chosen.groups.length < 2 || chosen.groups.length > 10) {
      status.textContent='Zaznacz od 2 do 10 folderów lub redakcji w „Baza / porównania”.';
      return;
    }
    const params = new URLSearchParams({mode:chosen.mode});
    chosen.groups.forEach(x=>params.append('group',x));
    const next = new AbortController();
    controller = next;
    activeKey=chosen.key;
    output.replaceChildren();
    status.textContent='Szukam wspólnych fragmentów i różnic tylko w wybranych grupach…';
    button.disabled=true;
    try {
      const response=await fetch('/api/baza/wspolna_tresc?'+params.toString(),{signal:next.signal});
      const data=await response.json();
      if(controller!==next || scope().key!==chosen.key) return;
      if(!response.ok || !data.ok) throw new Error(data.szczegoly || 'Nie udało się porównać tekstów.');
      status.textContent='Przejrzano '+data.examined_articles+' artykułów. Znaleziono '
        +(data.matches?.length||0)+' par o wspólnej treści lub zbliżonym temacie.'
        +(data.excluded_after_limit ? ' Uwaga: niektóre artykuły pominięto z powodu limitu przetwarzania.' : '');
      render(data);
    } catch (error) {
      if (error.name!=='AbortError') status.textContent='Błąd wyszukiwania: '+(error.message||'Nieznany błąd');
    } finally {
      if (controller===next) {
        controller=null;
        button.disabled=false;
      }
    }
  });
  picker?.addEventListener('change',event=>{
    if(event.target===modeChoice || event.target===groupsSelect || event.target?.matches?.('[data-compare-group]')){
      if(quoteScope && quoteScope!==scope().key){
        clearQuotes();quoteStatus.textContent='Zmieniono zakres. Odczytaj bazę cytatów ponownie.';
      }
      if(activeKey && activeKey!==scope().key){
        controller?.abort(); controller=null; activeKey=null;
        button.disabled=false; output.replaceChildren();
        status.textContent='Zmieniono zaznaczenie. Kliknij „Szukaj wspólnych treści i różnic”.';
      }
    }
  },true);
})();