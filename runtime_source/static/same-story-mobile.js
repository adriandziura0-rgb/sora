/* SORA: mobilne karty jednej sprawy, źródła i eksport. Nie zmienia CORE/SQLite. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  const result = el('sameStoryComparisonResult');
  const panel = el('sameStoryComparePanel');
  const topicSelect = el('sameStoryTopic');
  const groupSelect = el('sameStoryGroups');
  if (!result || !panel || !topicSelect || !groupSelect) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const asNum = x => Number.isFinite(Number(x)) ? Number(x) : 0;
  const format = (value, kind) => {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value);
    return n.toLocaleString('pl-PL', {maximumFractionDigits: kind === 'count' ? 0 : 2})
      + (kind === 'percent' ? '%' : '');
  };
  const groupNames = data => Array.isArray(data.groups) && data.groups.length
    ? data.groups.map(g => String(g.name || '—'))
    : [String(data.group_a?.name || 'A'), String(data.group_b?.name || 'B')];
  const metricsByGroup = (data, name, index) => (data.metrics || []).map(item => ({
    label: String(item.label || 'Metryka'),
    key: String(item.key || ''),
    kind: item.kind || '',
    value: Array.isArray(data.groups)
      ? (item.values || {})[name]
      : (index === 0 ? item.a : item.b)
  }));
  const category = entry => {
    const t = (entry.label + ' ' + entry.key).toLowerCase();
    if (/p0|sygnał/.test(t)) return 'P0 — sygnały';
    if (/p1|struktury/.test(t)) return 'P1 — struktury';
    if (/p2|technik/.test(t)) return 'P2 — techniki';
    if (/p3|ramy/.test(t)) return 'P3 — ramy narracyjne';
    if (/p4|strateg/.test(t)) return 'P4 — strategie';
    if (/p5|diagnoz/.test(t)) return 'P5 — diagnozy';
    if (/cytat|opini|fakt|wypowied|relacj/.test(t)) return 'Wypowiedzi i cytaty';
    return 'Podstawowe metryki';
  };
  const categories = ['Podstawowe metryki','Wypowiedzi i cytaty',
    'P0 — sygnały','P1 — struktury','P2 — techniki',
    'P3 — ramy narracyjne','P4 — strategie','P5 — diagnozy'];
  let active = null;
  const host = document.createElement('section');
  host.id = 'soraStoryReadable';
  host.className = 'sora-story-readable';
  host.hidden = true;
  host.setAttribute('aria-label','Czytelne porównanie tej samej sprawy');
  result.before(host);

  const topicFor = payload => {
    const topicId = String(payload.same_story?.topic_id || '');
    return (typeof wykryteTematyBazy !== 'undefined' && Array.isArray(wykryteTematyBazy)
      ? wykryteTematyBazy : []).find(t => t.topic_id === topicId) || null;
  };
  function selectedDocuments(data) {
    const topic = topicFor(data);
    const selected = new Set(groupNames(data).map(v=>v.toLocaleLowerCase('pl-PL')));
    return (topic?.items || []).filter(item =>
      selected.has(String(item.publisher || '').toLocaleLowerCase('pl-PL'))
      && Number(item.document_id) > 0).slice(0, 60);
  }
  function sourceCard(item) {
    const id = Number(item.document_id);
    const url = String(item.url || '');
    const sourceLink = /^https?:\/\//i.test(url) ?
      '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">Oryginalny artykuł</a>' : '';
    return '<article class="sora-story-source">'
      + '<div class="sora-story-source-meta"><strong>' + esc(item.publisher || 'Nieustalona redakcja')
      + '</strong><span>' + esc(item.date || 'Data nieustalona') + '</span></div>'
      + '<p>' + esc(item.title || item.relative_path || 'Dokument') + '</p>'
      + '<small>' + esc(item.relative_path || '') + ' · dokument #' + id + '</small>'
      + '<div class="sora-story-source-actions"><button type="button" data-sora-story-open="' + id
      + '">Otwórz zapisany wynik</button>'
      + '<button type="button" data-sora-story-quotes="' + id
      + '">Pokaż cytaty i ich źródła</button>' + sourceLink + '</div>'
      + '<div class="sora-story-excerpts" id="soraStoryExcerpts' + id + '" hidden></div></article>';
  }
  function render(payload) {
    if (!payload || payload.ok !== true || !payload.same_story?.topic_id) return;
    const groups = groupNames(payload);
    if (groups.length < 2) return;
    const sources = selectedDocuments(payload);
    const total = sources.length;
    const groupCards = groups.map((name,index) => {
      const group = (payload.groups || []).find(g => g.name === name)
        || (index === 0 ? payload.group_a : payload.group_b) || {};
      const metrics = metricsByGroup(payload,name,index);
      const sections = categories.map(section => {
        const entries = metrics.filter(m => category(m) === section);
        if (!entries.length) return '';
        return '<details class="sora-story-metrics" ' + (section === 'Podstawowe metryki' ? 'open' : '') + '>'
          + '<summary>' + esc(section) + ' (' + entries.length + ')</summary><dl>'
          + entries.map(row=>'<div><dt>'+esc(row.label)+'</dt><dd>'
              +esc(format(row.value,row.kind))+'</dd></div>').join('')
          + '</dl></details>';
      }).join('');
      return '<article class="sora-story-editor"><h4>' + esc(name) + '</h4>'
        + '<p class="sora-story-docs">' + esc(group.documents ?? sources.filter(s=>s.publisher===name).length)
        + ' artykułów w tej sprawie</p>' + sections + '</article>';
    }).join('');
    const warnings=(payload.warnings || []).map(w=>'<p class="sora-story-warning">'+esc(w)+'</p>').join('');
    const sourceList= sources.length ? sources.map(sourceCard).join('')
      : '<p>Lista dokumentów źródłowych nie jest dostępna w tym raporcie. Nie tworzę fikcyjnych odnośników.</p>';
    host.innerHTML = '<header class="sora-story-header"><p>PORÓWNANIE JEDNEJ SPRAWY</p><h3>'
      +esc(payload.same_story.title || topicSelect.selectedOptions[0]?.textContent || 'Wspólna sprawa')
      +'</h3><span>'+esc(groups.join(' · '))+'</span></header>'
      +'<div class="sora-story-actions">'
      +'<button type="button" id="soraStoryDownloadHtml">Pobierz raport tej sprawy (HTML)</button>'
      +'<button type="button" id="soraStoryDownloadJson">Pobierz dane (JSON)</button>'
      +'<button type="button" id="soraStoryTableToggle" aria-expanded="false">Pokaż oryginalną tabelę</button>'
      +'</div><p class="sora-story-info">Wyniki opisują wyłącznie wybrany temat i redakcje. '
      +'Różnice liczbowe nie są oceną intencji ani wiarygodności.</p>'
      +warnings
      +'<div class="sora-story-group-grid">'+groupCards+'</div>'
      +'<details class="sora-story-sources" open><summary>Artykuły, cytaty i dowody ('+total+')</summary>'
      +'<p>Każdy zapisany dokument możesz otworzyć osobno. Cytaty są pobierane dopiero po Twoim kliknięciu.</p>'
      +'<div class="sora-story-source-list">'+sourceList+'</div></details>';
    host.hidden=false;
    result.classList.add('sora-story-has-cards');
    active={payload,topicId:payload.same_story.topic_id,names:groups.slice(),sources};
    hookButtons();
  }
  function clear(){
    active=null; host.hidden=true; host.replaceChildren();
    result.classList.remove('sora-story-has-cards','sora-story-show-table');
  }
  const fileName = ext => 'Sora_ta_sama_sprawa_' + new Date().toISOString().slice(0,10) + '.' + ext;
  function download(name,text,mime){
    if (typeof pobierzPlik === 'function') pobierzPlik(name,text,mime);
  }
  function hookButtons(){
    el('soraStoryDownloadJson')?.addEventListener('click',()=>{
      if(!active) return;
      download(fileName('json'), JSON.stringify({
        format:'sora_same_story_report_v1', comparison:active.payload,
        source_documents:active.sources
      },null,2),'application/json;charset=utf-8');
    });
    el('soraStoryDownloadHtml')?.addEventListener('click',()=>{
      if(!active) return;
      const printable=host.cloneNode(true);
      printable.querySelector('.sora-story-actions')?.remove();
      printable.querySelectorAll('details').forEach(d=>d.open=true);
      printable.querySelectorAll('.sora-story-source-actions').forEach(e=>e.remove());
      const html='<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        +'<meta name="viewport" content="width=device-width,initial-scale=1">'
        +'<title>SORA — raport jednej sprawy</title>'
        +'<style>body{font:15px/1.5 Arial,sans-serif;max-width:920px;margin:24px auto;padding:12px;color:#122136}'
        +'article,details{border:1px solid #cbd5e1;padding:12px;margin:12px 0;border-radius:10px;break-inside:avoid}'
        +'h1,h2,h3,h4{color:#155e75}dl>div{display:flex;justify-content:space-between;border-top:1px solid #e2e8f0;padding:6px 0;gap:12px}'
        +'dt{flex:1}dd{font-weight:bold;margin:0;min-width:80px;text-align:right}'
        +'.sora-story-source-meta{display:flex;justify-content:space-between;gap:12px}'
        +'.sora-story-group-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}'
        +'@media(max-width:650px){.sora-story-group-grid{display:block}}'
        +'</style></head><body><h1>SORA — raport jednej sprawy</h1>'
        +'<p>Data: '+esc(new Date().toLocaleString('pl-PL'))+'</p>'
        +printable.innerHTML+'</body></html>';
      download(fileName('html'),html,'text/html;charset=utf-8');
    });
    el('soraStoryTableToggle')?.addEventListener('click',()=>{
      const show=result.classList.toggle('sora-story-show-table');
      const button=el('soraStoryTableToggle');
      button.textContent=show?'Ukryj oryginalną tabelę':'Pokaż oryginalną tabelę';
      button.setAttribute('aria-expanded',String(show));
    });
    host.querySelectorAll('[data-sora-story-open]').forEach(button=>button.addEventListener('click',()=>{
      const id=Number(button.dataset.soraStoryOpen);
      if(id>0 && typeof otworzWynikZBazy==='function') void otworzWynikZBazy(id);
    }));
    host.querySelectorAll('[data-sora-story-quotes]').forEach(button=>button.addEventListener('click',()=>{
      void loadQuotes(Number(button.dataset.soraStoryQuotes),button);
    }));
  }
  async function loadQuotes(id,button){
    if(!active || !active.sources.some(s=>Number(s.document_id)===id)) return;
    const box=el('soraStoryExcerpts'+id);
    if(!box) return;
    if(!box.hidden){box.hidden=true;button.textContent='Pokaż cytaty i ich źródła';return;}
    box.hidden=false; box.textContent='Odczytuję zapisane cytaty tego artykułu…';
    button.disabled=true;
    try{
      const response=await fetch('/api/baza/dokument/'+id+'/wynik');
      const data=await response.json();
      if(!response.ok) throw Error(data.szczegoly || data.blad || 'Brak dostępu do dokumentu');
      if(!active || !active.sources.some(s=>Number(s.document_id)===id)) return;
      const sections=data.wynik?.sekcje || {};
      const quoteCards=Array.isArray(sections.fact_opinia_cytat)?sections.fact_opinia_cytat:[];
      const quotes=quoteCards.filter(c=>/cytat|opinia/i.test(String(c.claim_type||'')) &&
        String(c.phrase||c.fragment||'').trim()).slice(0,8);
      if(!quotes.length){
        box.textContent='W zapisanym wyniku tego artykułu nie znaleziono kart cytatów.';
      }else{
        box.innerHTML='<h5>Wypowiedzi przypisane w tym artykule</h5>'
          +quotes.map(q=>'<blockquote><strong>'+esc(q.speaker || 'Mówca nieustalony')
            +'</strong><p>'+esc(q.phrase || q.fragment)+'</p><small>'
            +esc(q.claim_type_pl || q.claim_type || 'cytat')
            +(q.requires_review?' · wymaga weryfikacji':'')+'</small></blockquote>').join('')
          +'<p>Przypisanie pochodzi z zapisanej analizy. Weryfikuj je w oryginalnym artykule.</p>';
      }
      button.textContent='Ukryj cytaty';
    }catch(e){box.textContent='Nie udało się odczytać cytatów: '+String(e.message||e);}
    finally{button.disabled=false;}
  }
  new MutationObserver(()=>{
    // Oryginalny renderer pozostaje źródłem prawdy; karty są tylko widokiem.
    if(typeof ostatniePorownanieTejSamejSprawy === 'undefined')return;
    const data=ostatniePorownanieTejSamejSprawy;
    const chosen=Array.from(groupSelect.selectedOptions||[]).map(o=>String(o.value).toLocaleLowerCase('pl-PL')).sort();
    const returned=data?.ok ? groupNames(data).map(n=>String(n).toLocaleLowerCase('pl-PL')).sort() : [];
    if(data && data.ok && data.same_story?.topic_id === topicSelect.value
      && chosen.length>=2 && JSON.stringify(chosen)===JSON.stringify(returned)) render(data);
    else clear();
  }).observe(result,{childList:true});
  topicSelect.addEventListener('change',clear);
  groupSelect.addEventListener('change',clear);
  el('sameStoryGroupList')?.addEventListener('change',clear);
  panel.addEventListener('toggle',()=>{if(!panel.open)host.hidden=true;else if(active)host.hidden=false;});
})();