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
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
    '--name','Sora','--paths',str(extracted),'--collect-submodules','clean_core',
    '--collect-all','flask','--add-data',str(asset)+';.',str(root/'desktop/sora_pc.py')],check=True,cwd=root)
output=root/'dist/Sora'
(output/'SILNIK_PHONE_PC.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
(output/'INSTRUKCJA.txt').write_text((root/'desktop/README.md').read_text('utf-8'),encoding='utf-8')
exe=output/'Sora.exe'
assert exe.read_bytes()[:2]==b'MZ'
print('Windows executable:',exe)
