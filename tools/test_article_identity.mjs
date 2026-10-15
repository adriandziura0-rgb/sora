/* A2: identical persisted article result is the ONLY export source. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const src=readFileSync(resolve(root,'runtime_source/static/app.js'),'utf8');
function slice(a,b){
  const start=src.indexOf(a),end=src.indexOf(b,start+a.length);
  assert.ok(start>=0&&end>start,'Missing '+a);
  return src.slice(start,end);
}
const code=slice('async function eksportZapisanegoArtykulu(){','async function tekstRaportuMarkdown(){');
let events=[],text='TYTUŁ: Artykuł\nTREŚĆ: Przykład',run='run-123';
const doc={id:5,content_sha256:'hash',updated_at:'2026-10-15T11:00:00',analysis_run_id:run,analyzed_at:'2026-10-15T10:00',app_version:'1.2.16'};
const result={analysis_run_id:run,raport_roboczy:'Zapisany raport',sekcje:{relacje_wypowiedzi:[]}};
const save={id:5,path:'Folder/A.txt',content_sha256:'hash',updated_at:doc.updated_at,analysis_run_id:run,analyzed_at:doc.analyzed_at,app_version:'1.2.16',oryginalnyTekst:text,zmieniony:false};
let record={document:{...doc},wynik:{...result},tekst:text};
const els={textInput:{value:text},reportBox:{textContent:''}};
const context=vm.createContext({
  aktywnyZapisanyDokument:save,ostatnieDane:result,ostatniEksport:null,$:id=>els[id],
  pobierzJson:async (u,opts)=>{events.push({u,opts});return record;},
  ustawStatusSesji:(...x)=>events.push({status:x}),
});
vm.runInContext(code,context);
const runExport=()=>vm.runInContext('pobierzEksportRaportu()',context);
let exported=await runExport();
assert.equal(exported.analysis_run_id,run);
assert.equal(exported.saved_document.id,5);
assert.deepEqual(JSON.parse(JSON.stringify(exported.raport_json)),result);
assert.deepEqual(events.map(x=>x.u),['/api/baza/dokument/5/wynik']);
record={...record,document:{...record.document,updated_at:'new timestamp'}};
assert.equal(await runExport(),null,'Background reanalysis must invalidate export');
assert.equal(events.filter(x=>x.u?.includes('/api/raport')).length,0);
record={...record,document:{...doc}};
save.zmieniony=true;assert.equal(await runExport(),null);
assert.equal(events.filter(x=>x.u).length,2,'Edited article must not trigger an HTTP analysis');
save.zmieniony=false;els.textInput.value+=' ZMIENIONY';assert.equal(await runExport(),null);
els.textInput.value=text;
context.pobierzJson=async ()=>{context.aktywnyZapisanyDokument={...save,id:6};return record;};
assert.equal(await runExport(),null,'Switch while waiting must invalidate export');
console.log('PASS: A2 stored-article export: read-only GET, identity and content checks, no silent rerun');