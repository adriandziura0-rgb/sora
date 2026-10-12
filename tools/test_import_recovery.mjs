// Test przypadku użytkownika: folder ok. 40 MB, możliwość zamknięcia / anulowania
// i przekazanie plików do istniejącej kolejki SQLite, bez zmiany CORE.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
const code=readFileSync(new URL('./overview_assets/import-recovery.js',import.meta.url),'utf8');
const controls=new Map();
function element(id){
  const e={id,hidden:true,open:false,textContent:'',value:'',classList:{
    data:new Set(),add(x){this.data.add(x);},remove(x){this.data.delete(x);},
    contains(x){return this.data.has(x);}
  },events:{},addEventListener(name,fn){this.events[name]=fn;},
  click(){this.events.click?.();},setAttribute(){},removeAttribute(){},append(child){
    const ids=['soraImportCancel','soraImportDatabase','soraImportClose'];
    for(const key of ids)controls.set(key,element(key));
  }};
  return e;
}
for(const id of ['operationProgress','operationProgressLabel','operationProgressValue',
 'operationProgressDetail','operationProgressBar','fileLoadStatus','textInput','databasePanel'])
 controls.set(id,element(id));
const host=controls.get('operationProgress');
const events={};
const document={
  getElementById:id=>controls.get(id)||null,
  createElement:()=>element('actions'),
  addEventListener:(name,fn)=>{events[name]=fn;}
};
let added=0,dbEntries=null,originalFolderCalls=0,originalManyCalls=0,buttonsEnabled=true;
const inputBytes=0, fileCount=21, each=1900*1024; // ~40 MB; every file <= 2 MB
const files=Array.from({length:fileCount},(_,i)=>({name:'artykul-'+i+'.txt',size:each}));
const entries=files.map(file=>({file,relativePath:'WybranyFolder/'+file.name}));
const context={
  document, TextEncoder, clearTimeout:()=>{},timerUkryciaPostepu:0,
  importBazyAktywny:false,
  ustawZajetoscOperacji:v=>{buttonsEnabled=!v;},
  ustawStatusBazy:()=>{},
  pokazPostepOperacji:()=>1,zakonczPostepOperacji:()=>{},bladPostepuOperacji:()=>{},
  aktualizujPostepOperacji:()=>{},
  zbierzPlikiZKataloguHandle:async()=>entries,
  dodajFolderZHandle:async()=>{originalFolderCalls++;},
  dodajPlikiZFileList:async()=>{originalManyCalls++;},
  importujPlikiDoBazy:async data=>{dbEntries=data;added++;},
};
runInNewContext(code,context,{filename:'import-recovery.js'});
assert.equal(host.hidden,true);
await context.dodajFolderZHandle({name:'WybranyFolder'});
assert.equal(originalFolderCalls,0,'40 MB must not go into the single-text analysis');
assert.equal(controls.get('soraImportDatabase').hidden,false);
assert.equal(controls.get('soraImportClose').hidden,false);
assert.equal(buttonsEnabled,true,'Buttons unlocked after oversized folder');
assert.match(controls.get('operationProgressDetail').textContent,/1800 KB/);
await controls.get('soraImportDatabase').events.click();
assert.equal(added,1);
assert.equal(dbEntries.length,fileCount);
assert.equal(host.hidden,true);
// Reopen same oversize and dismiss without writing anything.
await context.dodajPlikiZFileList(files,true);
assert.equal(originalManyCalls,0);
assert.equal(controls.get('soraImportClose').hidden,false);
controls.get('soraImportClose').click();
assert.equal(host.hidden,true);
assert.equal(added,1);
assert.equal(buttonsEnabled,true);
// Escape also closes recoverable error.
await context.dodajPlikiZFileList(files,true);
events.keydown({key:'Escape'});
assert.equal(host.hidden,true);
assert.equal(added,1);
console.log('PASS: 40 MB folder never sent to 1.8 MB analysis, reusable DB queue, Close/Escape, no implicit write');
