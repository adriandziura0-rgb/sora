// SORA T03: bezpieczna, deterministyczna reprodukcja kolizji A→B→A.
// Node 20+: node tools/test_t03_quote_scope_race.mjs --audit
// Bramkę przyszłej poprawki: node tools/test_t03_quote_scope_race.mjs --gate
// Test ładuje ORYGINALNY shared-content.js z TEGO checkoutu do VM; nie uruchamia
// serwera ani nie otwiera prywatnych SQLite, nie wymaga internetu.
// --audit: sprawdza, czy odtworzono stary błąd (PASS testu, FAIL aplikacji).
// --gate: po minimalnym fixie musi być GREEN; dziś powinien być czerwony.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const source=readFileSync(new URL('../runtime_source/static/shared-content.js',import.meta.url),'utf8');
assert.match(source,/cytaty_wybranych/, 'Zmienił się plik źródłowy, zrób ponowny audyt');

function element(id){
  return {id,disabled:false,textContent:'',innerHTML:'',selectedOptions:[],events:{},
    parentNode:{insertBefore(){}},
    addEventListener(type,fn){this.events[type]=fn},
    replaceChildren(){this.innerHTML=''},
    querySelector(){return null},
    querySelectorAll(){return []},
  };
}
function harness(){
  const nodes=new Map();
  for(const id of ['findSharedContentBtn','sharedContentStatus','sharedContentResults',
    'databaseCompareGroups','databaseComparePanel','databaseCompareMode',
    'sharedContentPanel'])nodes.set(id,element(id));
  let current='Folder_A';
  const selector=nodes.get('databaseCompareGroups');
  selector.selectedOptions=[{value:current}];
  nodes.get('databaseCompareMode').value='folder';
  nodes.get('sharedContentPanel').querySelector=()=>element('summary');
  const bar={innerHTML:'',className:'',controls:new Map(),
    querySelector(id){return this.controls.get(id.slice(1))||null}};
  for(const id of ['soraFindQuotesBtn','soraDownloadQuotesBtn',
    'soraQuotesStatus','soraQuotesResults'])bar.controls.set(id,element(id));
  bar.controls.get('soraDownloadQuotesBtn').disabled=true;
  const document={
    getElementById:id=>nodes.get(id)||null,
    createElement:()=>bar
  };
  const requests=[],downloads=[];
  const fetch=(url,options={})=>new Promise((resolve,reject)=>{
    const entry={url,options,resolve,reject};
    requests.push(entry);
    if(options.signal?.addEventListener){
      options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('anulowano'),{name:'AbortError'})),{once:true});
    }
  });
  const window={pobierzPlik:(...args)=>downloads.push(args)};
  runInNewContext(source,{document,window,fetch,URLSearchParams,AbortController,Date});
  const quote=bar.controls.get('soraFindQuotesBtn');
  const exportBtn=bar.controls.get('soraDownloadQuotesBtn');
  const status=bar.controls.get('soraQuotesStatus');
  const result=bar.controls.get('soraQuotesResults');
  return {
    requests,downloads,
    click:()=>quote.events.click(),
    export:()=>exportBtn.events.click(),
    choose(name){current=name;selector.selectedOptions=[{value:name}];nodes.get('databaseComparePanel').events.change?.({target:selector})},
    state(){return {status:status.textContent,html:result.innerHTML,exportEnabled:!exportBtn.disabled,fetches:requests.length}},
  };
}
const payload=(tag)=>({ok:true,scanned_documents:1,quote_count:1,
  per_group:[{group:'Folder_A',quotes:1,documents:1}],
  same_statement_across_groups:[],records:[{
    group:'Folder_A',speaker:'Test',statement:tag,
    classification:'cytat',document_id:1
  }]});
const response=(p)=>({ok:true,json:async()=>p});
const badResponse=(msg)=>({ok:false,json:async()=>({ok:false,szczegoly:msg})});
async function reproduce(){
  // 1. Stara odpowiedź A1 wraca po zmianie A1→B→A2; klucz wygląda identycznie.
  const aba=harness(),first=aba.click();
  assert.equal(aba.requests.length,1);
  aba.choose('Folder_B');aba.choose('Folder_A');
  aba.requests[0].resolve(response(payload('STARY_CYTAT_A1')));
  await first;
  aba.export();
  const staleAccepted=aba.state().html.includes('STARY_CYTAT_A1');
  const staleExported=aba.downloads.some(x=>x[1].includes('STARY_CYTAT_A1'));

  // 2. Przejście do B i pozostanie tam: stara odpowiedź jest odrzucana.
  const ab=harness(),other=ab.click();
  ab.choose('Folder_B');
  ab.requests[0].resolve(response(payload('STARY_CYTAT_BLOKOWANY')));
  await other;
  const abRejected=!ab.state().html.includes('STARY_CYTAT_BLOKOWANY')&&!ab.state().exportEnabled;

  // 3. Stary błąd po powrocie B→A nie powinien dotyczyć nowej generacji wyboru.
  const err=harness(),bad=err.click();
  err.choose('Folder_B');err.choose('Folder_A');
  err.requests[0].resolve(badResponse('STARY_BLAD_A1'));
  await bad;
  const staleErrorShown=err.state().status.includes('STARY_BLAD_A1');

  // 4. Gdy A1 wisi, ponowienie A2 po B→A nie powinno być blokowane przez A1.
  const again=harness(),old=again.click();
  again.choose('Folder_B');again.choose('Folder_A');
  const attempt=again.click();
  const freshAllowed=again.requests.length>=2;
  again.requests[0].resolve(response(payload('STARY_CYTAT_A1')));
  await old;
  if(freshAllowed){
    again.requests[1].resolve(response(payload('NOWY_CYTAT_A2')));
    await attempt;
  }

  return {
    code:'SORA 1.2.17 / actual shared-content.js',
    A_B_A:{old_reply_accepted:staleAccepted,stale_exported:staleExported,fetch_signal_used:!!aba.requests[0].options?.signal},
    A_B:{old_reply_rejected:abRejected},
    stale_error:{shown_after_return_to_A:staleErrorShown},
    A1_pending_A2_attempt:{fresh_fetch_allowed:freshAllowed,fetch_count:again.requests.length},
  };
}
const result=await reproduce();
console.log(JSON.stringify({task:'SORA-T03',...result},null,2));
if(process.argv.includes('--gate')){
  assert.equal(result.A_B_A.old_reply_accepted,false,'FAIL T03: stare A1 nadpisało nowe A2');
  assert.equal(result.A_B_A.stale_exported,false,'FAIL T03: stary eksport A1 dostępny');
  assert.equal(result.A_B.old_reply_rejected,true,'FAIL T03: stare A widoczne podczas B');
  assert.equal(result.stale_error.shown_after_return_to_A,false,'FAIL T03: błąd starego A1 w nowym zakresie');
  assert.equal(result.A1_pending_A2_attempt.fresh_fetch_allowed,true,'FAIL T03: A2 nie może wystartować');
  console.log('PASS T03 GATE: żadna stara odpowiedź nie aktualizuje UI/eksportu');
}else{
  assert.equal(result.A_B_A.old_reply_accepted,true);
  assert.equal(result.A_B_A.stale_exported,true);
  assert.equal(result.A_B.old_reply_rejected,true);
  assert.equal(result.stale_error.shown_after_return_to_A,true);
  assert.equal(result.A1_pending_A2_attempt.fresh_fetch_allowed,false);
  console.log('PASS T03 AUDIT: odtworzono wszystkie objawy na źródłowym JS; aplikacja nie przechodzi bramki --gate');
}
