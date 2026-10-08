"""Cross-device merge regression and a real PC fixture for Android SAF tests."""
from pathlib import Path
import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app/src/main/python'))
from data_transfer import export_zip, merge_zip, runtime_identity


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--fixture');parser.add_argument('--verify-phone');args=parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);runtime=root/'runtime'
        with zipfile.ZipFile(ROOT/'app/src/main/assets/drogowskazy-runtime.zip') as z:z.extractall(runtime)
        sys.path.insert(0,str(runtime))
        from clean_core.document_database import DocumentDatabase
        from clean_core.version import APP_VERSION
        from clean_core.classifier import analyze_text
        from clean_core.api_pl import analiza_po_polsku
        identity=runtime_identity(runtime)
        sys.path.insert(0,str(ROOT/'desktop'))
        from engine import runtime_identity as asset_identity
        assert identity['engine_sha256']==asset_identity()['engine_sha256'],'PHONE/PC identity mismatch'
        def add(store,text,name):
            doc=store.begin_import(text=text,filename=name,relative_path='Transfer/'+name,extension='.txt',encoding='utf-8',source_bytes=len(text.encode()),app_version=APP_VERSION)['document']
            result=analiza_po_polsku(analyze_text(text));result['analysis_run_id']='transfer-'+doc['content_sha256'][:16]
            store.mark_success(doc['id'],result)
            return doc['id']
        def sql(path,query,params=()):
            db=sqlite3.connect(path)
            try:
                out=db.execute(query,params).fetchall();db.commit();return out
            finally:db.close()
        def dump(path):
            db=sqlite3.connect(path)
            try:return '\n'.join(db.iterdump())
            finally:db.close()
        phone=DocumentDatabase(runtime/'data/drogowskazy.sqlite3');pc=DocumentDatabase(root/'pc.sqlite3')
        p=add(phone,'Jan Kowalski powiedział, że projekt wymaga poprawek.','wspolny.txt')
        q=add(phone,'Anna Nowak stwierdziła, że komisja powinna opublikować dokumenty.','telefon.txt')
        local=add(pc,'Michał Zieliński ocenił, że decyzja była przedwczesna.','komputer.txt')
        common=add(pc,'Jan Kowalski powiedział, że projekt wymaga poprawek.','wspolny.txt')
        old='2026-01-01T10:00:00+00:00';new='2026-01-02T10:00:00+00:00'
        sql(phone.path,'UPDATE documents SET updated_at=?,analysis_run_id=? WHERE id=?',(old,'starsza',p))
        sql(pc.path,'UPDATE documents SET updated_at=?,analysis_run_id=? WHERE id=?',(new,'nowsza',common))
        phone.save_gold_annotation(document_id=p,expected_relations=[{'speaker':'Jan Kowalski','claim':'projekt wymaga poprawek','target':'','source':''}],note='starsza',app_version=APP_VERSION)
        pc.save_gold_annotation(document_id=common,expected_relations=[],note='nowsza',app_version=APP_VERSION)
        sql(phone.path,'UPDATE gold_document_annotations SET updated_at=?',(old,))
        sql(pc.path,'UPDATE gold_document_annotations SET updated_at=?',(new,))
        phone.save_benchmark_label(document_id=q,relation_id='relacja-telefonu',overall_label='correct',note='z telefonu')
        packet=root/'phone.zip';export_zip(phone.path,packet,identity,'PHONE')
        first=merge_zip(pc.path,packet,identity,root/'pc-transfers')
        assert first['documents_added']==1 and first['documents_unchanged']==1
        assert sql(pc.path,'SELECT analysis_run_id FROM documents WHERE id=?',(common,))[0][0]=='nowsza'
        assert sql(pc.path,'SELECT note FROM gold_document_annotations WHERE document_id=?',(common,))[0][0]=='nowsza'
        mapped=sql(pc.path,'SELECT id FROM documents WHERE filename=?',('telefon.txt',))[0][0]
        assert mapped!=q and sql(pc.path,'SELECT document_id FROM manual_benchmark_labels')[0][0]==mapped,'Foreign key remap failed'
        again=merge_zip(pc.path,packet,identity,root/'pc-transfers')
        assert again['documents_added']==again['documents_updated']==again['annotations_updated']==again['events_added']==0
        assert Path(first['backup']).exists() and Path(first['archived_package']).exists()
        back=root/'pc.zip';export_zip(pc.path,back,identity,'PC');merge_zip(phone.path,back,identity,root/'phone-transfers')
        assert sql(phone.path,'SELECT COUNT(*) FROM documents')[0][0]==3
        assert sql(phone.path,'SELECT analysis_run_id FROM documents WHERE id=?',(p,))[0][0]=='nowsza'
        assert sql(phone.path,'SELECT note FROM gold_document_annotations WHERE document_id=?',(p,))[0][0]=='nowsza'
        # Equal-time divergent edits stay local and remain available in archived input.
        sql(phone.path,'UPDATE documents SET analysis_run_id=? WHERE id=?',('rownoczesna',p))
        equal=root/'equal.zip';export_zip(phone.path,equal,identity,'PHONE')
        conflict=merge_zip(pc.path,equal,identity,root/'pc-transfers')
        assert conflict['conflicts']>=1 and sql(pc.path,'SELECT analysis_run_id FROM documents WHERE id=?',(common,))[0][0]=='nowsza'
        before=dump(pc.path)
        with zipfile.ZipFile(packet) as z:manifest=json.loads(z.read('manifest.json'));blob=z.read('core.sqlite3')
        for index,change in enumerate([{'engine_sha256':'wrong'},{'schema_version':999},{'transfer_version':999},{'database_sha256':'wrong'}]):
            bad=root/f'bad{index}.zip'
            with zipfile.ZipFile(bad,'w') as z:z.writestr('manifest.json',json.dumps({**manifest,**change}));z.writestr('core.sqlite3',blob)
            try:merge_zip(pc.path,bad,identity,root/'pc-transfers');raise AssertionError('Invalid package accepted')
            except ValueError:pass
            assert dump(pc.path)==before,'Rejected import modified target'
        bad=root/'path.zip'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('../core.sqlite3',blob);z.writestr('manifest.json',json.dumps(manifest))
        try:merge_zip(pc.path,bad,identity,root/'pc-transfers');raise AssertionError('Unsafe ZIP accepted')
        except ValueError:pass
        # Failure after document and annotation INSERTs must roll everything back.
        rollback=DocumentDatabase(root/'rollback.sqlite3')
        sql(rollback.path,"CREATE TRIGGER fail_events BEFORE INSERT ON import_events BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        initial=dump(rollback.path)
        try:merge_zip(rollback.path,packet,identity,root/'rollback-backups');raise AssertionError('Trigger did not fail')
        except sqlite3.IntegrityError:pass
        assert dump(rollback.path)==initial,'Partial import committed'
        assert sql(pc.path,'PRAGMA foreign_key_check')==[]
        # Exercise the Android bootstrap entry points with the SAME module.
        import android_bootstrap
        native=root/'native.zip';android_bootstrap.export_transfer(str(runtime),str(native))
        android_bootstrap.import_transfer(str(runtime),str(back))
        assert sql(phone.path,'SELECT COUNT(*) FROM documents')[0][0]==3
        if args.fixture:
            fixture=DocumentDatabase(root/'fixture.sqlite3')
            ident=add(fixture,'Katarzyna Wiśniewska podkreśliła, że termin nie zostanie zmieniony.','pc-transfer.txt')
            fixture.save_gold_annotation(document_id=ident,expected_relations=[{'speaker':'Katarzyna Wiśniewska','claim':'termin nie zostanie zmieniony','target':'','source':''}],note='PC transfer fixture',app_version=APP_VERSION)
            fixture.save_benchmark_label(document_id=ident,relation_id='fixture-relation',overall_label='correct',note='PC transfer fixture')
            export_zip(fixture.path,args.fixture,identity,'PC')
        if args.verify_phone:
            received=DocumentDatabase(root/'received.sqlite3');merge_zip(received.path,args.verify_phone,identity,root/'received-backups')
            assert received.stats()['done']==7,'Actual PHONE export did not merge into PC'
        print('PASS: PHONE-PC shared transfer identity, colliding IDs remapped, union of documents, newer data protected, idempotent import, annotations, backups, concurrent conflicts, invalid packages rejected, complete rollback, Android bootstrap')

if __name__=='__main__':run()
