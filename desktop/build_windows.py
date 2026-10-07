"""Build a self-contained Windows EXE with the APK runtime as its only engine."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parents[1]
asset=root/'app/src/main/assets/drogowskazy-runtime.zip'
extracted=root/'build/phone-runtime'
extracted.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(asset) as z:z.extractall(extracted)
sys.path.insert(0,str(Path(__file__).parent))
from engine import runtime_identity
identity=runtime_identity(asset)
# Generate reference results through the unmodified PHONE runtime in a fresh
# process. The packaged EXE must reproduce them, not merely start its window.
cases=['Jan Kowalski powiedział, że projekt wymaga poprawek. Sejm omówi nowe przepisy.',
       'Zdaniem autora decyzja ministra jest błędna. Komisja przeprowadzi kontrolę.']
reference=root/'build/engine-reference.json'
script="""import sys,json,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
os.environ['DROGOWSKAZY_DB_PATH']=str(Path(sys.argv[1])/'test.sqlite3')
import app
cases=json.loads(sys.argv[2])
with app.app.test_client() as client:
 results=[client.post('/api/analizuj',json={'tekst':t}).get_json() for t in cases]
Path(sys.argv[3]).write_text(json.dumps({'cases':cases,'results':results},ensure_ascii=False),encoding='utf-8')
"""
subprocess.run([sys.executable,'-c',script,str(extracted),json.dumps(cases),str(reference)],check=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
    '--name','Sora','--paths',str(extracted),'--collect-submodules','clean_core',
    '--collect-all','flask','--collect-all','reportlab','--collect-all','PIL','--add-data',str(asset)+';.','--add-data',str(reference)+';.',str(root/'desktop/sora_pc.py')],check=True,cwd=root)
output=root/'dist/Sora'
(output/'SILNIK_PHONE_PC.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
(output/'INSTRUKCJA.txt').write_text((root/'desktop/README.md').read_text('utf-8'),encoding='utf-8')
exe=output/'Sora.exe'
assert exe.read_bytes()[:2]==b'MZ'
print('Windows executable:',exe)
