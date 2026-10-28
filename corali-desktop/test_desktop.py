import base64
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
import pymupdf as pdf
from PIL import Image
from app import Application, make_server
from csv_tools import CsvSession
import pdf_tools


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.app=Application(Path(self.temp.name)/'data');self.work=Path(self.temp.name)
    def source(self,name,data):return self.app.resolve(self.app.import_bytes(name,data)['id'])
    def document(self,*texts):
        with pdf.open() as doc:
            for text in texts:doc.new_page().insert_text((50,80),text,fontsize=12)
            return self.source('prova.pdf',doc.tobytes())
    def run_pdf(self,action,source,**options):return self.app.dispatch({'cmd':'pdf','action':action,'ids':[self.app.meta(source)['id']],**options})
    def output(self,result):return self.app.resolve(result['files'][0]['id'])
    def test_pdf_reorders_actual_content_without_changing_source(self):
        source=self.document('PRIMA','SECONDA','TERZA');raw=source.read_bytes();result=self.run_pdf('organize',source,pages='3,1-2')
        with pdf.open(self.output(result)) as doc:self.assertEqual([p.get_text().strip() for p in doc],['TERZA','PRIMA','SECONDA'])
        self.assertEqual(source.read_bytes(),raw)
    def test_replace_removes_old_text_from_saved_content(self):
        source=self.document('Incontro lunedi');raw=source.read_bytes();result=self.run_pdf('replace',source,find='lunedi',replacement='martedi')
        with pdf.open(self.output(result)) as doc:
            text=doc[0].get_text();self.assertIn('martedi',text);self.assertNotIn('lunedi',text)
        self.assertEqual(source.read_bytes(),raw)
    def test_merge_split_rotate_and_numbers(self):
        a=self.document('Uno','Due');b=self.document('Tre')
        merged=self.app.dispatch({'cmd':'pdf','action':'merge','ids':[self.app.meta(x)['id'] for x in (a,b)]})
        with pdf.open(self.output(merged)) as doc:self.assertEqual(len(doc),3)
        split=self.run_pdf('split',a);self.assertEqual(len(split['files']),2)
        rotate=self.run_pdf('rotate',a,degrees=90,pages='1')
        with pdf.open(self.output(rotate)) as doc:self.assertEqual(doc[0].rotation,90);self.assertEqual(doc[1].rotation,0)
        numbers=self.run_pdf('numbers',a)
        with pdf.open(self.output(numbers)) as doc:self.assertIn('1',doc[0].get_text());self.assertIn('2',doc[1].get_text())
    def test_compression_reduces_photographic_pdf(self):
        import random,io
        image=Image.frombytes('RGB',(1800,1800),random.Random(12).randbytes(1800*1800*3));buffer=io.BytesIO();image.save(buffer,'PNG')
        with pdf.open() as doc:
            page=doc.new_page();page.insert_image(page.rect,stream=buffer.getvalue());source=self.source('foto.pdf',doc.tobytes())
        result=self.run_pdf('compress',source,mode='strong');self.assertLess(result['after'],result['before']//2)
        with pdf.open(self.output(result)) as doc:self.assertGreater(len(doc[0].get_pixmap().samples),0)
    def test_annotations_and_form_saved(self):
        with pdf.open() as doc:
            page=doc.new_page();widget=pdf.Widget();widget.field_name='Nome';widget.field_type=pdf.PDF_WIDGET_TYPE_TEXT;widget.rect=pdf.Rect(40,100,240,130);page.add_widget(widget);source=self.source('modulo.pdf',doc.tobytes())
        filled=self.run_pdf('form',source,fields={'Nome':'Esempio'})
        with pdf.open(self.output(filled)) as doc:self.assertEqual(next(doc[0].widgets()).field_value,'Esempio')
        added=self.run_pdf('annotate',source,edits=[{'page':0,'type':'text','x':.1,'y':.3,'text':'Copia di prova','size':14,'color':'#174b58'},{'page':0,'type':'draw','points':[[.1,.4],[.2,.45]],'size':2}])
        with pdf.open(self.output(added)) as doc:self.assertIn('Copia di prova',doc[0].get_text())
    def test_protection_requires_password_and_owner_for_unlock(self):
        source=self.document('Riservato');secured=self.output(self.run_pdf('protect',source,newPassword='prova1234'))
        with self.assertRaisesRegex(ValueError,'Password'):pdf_tools.info(secured,{})
        self.assertIn('Riservato',pdf_tools.info(secured,{'password':'prova1234'})['text'])
        unlocked=self.run_pdf('unlock',secured,password='prova1234')
        with pdf.open(self.output(unlocked)) as doc:self.assertFalse(doc.needs_pass)
        with pdf.open() as doc:
            doc.new_page().insert_text((40,40),'Esterno');external=self.source('esterno.pdf',doc.tobytes(encryption=pdf.PDF_ENCRYPT_AES_256,owner_pw='owner456',user_pw='user123',permissions=pdf.PDF_PERM_PRINT))
        with self.assertRaisesRegex(ValueError,'proprietario'):self.run_pdf('unlock',external,password='user123')
    def test_csv_keeps_identifiers_decimals_accents_and_separator(self):
        source=self.source('dati.csv','codice;importo;nome\r\n00123;12,50;città\r\n'.encode('cp1252'));raw=source.read_bytes();s=CsvSession(source)
        self.assertEqual(s.delimiter,';');self.assertEqual(s.encoding,'cp1252');self.assertEqual(s.rows[1],['00123','12,50','città'])
        s.apply([{'row':1,'column':1,'value':'14,70'}]);dest=self.work/'risultato.csv';s.save(dest)
        self.assertEqual(CsvSession(dest).rows[1],['00123','14,70','città']);self.assertEqual(source.read_bytes(),raw)
    def test_csv_quote_newline_unicode_and_atomic_rejection(self):
        source=self.source('unicode.csv','codice,note\n0007,"prima riga\nseconda, riga"\n'.encode('utf-8-sig'));s=CsvSession(source);before=[r.copy() for r in s.rows]
        with self.assertRaises(ValueError):s.apply([{'row':1,'column':0,'value':'cambio'},{'row':999,'column':0,'value':'x'}])
        self.assertEqual(s.rows,before);dest=self.work/'salvato.csv';s.save(dest);self.assertEqual(CsvSession(dest).rows,before);self.assertTrue(dest.read_bytes().startswith(b'\xef\xbb\xbf'))
    def test_paths_cannot_escape_registered_files(self):
        outside=self.work/'secret.txt';outside.write_text('secret')
        for id in ('../secret.txt',str(outside),'cache/../../secret.txt'):
            with self.assertRaises(ValueError):self.app.resolve(id)
    def test_office_commit_preserves_original_and_validates_actual_zip(self):
        import io
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr('[Content_Types].xml','<Types/>');z.writestr('word/document.xml','<document/>')
        source=self.source('documento.docx',data.getvalue());hash=hashlib.sha256(source.read_bytes()).hexdigest();sid=self.app.new_office(source)['session']
        raw=data.getvalue();token=self.app.office({'cmd':'begin','size':len(raw)},sid)['token']
        self.app.office({'cmd':'chunk','token':token,'offset':0,'data':base64.b64encode(raw).decode()},sid);saved=self.app.office({'cmd':'commit','token':token},sid)
        self.assertTrue(saved['originalUnchanged']);self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),hash)
    def test_macros_and_signed_office_remain_readonly(self):
        import io
        for extra in ('word/vbaProject.bin','_xmlsignatures/sig1.xml'):
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as z:z.writestr('word/document.xml','<document/>');z.writestr(extra,b'x')
            source=self.source('macro.docx',buffer.getvalue());self.assertFalse(self.app.office_inspect(source)['editable'])
    def test_empty_workbook_protection_is_editable_active_protection_is_not(self):
        import io
        for content,allowed in [('<workbookProtection/>',True),('<workbookProtection lockStructure="0"/>',True),('<workbookProtection lockStructure="1"/>',False),('<sheetProtection sheet="1"/>',False)]:
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as z:z.writestr('xl/workbook.xml','<workbook>'+content+'</workbook>')
            source=self.source('foglio.xlsx',buffer.getvalue());self.assertEqual(self.app.office_inspect(source)['editable'],allowed)
    def test_http_rejects_missing_token_cross_origin_and_host_spoofing(self):
        server=make_server(self.app);threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(headers):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request('POST','/rpc',json.dumps({'cmd':'init'}),headers);response=c.getresponse();status=response.status;data=response.read();c.close();return status,data
        self.assertEqual(request({})[0],403)
        self.assertEqual(request({'X-Corali-Token':self.app.token,'Origin':'https://example.com'})[0],403)
        self.assertEqual(request({'X-Corali-Token':self.app.token,'Host':'evil.example'})[0],403)
        status,data=request({'X-Corali-Token':self.app.token,'Origin':self.app.origin});self.assertEqual(status,200);self.assertTrue(json.loads(data)['ok'])
    def test_real_cedro_conversion_produces_new_image(self):
        if not self.app.cedro.is_file():self.skipTest('Cedro not installed')
        import io
        buffer=io.BytesIO();Image.new('RGB',(32,24),'#bfa2e6').save(buffer,'PNG');source=self.source('colore.png',buffer.getvalue());before=source.read_bytes()
        result=self.app.dispatch({'cmd':'convert','ids':[self.app.meta(source)['id']],'action':'jpeg','quality':82})
        with Image.open(self.output(result)) as image:self.assertEqual(image.size,(32,24));self.assertEqual(image.format,'JPEG')
        self.assertEqual(source.read_bytes(),before)
    def test_conversion_catalog_works_after_cancel(self):
        if not self.app.cedro.is_file():self.skipTest('Cedro not installed')
        source=self.source('test.txt',b'Testo di prova');self.app.stop()
        result=self.app.dispatch({'cmd':'catalog','id':self.app.meta(source)['id']});self.assertTrue(result['actions'])

    def test_integrated_engine_honours_dpi_and_keeps_private_settings(self):
        source=self.document('Risoluzione di prova');id=self.app.meta(source)['id'];dimensions=[]
        catalog=self.app.dispatch({'cmd':'catalog','id':id})['actions']
        self.assertTrue(next(a for a in catalog if a['id']=='png')['options'])
        for dpi in (100,200):
            result=self.app.dispatch({'cmd':'convert','ids':[id],'action':'png','options':{'pdf_dpi':str(dpi),'ocr_lang':'it','ocr_max':0}})
            with Image.open(self.output(result)) as image:dimensions.append(image.size)
        self.assertAlmostEqual(dimensions[1][0]/dimensions[0][0],2,delta=.01)
        settings=(self.app.root/'engine-config/Cedro/config.txt').read_text()
        self.assertIn('ocr_lang=it',settings);self.assertIn('dest=same',settings)
        with self.assertRaises(ValueError):self.app.engine_settings({'ocr_lang':'it\ndest=fixed'})

    def test_removed_external_window_command_is_not_available(self):
        with self.assertRaisesRegex(ValueError,'Comando non disponibile'):self.app.dispatch({'cmd':'cedro'})

    def test_cli_progress_is_visible_before_process_exits(self):
        import sys,time
        finished=threading.Event();errors=[]
        def run():
            try:self.app.command([sys.executable,'-u','-c',"import time; print('Scaricamento 37%',flush=True); time.sleep(.8)"])
            except Exception as e:errors.append(e)
            finally:finished.set()
        thread=threading.Thread(target=run);thread.start()
        deadline=time.monotonic()+2
        while self.app.progress['percent']!=37 and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.app.progress['percent'],37);self.assertFalse(finished.is_set());thread.join(3);self.assertFalse(errors)

    def test_transcription_recovers_from_gpu_crash(self):
        from unittest.mock import patch
        source=self.source('voce.mp3',b'mp3');calls=[]
        def command(args,timeout=1800):
            calls.append(args)
            if len(calls)==1:raise ValueError('il motore si è chiuso all’improvviso')
            Path(args[2]).with_suffix('.txt').write_text('Trascrizione recuperata',encoding='utf8')
        with patch.object(self.app,'command',command):
            result=self.app.dispatch({'cmd':'transcribe','ids':[self.app.meta(source)['id']],'model':0})
        self.assertEqual(len(calls),2);self.assertIn('--cpu',calls[1]);self.assertEqual(self.output(result).read_text(),'Trascrizione recuperata')

    def test_default_data_avoids_msix_appdata_and_preserves_legacy_results(self):
        import os
        from unittest.mock import patch
        home=self.work/'utente';legacy=self.work/'localappdata';old=legacy/'CoraliLab/outputs/sessione/trascritto.txt';old.parent.mkdir(parents=True);old.write_text('Risultato già prodotto',encoding='utf8')
        with patch('app.Path.home',return_value=home),patch.dict(os.environ,{'LOCALAPPDATA':str(legacy)}):
            app=Application();result=next(f for f in app.scan() if f['output']);new=app.resolve(result['id'])
        self.assertEqual(app.root,home/'CoraliLab');self.assertEqual(new.read_bytes(),old.read_bytes());self.assertFalse(new.is_relative_to(legacy))

    def test_in_progress_files_are_not_presented_as_completed_results(self):
        folder=self.app.folder();marker=folder/'.corali-pending';marker.touch();(folder/'copia.mp3').write_bytes(b'audio')
        self.assertFalse(any(f['output'] for f in self.app.scan()))
        (folder/'copia.mp3').unlink();(folder/'trascrizione.txt').write_text('Finito');marker.unlink()
        self.assertEqual([f['name'] for f in self.app.scan() if f['output']],['trascrizione.txt'])

    def test_export_reports_selected_path_and_cancel_writes_nothing(self):
        from unittest.mock import Mock
        source=self.source('test.txt',b'Una copia');target=self.work/'scelta.txt'
        self.app.window=Mock();self.app.window.create_file_dialog.return_value=[str(target)]
        result=self.app.export(source);self.assertTrue(result['saved']);self.assertEqual(Path(result['path']),target);self.assertEqual(target.read_bytes(),source.read_bytes())
        self.app.window.create_file_dialog.return_value=None
        self.assertEqual(self.app.export(source),{'saved':False,'path':''});self.assertEqual(target.read_bytes(),b'Una copia')


if __name__=='__main__':unittest.main(verbosity=2)
