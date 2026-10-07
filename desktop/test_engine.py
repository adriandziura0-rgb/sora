from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from engine import Engine, runtime_asset, runtime_identity

TEXTS=[
    'Premier powiedział, że rząd przedstawi projekt ustawy. Sejm omówi nowe przepisy.',
    'TYTUŁ: Nowy szpital\nŹRÓDŁO: PAP\nURL: https://example.com/news\nTREŚĆ: Rada miasta zatwierdziła budowę szpitala. Mieszkańcy oceniają projekt pozytywnie.',
    'Zdaniem autora decyzja ministra jest błędna. „To ważny krok” — powiedział burmistrz. Komisja przeprowadzi kontrolę.',
    'Warszawa. Prezydent podpisał ustawę. Opozycja krytykuje koszty projektu, a rząd zapowiada oszczędności.',
]

def stable(value):
    if isinstance(value,dict):return {k:stable(v) for k,v in value.items() if k not in {'analysis_run_id','analysis_generated_at','generated_at','utworzono','czas_generowania','timestamp'}}
    if isinstance(value,list):return [stable(v) for v in value]
    return value

with tempfile.TemporaryDirectory() as tmp:
    home=Path(tmp)/'desktop'
    e=Engine(home)
    reference=Path(tmp)/'phone'
    with zipfile.ZipFile(runtime_asset()) as z:z.extractall(reference)
    for relative in ['app.py']+[p.relative_to(reference).as_posix() for p in (reference/'clean_core').rglob('*.py')]:
        active=home/'runtime'/e.identity['asset_sha256']/relative
        assert active.read_bytes()==(reference/relative).read_bytes(),relative
    source=Path(tmp)/'cases.json';source.write_text(json.dumps(TEXTS))
    output=Path(tmp)/'phone-results.json'
    script="""import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import app
cases=json.loads(Path(sys.argv[2]).read_text())
with app.app.test_client() as client:
 results=[client.post('/api/analizuj',json={'tekst':text}).get_json() for text in cases]
Path(sys.argv[3]).write_text(json.dumps(results,ensure_ascii=False),encoding='utf-8')
"""
    env=os.environ.copy();env['DROGOWSKAZY_DB_PATH']=str(reference/'data/phone.sqlite3')
    subprocess.run([sys.executable,'-c',script,str(reference),str(source),str(output)],check=True,env=env)
    expected=json.loads(output.read_text('utf-8'))
    for text,result in zip(TEXTS,expected):
        actual=e.request('/api/analizuj',{'tekst':text})
        assert stable(actual)==stable(result),'Phone/PC result mismatch'
        report=e.request('/api/raport',{'tekst':text,'analysis_run_id':actual['analysis_run_id']})
        assert report['analysis_run_id']==actual['analysis_run_id']
    for i,text in enumerate(TEXTS):
        path=Path(tmp)/f'article{i}.txt';path.write_text(text,encoding='utf-8')
        e.import_file(path,f'Grupa{i%2}/article{i}.txt')
    e.stop()
    assert e.request('/api/baza/status')['stats']['done']==4
    assert e.import_file(Path(tmp)/'article0.txt','Grupa0/article0.txt')['status']=='duplicate'
    groups=e.request('/api/baza/porownanie/grupy?mode=folder')['groups']
    assert len(groups)==2,groups
    from urllib.parse import urlencode
    comparison=e.request('/api/baza/porownanie?'+urlencode([('mode','folder')]+[('group',g['id']) for g in groups]))
    assert comparison
    e.backup(Path(tmp)/'copy.sqlite3')
    db=sqlite3.connect(Path(tmp)/'copy.sqlite3')
    try:assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    finally:db.close()
    (Path(tmp)/'identity.json').write_text(json.dumps(e.identity))
    print('PASS: unchanged shared engine, four PHONE/PC parity cases, report consistency, native file adapter, queue, duplicate detection, group comparison, SQLite backup')
