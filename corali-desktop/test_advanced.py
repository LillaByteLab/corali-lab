import hashlib, json, tempfile, threading, unittest, zipfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
import pymupdf
import app, workspace_tools as tools


class AdvancedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.a=app.Application(self.root/'data')
    def tearDown(self):self.a.advanced.ai.stop();self.tmp.cleanup()
    def imported(self,name,raw):return self.a.import_bytes(name,raw)
    def test_decimal_reduction_and_bounds(self):
        self.assertEqual(tools.tariff('10,05','50')['amount'],'5.03')
        self.assertEqual(tools.tariff('120','100')['amount'],'0.00')
        for value in ('NaN','Infinity','-1','1.000,00'):
            with self.assertRaises(ValueError):tools.tariff(value,'20')
        with self.assertRaises(ValueError):tools.tariff('100','101')
    def test_xlsx_literal_formula_injection_and_zeros(self):
        path=self.root/'safe.xlsx';tools.write_xlsx(path,[('Dati',[['Codice','Valore'],['00123','=WEBSERVICE("https://example.invalid")']])])
        with zipfile.ZipFile(path) as z:
            xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertNotIn('<f>',xml);self.assertIn('00123',xml);self.assertNotIn('mergeCell',xml)
    def test_tariff_export_has_explicit_formula_and_cache(self):
        r=self.a.dispatch({'cmd':'tariff','base':'10,05','rate':'50','export':True})
        with zipfile.ZipFile(self.a.resolve(r['files'][0]['id'])) as z:
            xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('ROUND(A2*(1-B2/100),2)',xml);self.assertIn('5.03',xml)
    def test_save_text_preserves_source_and_roundtrips(self):
        src=self.imported('testo.txt','Testo originale'.encode());before=self.a.resolve(src['id']).read_bytes();r=self.a.dispatch({'cmd':'saveText','text':'Nuova versione\nSeconda riga','name':'Revisione'})
        word=next(f for f in r['files'] if f['name'].endswith('.docx'));self.assertIn('Nuova versione',tools.text(self.a.resolve(word['id'])));self.assertEqual(before,self.a.resolve(src['id']).read_bytes())
    def test_rename_copy_rejects_path_and_retains_original(self):
        f=self.imported('origine.csv',b'a;b\n001;2');r=self.a.dispatch({'cmd':'renameCopy','id':f['id'],'name':'Nuovo'})
        self.assertEqual(self.a.resolve(r['files'][0]['id']).read_bytes(),self.a.resolve(f['id']).read_bytes())
        with self.assertRaises(ValueError):self.a.dispatch({'cmd':'renameCopy','id':f['id'],'name':'../fuga'})
    def test_preferred_folder_non_overwrite(self):
        folder=self.root/'exports';folder.mkdir();self.a.dispatch({'cmd':'preferences','folder':str(folder),'directSave':True});f=self.imported('prova.txt',b'abc')
        one=self.a.dispatch({'cmd':'export','id':f['id']});two=self.a.dispatch({'cmd':'export','id':f['id']});self.assertNotEqual(one['path'],two['path']);self.assertEqual(Path(two['path']).read_bytes(),b'abc')
        with self.assertRaises(ValueError):self.a.dispatch({'cmd':'preferences','folder':str(self.a.root/'inputs'),'directSave':True})
    def test_batch_partial_success_is_explicit(self):
        doc=pymupdf.open();doc.new_page().insert_text((40,40),'Documento');raw=doc.tobytes();doc.close();good=self.imported('valido.pdf',raw);bad=self.imported('invalido.pdf',b'not a pdf')
        r=self.a.dispatch({'cmd':'batch','operation':'compress','ids':[bad['id'],good['id']]});self.assertEqual([i['ok'] for i in r['items']],[False,True]);self.assertEqual(len(r['files']),1)
    def test_repeat_detection_does_not_rewrite(self):
        raw='questa frase contiene sempre le stesse parole ripetute qui '*8;self.assertTrue(tools.repetition_warnings(raw));self.assertIn('frase',raw)
    def test_ai_limits_before_start_and_no_cloud(self):
        engine=self.a.advanced.ai
        with patch.object(engine,'start',side_effect=AssertionError('must not start')):
            with self.assertRaises(ValueError):engine.ask('', '', 'formule',threading.Event())
            with self.assertRaises(ValueError):engine.ask('test','x'*10001,'formule',threading.Event())
    def test_ai_download_rejects_digest(self):
        import io
        class Response(io.BytesIO):headers={'Content-Length':'3'}
        with patch('urllib.request.urlopen',return_value=Response(b'abc')):
            with self.assertRaises(ValueError):self.a.advanced.ai.download({'url':'https://example.invalid','sha256':'0'*64},self.root/'bad.bin',lambda x:None,threading.Event())
        self.assertFalse((self.root/'bad.bin').exists());self.assertFalse((self.root/'bad.bin.part').exists())
    def test_register_synthetic_cross_page_identity(self):
        doc=pymupdf.open();page=doc.new_page(width=842,height=595)
        page.insert_text((220,60),'Registro mensile della classe 1A (ESEMPIO)');page.insert_text((220,80),'Situazione del mese di Settembre')
        for n in range(30):page.insert_text((180+n*16.8,125),str(n+1).zfill(2),fontsize=7)
        for n,k in enumerate(('P','A','R','U','M')):page.insert_text((710+n*25,110),k,fontsize=7)
        page.insert_text((7,145),'ALUNNO ESEMPIO');page.insert_text((7,157),'(01-01-2020)');page.insert_text((181,145),'P',fontsize=7);page.insert_text((181,154),'M',fontsize=7)
        for n,v in enumerate((1,0,0,0,1)):page.insert_text((710+n*25,148),str(v),fontsize=7)
        page.insert_text((7,570),'ALUNNO FITTIZIO');page.insert_text((181,570),'P',fontsize=7)
        for n,v in enumerate((1,0,0,0,0)):page.insert_text((710+n*25,575),str(v),fontsize=7)
        page=doc.new_page(width=842,height=595);page.insert_text((7,40),'(02-02-2020)');path=self.root/'registro.pdf';doc.save(path);doc.close()
        sheets,warnings=tools.register(path);self.assertEqual(len(sheets[0][1]),3);self.assertEqual(warnings,[]);self.assertEqual(sheets[0][1][2][1],'02-02-2020');self.assertEqual(sheets[0][1][1][4],'P\nM')
    def test_unrecognized_register_fails(self):
        doc=pymupdf.open();doc.new_page().insert_text((20,20),'Non è un registro');path=self.root/'altro.pdf';doc.save(path);doc.close()
        with self.assertRaises(ValueError):tools.register(path)

if __name__=='__main__':unittest.main()
