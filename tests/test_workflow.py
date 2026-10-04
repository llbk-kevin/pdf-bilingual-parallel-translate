"""Regenerable behavioral fixtures for naming, fonts, recovery and review evidence."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import pdf_tools as t
import workflow as w
import example_build as builder
from test_pdf_tools import source_pdf, bilingual
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


def make_font(dest, symbols=False):
    chars = set(range(32,127)) | {ord(x) for x in '中文项目数值距离条件页脚'}
    if symbols:
        chars |= {0x2243,0x2095,0x00B1,0x2212,0x03B1}
    names = ['.notdef'] + [f'u{x:04X}' for x in sorted(chars)]
    fb = FontBuilder(1000,isTTF=True)
    fb.setupGlyphOrder(names)
    glyphs={}
    for n in names:
        pen=TTGlyphPen(None)
        if n!='u0020':
            pen.moveTo((50,0));pen.lineTo((50,700));pen.lineTo((550,700));pen.lineTo((550,0));pen.closePath()
        glyphs[n]=pen.glyph()
    fb.setupCharacterMap({u:f'u{u:04X}' for u in chars})
    fb.setupGlyf(glyphs);fb.setupHorizontalMetrics({n:(600,0)for n in names})
    fb.setupHorizontalHeader(ascent=800,descent=-200)
    fb.setupNameTable({'familyName':'SyntheticSymbols' if symbols else 'SyntheticBody',
                      'styleName':'Regular','psName':'SyntheticSymbols' if symbols else 'SyntheticBody',
                      'fullName':'Synthetic Test Font'})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200)
    fb.setupPost();fb.setupMaxp();fb.save(dest)


class Upgrade(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source.pdf';source_pdf(self.source)
        for name in ('Body','Symbols'):make_font(self.root/(name+'.ttf'),name=='Symbols')
        self.state={'schema_version':2,'document':{'source_kind':'english-original'},
            'source':{'path':'source.pdf','sha256':w.digest(self.source)},
            'layout':{'pane_width_pt':240,'fonts':[{'name':n,'source':n+'.ttf','sha256':w.digest(self.root/(n+'.ttf')),'purpose':'Synthetic fixture'}for n in ('Body','Symbols')]},
            'glossary':[],'issues':[],'qc':{},'pages':[]}
        for n in (1,2):
            bid=f'p{n}-body'
            self.state['pages'].append({'source_page':n,'output_page':n,'source_rect':[0,0,240,300],
                'kind':'translated','inventory_reviewed':True,'expected_blocks':[bid],'reading_order':[bid],
                'context_reviewed':True,'context_pages':[n],
                'blocks':[{'id':bid,'kind':'paragraph','source_bbox':[20,20,220,70],
                    'target_bbox':[260,20,460,90],'source_text':'distance approximately 12 km','translation':'距离 ≃ 12 km <sub>h</sub>',
                    'font_size':10,'status':'translated'}]})
        self.sp=self.root/'state.json';self.save(self.state)
    def tearDown(self):self.temp.cleanup()
    def save(self,s):self.sp.write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8')
    def built(self,name='output'):
        result=builder.build(self.source,self.sp,self.root/(name+'.pdf'))
        return result,w.load(result['state'])
    def test_ti_names_and_missing_numbers(self):
        self.assertEqual(w.ti_filename('Designing A SEPIC Converter','设计 SEPIC 转换器','SNVA168E',role='original'),
            'snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器.pdf')
        self.assertEqual(w.ti_filename('Designing A SEPIC Converter','设计 SEPIC 转换器','SNVA168E',role='generated-translation'),
            'snva168e_Designing A SEPIC Converter_设计 SEPIC 转换器_双语左右对照翻译.pdf')
        self.assertEqual(w.ti_filename(chinese_title='耦合电感器SEPIC功率级的基本计算',document_id='ZHCACE2',english_document_id='SNVAA43',role='official-chinese'),
            'snvaa43_zhcace2_耦合电感器SEPIC功率级的基本计算.pdf')
        self.assertEqual(w.ti_filename('Multiple\nOutput: Title','中文',role='original'),'Multiple Output - Title_中文.pdf')
        self.assertEqual(w.ti_filename('Title','中文_双语左右对照翻译',role='generated-translation'),'Title_中文_双语左右对照翻译.pdf')
        self.assertNotIn('slup261',w.ti_filename('Title','中文',role='original'))
    def test_assigned_font_not_union(self):
        r,s=self.built();fr=w.check_fonts(r['state'],r['assignments'])
        self.assertTrue(fr['mechanical_pass'],fr)
        self.assertGreater(fr['fallback_runs'],0)
        a=w.load(r['assignments'])
        for item in a['runs']:item['font']='Body'
        Path(r['assignments']).write_text(json.dumps(a),encoding='utf-8')
        fr=w.check_fonts(r['state'],r['assignments'])
        self.assertIn('missing_assigned_glyph',{x['code']for x in fr['errors']})
    def test_build_rejects_missing_glyph(self):
        self.state['pages'][0]['blocks'][0]['translation']='中文 \U0001F9EC'
        self.save(self.state)
        with self.assertRaisesRegex(ValueError,'Missing glyph'):self.built()
    def test_state_edits_drive_rebuild_without_overwriting_authoring_state(self):
        before=self.sp.read_bytes();r,s=self.built('first')
        self.assertEqual(before,self.sp.read_bytes())
        same,_=self.built('same');self.assertEqual(r['sha256'],same['sha256'])
        self.state['pages'][0]['blocks'][0]['translation']='距离 24 km';self.save(self.state)
        newer,_=self.built('second');self.assertNotEqual(r['sha256'],newer['sha256'])
        self.assertIn('24 km',PdfReader(newer['output']).pages[0].extract_text())
        self.assertIn('24 km',w.load(self.sp)['pages'][0]['blocks'][0]['translation'])
    def test_table_reads_full_cells_and_overflow(self):
        b=self.state['pages'][0]['blocks'][0]
        b.update(kind='table',translation='Table summary',target_bbox=[260,20,460,160],
                 table={'source_rows':[['A','B'],['C','D']],'translated_rows':[['项目','数值'],['距离','73 km']]})
        self.save(self.state);r,s=self.built()
        self.assertIn('73 km',PdfReader(r['output']).pages[0].extract_text())
        self.assertTrue(w.check_fonts(r['state'],r['assignments'])['mechanical_pass'])
        b['target_bbox']=[260,20,270,22];self.save(self.state)
        with self.assertRaisesRegex(ValueError,'overflow'):self.built('overflow')
    def test_external_inputs_preserved_and_changed_input_rejected(self):
        dependency=self.root/'layout.json';dependency.write_text('{}',encoding='utf-8')
        self.state['layout']['inputs']=[{'path':'layout.json','sha256':w.digest(dependency)}]
        self.save(self.state);r,s=self.built()
        self.assertIn(str(dependency.resolve()),[x['path']for x in s['layout']['inputs']])
        dependency.write_text('{"changed":true}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'External input'):self.built('changed')
    def test_same_basename_different_directory_and_duplicate_font(self):
        output=self.root/'task'/self.source.name
        before=w.digest(self.source)
        r=builder.build(self.source,self.sp,output)
        self.assertTrue(output.exists());self.assertEqual(before,w.digest(self.source))
        self.state['layout']['fonts'].append(copy.deepcopy(self.state['layout']['fonts'][0]))
        self.save(self.state)
        with self.assertRaisesRegex(ValueError,'Duplicate font'):self.built('duplicate')
    def test_prevent_original_and_existing_output_overwrite(self):
        h=w.digest(self.source)
        with self.assertRaises(ValueError):builder.build(self.source,self.sp,self.source)
        self.built()
        with self.assertRaises(ValueError):self.built()
        self.assertEqual(h,w.digest(self.source))
    def test_fractional_dimensions_and_real_corruption(self):
        c=canvas.Canvas(str(self.source),pagesize=(595.276,841.89),invariant=1)
        c.drawString(40,600,'Fixed scale');c.showPage();c.save()
        out=self.root/'wide.pdf';bilingual(self.source,out)
        self.assertTrue(t.audit(self.source,out)['mechanical_pass'])
        bilingual(self.source,out,corrupt=True)
        self.assertFalse(t.audit(self.source,out)['mechanical_pass'])
    def test_empty_password_and_explicit_password(self):
        for pwd in ('','explicit-test-password'):
            out=self.root/('encrypted-'+str(bool(pwd))+'.pdf')
            writer=PdfWriter(clone_from=self.source);writer.encrypt(pwd);writer.write(out)
            t._PASSWORD=None
            if pwd:
                with self.assertRaises(ValueError):t.checked_reader(out)
            t._PASSWORD=pwd or None
            self.assertEqual(len(t.checked_reader(out).pages),2)
            self.assertEqual(t.pdf_metadata(out)['page_count'],2)
            rendered=t.open_document(out)
            try:
                page=rendered[0]
                try:self.assertGreater(t.render_image(page,72).width,0)
                finally:page.close()
            finally:rendered.close()
            bilingual_out=self.root/('bilingual-'+str(bool(pwd))+'.pdf')
            bilingual(self.source,bilingual_out)
            self.assertTrue(t.audit(out,bilingual_out)['mechanical_pass'])
            with patch.dict(os.environ,{'PDF_TEST_PASSWORD':pwd}):
                self.assertEqual(t.main(['inspect',str(out),'--password-env','PDF_TEST_PASSWORD','--out',str(self.root/('inspect-'+str(bool(pwd))+'.json'))]),0)
            t._PASSWORD=None
    def test_font_text_and_output_binding(self):
        r,s=self.built();a=w.load(r['assignments']);a['runs']=a['runs'][1:]
        Path(r['assignments']).write_text(json.dumps(a),encoding='utf-8')
        self.assertIn('font_run_text_mismatch',{x['code']for x in w.check_fonts(r['state'],r['assignments'])['errors']})
        a['output_sha256']='0'*64;Path(r['assignments']).write_text(json.dumps(a),encoding='utf-8')
        self.assertIn('stale_font_assignments',{x['code']for x in w.check_fonts(r['state'],r['assignments'])['errors']})
    def render_records(self,r,s,folder):
        dest=self.root/folder
        rc=t.main(['render',r['output'],'--source',str(self.source),'--state',r['state'],'--out',str(dest),'--dpi','72'])
        self.assertEqual(rc,0)
        index=w.load(dest/'index.json');records=[]
        self.assertFalse(index['visual_review_completed'])
        for row in index['pages']:
            records.append({'page':row['source_page'],'mode':'viewed','output_sha256':s['output']['sha256'],
                'render_index':{'path':str(dest/'index.json'),'sha256':w.digest(dest/'index.json')},
                'settings_sha256':index['settings_sha256'],
                **{k:row[k]for k in ('image_sha256','pixel_sha256','page_content_sha256')},
                'reviewer':'synthetic test only','reviewed_at':'2000-01-01T00:00:00Z',
                'evidence':'Fixture attestation; no claim of real visual review'})
        s['qc']['page_reviews']=records
        return records
    def test_review_reuse_requires_matching_page_and_context(self):
        r,s=self.built('first');old=self.render_records(r,s,'r1')
        self.assertFalse(w.validate_reviews(s,r['state']))
        # Same visual file but different byte version; separate render index is required.
        output=Path(r['output']);output.write_bytes(output.read_bytes()+b'\n% second save\n')
        s['output']['sha256']=w.digest(output);s['qc']={}
        Path(r['state']).write_text(json.dumps(s),encoding='utf-8')
        new=self.render_records(r,s,'r2')
        for row,prev in zip(new,old):row.update(mode='reused',previous=prev,reuse_reason='Identical rendered pixels, settings and semantic context')
        self.assertFalse(w.validate_reviews(s,r['state']))
        s['glossary'].append({'source':'condition','target':'限定条件'})
        self.assertTrue(w.validate_reviews(s,r['state']))
    def test_rendered_but_unviewed_stale_or_modified_image_fails(self):
        r,s=self.built();self.assertTrue(w.validate_reviews(s,r['state']))
        records=self.render_records(r,s,'r1');records[0]['mode']='rendered'
        self.assertTrue(w.validate_reviews(s,r['state']))
        records[0]['mode']='viewed';records[0]['output_sha256']='0'*64
        self.assertTrue(w.validate_reviews(s,r['state']))
        records[0]['output_sha256']=s['output']['sha256']
        (self.root/'r1/page-0001.png').write_bytes(b'changed')
        self.assertTrue(w.validate_reviews(s,r['state']))
    def test_caption_blocks_exclude_body_references_and_classify_footer(self):
        chars=[{'char':c,'bbox':[0,10,10,20]}for c in 'Figure1']
        right=[{'char':c,'bbox':[250,180,260,190]}for c in 'Figure1']
        m={'blocks':[{'id':'body','kind':'paragraph','target_bbox':[240,170,470,200]}]}
        self.assertEqual(t.caption_findings(chars,right,m,[0,0,240,300],300),[])
        m['blocks'][0].update(kind='caption',source_bbox=[0,0,100,30],figure_id='1')
        self.assertEqual(len(t.caption_findings(chars,right,m,[0,0,240,300],300)),1)
        m['blocks'][0]['kind']='footer'
        self.assertEqual(t.small_text_roles(right,m),{'footer':7})
    def test_new_uncompressed_content_is_identified(self):
        out=self.root/'output.pdf';bilingual(self.source,out)
        self.assertIn('new_uncompressed_page_contents',{x['code']for x in t.audit(self.source,out)['findings']})
        writer=PdfWriter(clone_from=out)
        for p in writer.pages:p.compress_content_streams()
        writer.write(out)
        self.assertNotIn('new_uncompressed_page_contents',{x['code']for x in t.audit(self.source,out)['findings']})


    def accepted_v2(self):
        r,s=self.built()
        self.render_records(r,s,'accepted-render')
        audit=t.audit(self.source,r['output'],s,dpi=72)
        t.write_json(audit,self.root/'audit.json')
        fonts=w.check_fonts(r['state'],r['assignments'])
        t.write_json(fonts,self.root/'fonts.json')
        s['qc'].update(content_sha256=t.content_hash(s),source_sha256=s['source']['sha256'],
            output_sha256=s['output']['sha256'],translation_pages=[1,2],visual_pages=[1,2],
            reviewer='synthetic fixture',reviewed_at='2000-01-01T00:00:00Z',structure='passed',
            audit_path='audit.json',structure_notes='Synthetic font shapes; no real semantic certification.',
            font_report={'path':'fonts.json','sha256':w.digest(self.root/'fonts.json')},
            font_assignments=Path(r['assignments']).name)
        Path(r['state']).write_text(json.dumps(s),encoding='utf-8')
        return r,s
    def test_v2_final_acceptance_requires_bound_fonts_and_viewing(self):
        r,s=self.accepted_v2()
        report=t.check_state(r['state'],True)
        self.assertTrue(report['ready_for_delivery'],report)
        self.assertFalse(report['quality_certified'])
        s['qc']['page_reviews'][0]['mode']='rendered'
        Path(r['state']).write_text(json.dumps(s),encoding='utf-8')
        self.assertFalse(t.check_state(r['state'],True)['ready_for_delivery'])
    def test_path_only_migration_retains_original_review_but_rejects_content_edits(self):
        r,s=self.accepted_v2();previous=self.root/'before-migration.json'
        previous.write_bytes(Path(r['state']).read_bytes())
        newsource=self.root/'renamed-source.pdf';self.source.rename(newsource)
        old=s['source']['path'];s['source']['path']=str(newsource)
        s['migration']={'kind':'path-only','performed_at':'2000-01-01T00:00:00Z','reason':'Explicit approved rename',
            'previous_state':{'path':previous.name,'sha256':w.digest(previous)},
            'old_source':old,'new_source':str(newsource)}
        Path(r['state']).write_text(json.dumps(s),encoding='utf-8')
        result=t.check_state(r['state'],True)
        self.assertTrue(result['ready_for_delivery'],result)
        self.assertIn('verified_path_only_migration',{x['code']for x in result['warnings']})
        s['pages'][0]['blocks'][0]['translation']='changed'
        Path(r['state']).write_text(json.dumps(s),encoding='utf-8')
        self.assertIn('stale_qc_content',{x['code']for x in t.check_state(r['state'],True)['errors']})

    def test_invalid_migration_is_checked_even_when_content_hash_matches(self):
        r,s=self.accepted_v2()
        s['migration']={'kind':'path-only','performed_at':'2000-01-01T00:00:00Z','reason':'Synthetic invalid chain',
                        'previous_state':{'path':'missing.json','sha256':'0'*64},
                        'old_source':s['source']['path'],'new_source':s['source']['path']}
        Path(r['state']).write_text(json.dumps(s),encoding='utf-8')
        self.assertIn('stale_qc_content',{x['code']for x in t.check_state(r['state'],True)['errors']})

if __name__=='__main__':unittest.main()

