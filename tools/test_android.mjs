// Exercises the installed APK, its real WebView, SAF pickers and SQLite queue.
// All documents below are disposable test fixtures, never the user's database.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {mkdirSync,writeFileSync,readFileSync,copyFileSync} from 'node:fs';
import {_android as android} from 'playwright';

const output='test-output';
mkdirSync(`${output}/input/Sora-tests/RedakcjaA/Sub`,{recursive:true});
mkdirSync(`${output}/input/Sora-tests/RedakcjaB`,{recursive:true});
const article=(source,ending)=>`ŹRÓDŁO: ${source}\nURL: https://${source==='TVN24'?'tvn24.pl':'pap.pl'}/test-szpital\nTYTUŁ: Budowa szpitala w Warszawie\nLEAD: Rada Warszawy zatwierdziła budowę szpitala w dzielnicy Wola.\nTREŚĆ:\nPrezydent Warszawy Rafał Trzaskowski powiedział, że nowy szpital poprawi dostęp do leczenia. Minister zdrowia stwierdził, że rząd sfinansuje budowę szpitala. Rada Warszawy przyjęła uchwałę w sprawie inwestycji. ${ending}\n`;
const fixtures={
 'single.txt':article('TVN24','Budowa potrwa trzy lata.'),
 'second.txt':article('PAP','Opozycja zapowiedziała kontrolę kosztów.'),
 'RedakcjaA/a1.txt':article('TVN24','Władze Warszawy podały harmonogram.'),
 'RedakcjaA/a2.md':article('TVN24','Mieszkańcy Woli oczekują nowego oddziału.'),
 'RedakcjaA/Sub/nested.html':`<article><h1>Szpital na Woli</h1><p>${article('TVN24','Lekarze poparli inwestycję.')}</p></article>`,
 'RedakcjaB/b1.txt':article('PAP','Minister przekazał informacje o finansowaniu.'),
 'RedakcjaB/b2.md':article('PAP','Sejm omówi koszty budowy szpitala.'),
 'empty.txt':'', 'invalid.sqlite3':'This is not a SQLite database.',
 'RedakcjaA/ignored.png':'Not a document',
};
for(const [name,text] of Object.entries(fixtures))writeFileSync(`${output}/input/Sora-tests/${name}`,text);
writeFileSync(`${output}/input/Sora-tests/RedakcjaA/too-large.txt`,Buffer.alloc(3*1024*1024,65));
copyFileSync('app/src/main/assets/drogowskazy-runtime.zip',`${output}/input/Sora-tests/runtime.zip`);
const adb=(...args)=>execFileSync('adb',args,{encoding:'utf8',timeout:45000}).trim();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const until=async(test,label,timeout=60000)=>{
 const end=Date.now()+timeout;let last;
 while(Date.now()<end){try{const value=await test();if(value)return value;}catch(e){last=e;}await pause(250);}
 throw new Error(`Timeout: ${label}${last?' · '+last.message:''}`);
};
const decode=s=>s.replace(/&quot;/g,'"').replace(/&amp;/g,'&').replace(/&apos;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>');
function nativeNodes(){
 adb('shell','uiautomator','dump','/sdcard/sora-window.xml');
 const xml=adb('shell','cat','/sdcard/sora-window.xml');
 writeFileSync(`${output}/last-native.xml`,xml);
 return Array.from(xml.matchAll(/<node\b([^>]+)>/g),m=>Object.fromEntries(Array.from(m[1].matchAll(/([\w-]+)="([^"]*)"/g),a=>[a[1],decode(a[2])])));
}
function point(node){const n=node.bounds.match(/\d+/g).map(Number);return [Math.round((n[0]+n[2])/2),Math.round((n[1]+n[3])/2)];}
const matches=(n,label)=>n.text?.toLowerCase()===label.toLowerCase() || n['content-desc']?.toLowerCase()===label.toLowerCase() || n['resource-id']===label;
async function nativeFind(label,timeout=20000){
 return until(()=>{
   const nodes=nativeNodes();
   const node=nodes.find(n=>matches(n,label)&&n.enabled!=='false');
   if(node)return node;
   const candidates=nodes.filter(n=>n.scrollable==='true' && n.class!=='android.webkit.WebView' && !n.class.includes('Horizontal'));
   const height=n=>{const b=n.bounds.match(/\d+/g).map(Number);return b[3]-b[1];};
   const list=candidates.sort((a,b)=>height(b)-height(a)).find(n=>height(n)>300);
   if(list){
     const [left,top,right,bottom]=list.bounds.match(/\d+/g).map(Number);
     const x=String(Math.round((left+right)/2));
     // Stay clear of Android's bottom navigation gesture area.
     const screenBottom=Math.max(...nodes.map(n=>Number(n.bounds.match(/\d+/g)?.[3]||0)));
     const start=Math.min(bottom-200,Math.round(screenBottom*0.82));
     const end=Math.max(top+120,Math.round(screenBottom*0.24));
     if(start>end)adb('shell','input','swipe',x,String(start),x,String(end),'400');
   }
   return false;
 },`Android button ${label}`,timeout);
}
async function nativeTap(label,timeout=20000){
 const node=await nativeFind(label,timeout);
 adb('shell','input','tap',...point(node).map(String));await pause(350);return node;
}
async function downloads(){
 const nodes=await until(()=>{const ns=nativeNodes();return ns.some(n=>/documentsui/.test(n.package||''))?ns:false;},'document picker ready');
 if(nodes.some(n=>matches(n,'Sora-tests')))return;
 // Our own pickers set Downloads explicitly. Android's print spooler may
 // instead remember a different provider, so navigate through local storage.
 await nativeTap('Show roots');
 const storage=await until(()=>nativeNodes().find(n=>n.enabled!=='false' && /sdk_gphone|Internal storage/i.test(n.text||n['content-desc']||'')),'local storage root');
 adb('shell','input','tap',...point(storage).map(String));await pause(350);
 await nativeTap('Download');
 await until(()=>nativeNodes().some(n=>matches(n,'Sora-tests')),'picker opens filesystem Downloads');
}
async function pickFile(name){await downloads();await nativeTap('Sora-tests');await nativeTap(name);}
async function pickFiles(names){
 await downloads();await nativeTap('Sora-tests');
 const first=await nativeFind(names[0]);
 const [x,y]=point(first).map(String);adb('shell','input','swipe',x,y,x,y,'900');
 for(const name of names.slice(1))await nativeTap(name);
 const select=await until(()=>nativeNodes().find(n=>['Select','Open','com.google.android.documentsui:id/action_menu_select','com.android.documentsui:id/action_menu_select'].some(label=>matches(n,label))),'confirm multiple files');
 adb('shell','input','tap',...point(select).map(String));await pause(350);
}
async function pickFolder(name){
 await downloads();await nativeTap('Sora-tests');if(name)await nativeTap(name);
 await nativeTap('Use this folder');await nativeTap('Allow');
}
async function saveFile(name){
 await downloads();
 const edit=await until(()=>nativeNodes().find(n=>n.class==='android.widget.EditText'), 'Save filename');
 adb('shell','input','tap',...point(edit).map(String));
 adb('shell','input','keyevent','123');
 adb('shell','input','keyevent',...Array(Math.max(1,edit.text.length)).fill('67'));
 adb('shell','input','text',name);await nativeTap('Save');
 await until(()=>{try{return adb('shell','ls',`/sdcard/Download/${name}`).includes(name);}catch{return false;}},`saved ${name}`);
 adb('pull',`/sdcard/Download/${name}`,`${output}/${name}`);
 return readFileSync(`${output}/${name}`);
}
const api=async(path,options)=>{const r=await fetch(`http://127.0.0.1:15433${path}`,options);const value=await r.json();if(!r.ok)throw new Error(JSON.stringify(value));return value;};
const queueDone=()=>until(async()=>{const s=await api('/api/baza/status');return s.stats.processing===0?s:false;},'queue drained',120000);
let device,page;
const clicked=new Set();const scenarios=[];const jsErrors=[];let importResponses=0;
async function click(selector,real=false){
 const el=page.locator(selector).first();
 assert.equal(await el.count(),1,`Missing ${selector}`);
 assert.equal(await el.evaluate(e=>e.disabled),false,`Disabled ${selector}`);
 if(real)await el.click({timeout:15000});else await el.evaluate(e=>e.click());
 clicked.add(selector);await pause(120);
}
const waitJs=condition=>page.waitForFunction(condition,null,{timeout:120000});
const done=label=>{scenarios.push(label);writeFileSync(`${output}/progress.json`,JSON.stringify({scenarios,clicked:[...clicked]},null,2));console.log(`PASS: ${label}`);};
async function exportButton(selector,name){await click(selector);return saveFile(name);}
async function databaseView(){await click('#userModeBtn');await click('[data-production-view="baza"]');}
async function importAndWait(selector,picker,requests){
 const expected=importResponses+requests;
 await click(selector,true);await picker();
 await until(async()=>importResponses>=expected && !await page.evaluate(()=>importBazyAktywny),'selected files uploaded',120000);
}
try{
 await until(()=>{
   try{
     if(adb('get-state')!=='device')return false;
     adb('shell','mkdir','-p','/sdcard/Download/Sora-tests');
     adb('shell','touch','/sdcard/Download/Sora-tests/.ready');
     return true;
   }catch{return false;}
 },'emulator shared storage ready',120000);
 adb('push',`${output}/input/Sora-tests/.`,'/sdcard/Download/Sora-tests/');
 adb('install','-r','app/build/outputs/apk/debug/app-debug.apk');
 adb('shell','pm','grant','pl.drogowskazy.sora','android.permission.POST_NOTIFICATIONS');
 adb('shell','am','start','-n','pl.drogowskazy.sora/.MainActivity');
 adb('forward','tcp:15433','tcp:5433');
 await until(()=>api('/api/health'),'APK server start',120000);
 const devices=await android.devices({omitDriverInstall:true});assert.equal(devices.length,1);
 device=devices[0];device.setDefaultTimeout(120000);
 const webview=await device.webView({pkg:'pl.drogowskazy.sora'});
 page=await webview.page();
 await until(()=>page.url().includes('127.0.0.1:5433'),'local panel');
 page.on('pageerror',e=>jsErrors.push(e.message));
 page.on('response',r=>{if(new URL(r.url()).pathname==='/api/baza/importuj')importResponses++;});
 await waitJs(()=>window.__drogowskazyNativeInstalled && document.getElementById('backendStatusPill').classList.contains('backend-ok'));
 const inventory=await page.evaluate(()=>Array.from(document.querySelectorAll('button')).map(e=>e.id?`#${e.id}`:['productionView','expertView','previewView','userTextView','view','menuGroup'].map(key=>e.dataset[key]?`[data-${key.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())}="${e.dataset[key]}"]`:null).find(Boolean)).filter(Boolean));
 done('APK first start, embedded runtime, HTTP health, real Android WebView bridge');

 await click('#loadFileBtn',true);await pickFile('single.txt');await waitJs(()=>document.getElementById('textInput').value.includes('Budowa potrwa'));
 await click('#appendFileBtn',true);await pickFile('second.txt');await waitJs(()=>document.getElementById('textInput').value.includes('Opozycja'));
 await click('#appendManyFilesBtn',true);await pickFiles(['single.txt','second.txt']);await waitJs(()=>document.getElementById('fileLoadStatus').textContent.includes('Dodano 2'));
 await click('#clearBtn');
 await click('#appendAllFilesBtn',true);await pickFolder('RedakcjaA');await waitJs(()=>document.getElementById('textInput').value.includes('Lekarze poparli'));
 assert.match(await page.locator('#fileLoadStatus').textContent(),/Pominięto/);
 done('real SAF single/append/multiple file pickers, recursive folder, unsupported and oversized skips');

 await databaseView();
 await importAndWait('#importFilesToDatabaseBtn',()=>pickFiles(['single.txt','second.txt']),2);
 let state=await queueDone();assert.equal(state.stats.done,2);
 await importAndWait('#importFilesToDatabaseBtn',()=>pickFile('single.txt'),1);
 await waitJs(()=>!importBazyAktywny && document.getElementById('databaseImportFeedback').textContent.includes('duplikaty 1'));assert.equal((await queueDone()).stats.done,2);
 await importAndWait('#importFilesToDatabaseBtn',()=>pickFile('empty.txt'),1);
 await waitJs(()=>document.getElementById('databaseImportFeedback').classList.contains('is-error'));
 assert.match(await page.locator('#databaseImportFeedback').textContent(),/pusty|empty|nie zawiera tekstu/i);
 await importAndWait('#importFolderToDatabaseBtn',()=>pickFolder('RedakcjaA'),3);state=await queueDone();assert.equal(state.stats.done,5);
 await page.locator('#databaseComparePanel > summary').click();
 await importAndWait('#addCompareFolderBtn',()=>pickFolder('RedakcjaB'),2);state=await queueDone();assert.equal(state.stats.done,7);
 await importAndWait('#addCompareFolderPackBtn',()=>pickFolder(),5);assert.equal((await queueDone()).stats.done,7);
 await click('#importFolderToDatabaseBtn',true);await nativeTap('Show roots');adb('shell','input','keyevent','4');adb('shell','input','keyevent','4');await pause(500);
 assert.equal(await page.evaluate(()=>wymusKlasycznyPickerFolderuBazy),false);
 await importAndWait('#importFolderToDatabaseBtn',()=>pickFolder('RedakcjaA'),3);
 done('real SQLite import: files, duplicate, empty-file error retained, folders, nested HTML, folder pack, cancellation and retry');

 // Delay one transfer to verify Stop adding without interrupting persisted jobs.
 await page.route('**/api/baza/importuj',async route=>{await pause(700);await route.continue();});
 await click('#importFolderToDatabaseBtn',true);await pickFolder('RedakcjaA');
 await waitJs(()=>importBazyAktywny);await click('#cancelDatabaseImportBtn');await waitJs(()=>!importBazyAktywny);
 await page.unroute('**/api/baza/importuj');await queueDone();
 await click('#refreshDatabaseBtn');await waitJs(()=>document.querySelectorAll('.database-folder-group').length>0);
 await page.locator('.database-documents-panel').evaluate(e=>e.open=true);
 const folder=page.locator('#databaseDocuments details').first();if(await folder.count())await folder.evaluate(e=>e.open=true);
 await waitJs(()=>document.querySelectorAll('[data-database-document-id]').length>0);
 await page.locator('[data-database-document-id]').first().evaluate(e=>e.click());await waitJs(()=>ostatnieDane!==null);
 done('stop adding and database refresh');

 await click('#expertModeBtn');
 await click('#splitWorkspaceBtn');
 await page.locator('#sourceTextDetails').evaluate(e=>e.open=true);
 await page.locator('#textInput').fill(article('TVN24','Eksperci ocenili skutki decyzji.'));
 await click('#analyzeBtn');await waitJs(()=>ostatnieDane && ostatnieDane.analysis_run_id && !document.getElementById('analyzeBtn').disabled);
 for(const selector of inventory.filter(s=>s.startsWith('[data-') && !s.includes('production-view'))){
  if(selector.includes('user-text-view'))continue;
  const el=page.locator(selector).first();
  if(await el.evaluate(e=>e.disabled)){
    assert.ok(await el.evaluate(e=>e.classList.contains('is-unavailable')||e.getAttribute('aria-disabled')==='true'),`Unexplained disabled button ${selector}`);
    clicked.add(selector);
  }else await click(selector);
 }
 for(const id of ['splitWorkspaceBtn','resultsFocusBtn','clearSectionMenuSearch','openAllWindowsBtn','openSublevelsBtn','closeSublevelsBtn','closeAllWindowsBtn','singleWindowModeBtn','previousSectionBtn','nextSectionBtn','openResultsMenuBtn'])await click(`#${id}`);
 const windowButton=page.locator('.readable-window').first();assert.ok(await windowButton.count());await windowButton.evaluate(e=>e.click());
 assert.equal(await page.locator('#sectionWindowDialog').evaluate(e=>e.open),true);await click('#closeSectionWindowBtn');
 await click('#userModeBtn');
 for(const selector of inventory.filter(s=>s.includes('production-view')||s.includes('user-text-view')))await click(selector);
 await click('#expertModeBtn');await click('#suggestBtn');await waitJs(()=>!document.getElementById('suggestBtn').disabled);
 await click('#analyzeBtn');await waitJs(()=>!document.getElementById('analyzeBtn').disabled);
 await click('#reportBtn');await waitJs(()=>ostatniEksport!==null && !document.getElementById('reportBtn').disabled);
 await click('#copyReportBtn');await waitJs(()=>document.getElementById('reportBox').textContent.includes('Skopiowano'));
 JSON.parse((await exportButton('#downloadResultsBtn','audit-results.json')).toString());
 assert.ok((await exportButton('#downloadMdBtn','audit-report.md')).length>100);
 JSON.parse((await exportButton('#downloadJsonBtn','audit-report.json')).toString());
 await click('#printPdfBtn');
 const print=await until(()=>nativeNodes().find(n=>/:id\/print_button$/.test(n['resource-id']||'') && n.enabled==='true'),'Save PDF print button');
 adb('shell','input','tap',...point(print).map(String));
 const pdf=await saveFile('audit-report.pdf');assert.equal(pdf.subarray(0,5).toString(),'%PDF-');assert.ok(pdf.length>1000);
 await until(()=>nativeNodes().some(n=>n.package==='pl.drogowskazy.sora'),'print returns to application');
 done('analysis, suggestions, all navigation/filter/window buttons, report, native clipboard, JSON/MD/PDF export');

 await databaseView();await click('#expertModeBtn');await page.locator('#databasePanel').evaluate(e=>e.open=true);
 const backup=await exportButton('#downloadDatabaseBtn','audit-backup.sqlite3');assert.equal(backup.subarray(0,16).toString(),'SQLite format 3\0');
 await click('#reanalyzeDatabaseBtn');await waitJs(()=>!document.getElementById('reanalyzeDatabaseBtn').disabled);assert.equal((await queueDone()).stats.done,7);
 await click('#aggregateDatabaseBtn');await waitJs(()=>ostatnieDane?.aggregate_from_database===true);
 JSON.parse((await exportButton('#downloadResultsBtn','audit-aggregate.json')).toString());
 await databaseView();await click('#expertModeBtn');await page.locator('#databasePanel').evaluate(e=>e.open=true);
 await page.locator('#databaseComparePanel').evaluate(e=>e.open=true);
 await page.locator('#databaseCompareMode').selectOption('folder');await page.evaluate(()=>odswiezGrupyPorownania());await waitJs(()=>document.getElementById('databaseCompareGroups').options.length>=2);
 await page.evaluate(()=>{const s=document.getElementById('databaseCompareGroups');Array.from(s.options).forEach((o,i)=>o.selected=i<2);s.dispatchEvent(new Event('change'));});
 await click('#compareDatabaseBtn');await waitJs(()=>ostatniePorownanieBazy!==null);
 JSON.parse((await exportButton('#downloadDatabaseComparisonBtn','audit-comparison.json')).toString());
 await page.locator('#sameStoryComparePanel').evaluate(e=>e.open=true);
 await page.evaluate(()=>odswiezTematyTejSamejSprawy());
 await waitJs(()=>Array.from(document.getElementById('sameStoryTopic').options).some(o=>o.value));
 await page.evaluate(()=>{const s=document.getElementById('sameStoryTopic');s.value=Array.from(s.options).find(o=>o.value).value;s.dispatchEvent(new Event('change'));});
 await waitJs(()=>document.getElementById('sameStoryGroups').options.length>=2);
 await page.evaluate(()=>{const s=document.getElementById('sameStoryGroups');Array.from(s.options).forEach((o,i)=>o.selected=i<2);s.dispatchEvent(new Event('change'));});
 await click('#compareSameStoryBtn');await waitJs(()=>ostatniePorownanieTejSamejSprawy!==null);
 JSON.parse((await exportButton('#downloadSameStoryComparisonBtn','audit-same-story.json')).toString());
 done('SQLite export, reanalysis, aggregate export, folder comparison and same-story comparison with JSON');

 await page.locator('#manualBenchmarkPanel').evaluate(e=>e.open=true);
 await click('#loadBenchmarkSampleBtn');await waitJs(()=>benchmarkProba.length>0);await click('#saveBenchmarkLabelBtn');await waitJs(()=>benchmarkIndex===1);
 await click('#refreshBenchmarkStatsBtn');
 await page.locator('#effectivenessGoldPanel').evaluate(e=>e.open=true);
 await click('#loadGoldSampleBtn');await waitJs(()=>goldProba.length>0);
 await page.locator('#goldExpectedJson').fill('not JSON');await click('#saveGoldDocumentBtn');assert.match(await page.locator('#goldStatus').textContent(),/Błąd JSON/);
 await page.locator('#goldExpectedJson').fill('[]');await click('#saveGoldDocumentBtn');await waitJs(()=>goldIndex===1);
 await click('#refreshGoldStatsBtn');done('benchmark sample/save/stats, GOLD sample, invalid JSON, save and stats');

 await click('#appSettingsBtn',true);await nativeTap('Ustawienia baterii — ustaw Bez ograniczeń');adb('shell','input','keyevent','4');await pause(350);
 await nativeTap('Uruchom ponownie usługę');await until(()=>nativeNodes().some(n=>n.text==='Program działa w tle.'),'runtime restart',120000);
 assert.equal((await queueDone()).stats.done,7);
 await nativeTap('Otwórz panel Drogowskazów');await waitJs(()=>window.__drogowskazyNativeInstalled);
 await databaseView();const restored=page.waitForEvent('load',{timeout:120000});
 await click('#restoreDatabaseBackupBtn',true);await downloads();await nativeTap('audit-backup.sqlite3');
 await restored;await waitJs(()=>window.__drogowskazyNativeInstalled);assert.equal((await queueDone()).stats.done,7);
 await click('#appSettingsBtn',true);await nativeTap('Przywróć kopię bazy SQLite');await pickFile('invalid.sqlite3');
 await until(()=>nativeNodes().some(n=>/Błąd przywracania|Nie udało się przywrócić/.test(n.text)),'invalid SQLite error',120000);
 await nativeTap('Uruchom ponownie usługę');await until(()=>nativeNodes().some(n=>n.text==='Program działa w tle.'),'restart after rejected backup',120000);
 assert.equal((await queueDone()).stats.done,7);
 await nativeTap('Wybierz / zaktualizuj ZIP Drogowskazów');adb('shell','input','keyevent','4');
 const updated=page.waitForEvent('load',{timeout:120000});
 await nativeTap('Wybierz / zaktualizuj ZIP Drogowskazów');await pickFile('runtime.zip');
 await updated;await waitJs(()=>window.__drogowskazyNativeInstalled);assert.equal((await queueDone()).stats.done,7);
 await click('#appSettingsBtn',true);
 await nativeTap('Zatrzymaj pracę w tle');await until(async()=>{try{await api('/api/health');return false;}catch{return true;}},'service stopped',60000);
 await nativeTap('Uruchom ponownie usługę');await until(()=>api('/api/health'),'service resumed',120000);assert.equal((await queueDone()).stats.done,7);
 await nativeTap('Otwórz panel Drogowskazów');await waitJs(()=>window.__drogowskazyNativeInstalled);
 await click('#clearBtn');assert.equal(await page.locator('#textInput').inputValue(),'');assert.equal(await page.evaluate(()=>ostatnieDane),null);
 assert.equal(await page.locator('.user-result-card').count(),0);
 assert.equal(await page.locator('#statementRelationsSection').textContent(),'');
 assert.equal(await page.locator('#printReport').textContent(),'');
 done('app settings, battery screen, actual service restart/stop/resume, valid restore, invalid restore preserves SQLite, ZIP cancellation/update preserves SQLite, clear');
 const missing=inventory.filter(s=>!clicked.has(s));assert.deepEqual(missing,[],`Untested static buttons: ${missing.join(', ')}`);
 assert.deepEqual(jsErrors,[],`Uncaught WebView errors: ${jsErrors.join(', ')}`);
 writeFileSync(`${output}/android-audit.json`,JSON.stringify({apk:'1.2.3',androidApi:adb('shell','getprop','ro.build.version.sdk'),staticButtons:inventory.length,clicked:[...clicked],scenarios,uncaughtErrors:jsErrors},null,2));
 writeFileSync(`${output}/android-final.png`,execFileSync('adb',['exec-out','screencap','-p']));
 console.log(`PASS: ${inventory.length} static panel buttons covered on Android; ${scenarios.length} integration scenarios`);
}catch(error){
 writeFileSync(`${output}/failure.txt`,error.stack || String(error));
 try{writeFileSync(`${output}/web-state.json`,JSON.stringify(await page.evaluate(()=>({classes:document.body.className,buttons:Array.from(document.querySelectorAll('button[id]')).map(e=>({id:e.id,disabled:e.disabled,visible:!!e.getClientRects().length})),statuses:Array.from(document.querySelectorAll('[id$="Status"],[id$="Feedback"]')).map(e=>({id:e.id,text:e.textContent})),details:Array.from(document.querySelectorAll('details[id]')).map(e=>({id:e.id,open:e.open}))})),null,2));}catch{}
 try{writeFileSync(`${output}/android-failure.png`,execFileSync('adb',['exec-out','screencap','-p']));writeFileSync(`${output}/logcat.txt`,adb('logcat','-d','-t','800'));}catch{}
 throw error;
}finally{if(device)await device.close();}