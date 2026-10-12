"""Dodatkowy audyt: QtWebEngine bez PyInstaller, bez bazy, bez WebView hosta."""
from pathlib import Path
import faulthandler
import os
import sys

out=Path(os.environ.get('SORA_QT_DIAGNOSTICS') or '.')
out.mkdir(parents=True,exist_ok=True)
handle=(out/'unfrozen-qt-fault.txt').open('w',encoding='utf-8')
faulthandler.enable(file=handle,all_threads=True)
def step(value):
    with (out/'unfrozen-qt-stages.txt').open('a',encoding='utf-8') as file:
        file.write(value+'\n')
        file.flush()
os.environ['QT_API']='pyqt6'
step('START Python '+sys.version)
from PyQt6.QtWidgets import QApplication
step('IMPORTED QApplication')
from PyQt6.QtWebEngineWidgets import QWebEngineView
step('IMPORTED QtWebEngine')
app=QApplication([])
step('CREATED QApplication')
view=QWebEngineView()
step('CREATED QWebEngineView')
view.setHtml('<html><body>Sora diagnostyka Qt</body></html>')
step('SUBMITTED HTML')
app.processEvents()
step('PROCESSED EVENT LOOP')
view.deleteLater()
app.processEvents()
step('PASS unfrozen Qt control')
