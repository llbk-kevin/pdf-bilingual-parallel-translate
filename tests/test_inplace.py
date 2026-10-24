"""Procedural regression fixtures for same-source in-place translation."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pymupdf as fitz
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject
import inplace as ip
import pdf_tools as pt
import workflow as wf
from test_workflow import make_font

class Inplace(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'source.pdf';self.sp=self.root/'state.json'
        self.font=self.root/'font.ttf';make_font(self.font,True)
    def tearDown(self):self.tmp.cleanup()
    def save_source(self,doc):doc.save(self.source);doc.close()
    def extract(self,pages='all'):
        ip.extract(self.source,self.sp,pages)
        s=wf.load(self.sp)
        s['layout']['fonts']=[{'name':'Body','source':'font.ttf','sha256':wf.digest(self.font),'purpose':'Procedural test font'}]
        for p in s['pages']:
            p['inventory_reviewed']=True;p['visual_text_review']='reviewed'
            for b in p['blocks']:
                if b['method']=='unresolved':
                    b.update(method='replace',translation='中文',status='translated',font_size=8)
        return s
    def build(self,s,name='output'):
        ip.write_json(self.sp,s)
        return ip.build(self.source,self.sp,self.root/(name+'.pdf'))
    def make_basic(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180)
        p.draw_rect((10,20,220,65),fill=(.2,.7,.6),color=None)
        p.insert_text((20,45),'Translate label',fontsize=12)
        p.insert_text((150,45),'12 + 34 = 46',fontsize=10)
        p.draw_line((10,70),(220,70),color=(0,0,0),width=2)
        self.save_source(doc)
    def assert_left_same(self,result,tolerance=0):
        state=wf.load(result['state'])
        with fitz.open(self.source) as src,fitz.open(result['output']) as out:
            for p in state['pages']:
                a=src[p['source_page']-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                b=out[p['output_page']-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
                ai=Image.frombytes('RGB',(a.width,a.height),a.samples)
                bi=Image.frombytes('RGB',(b.width,b.height),b.samples).crop((0,0,a.width,a.height))
                diff=ImageChops.difference(ai,bi)
                self.assertLessEqual(max(v[1] for v in diff.getextrema()),tolerance)
    def test_colored_background_formula_and_left_isolation(self):
        self.make_basic();s=self.extract();before=self.sp.read_bytes();r=self.build(s)
        self.assert_left_same(r)
        with fitz.open(r['output']) as out:
            p=out[0];left=p.get_text(clip=fitz.Rect(0,0,240,180));right=p.get_text(clip=fitz.Rect(240,0,480,180))
            self.assertIn('Translate label',left);self.assertNotIn('Translate label',right)
            self.assertIn('12 + 34 = 46',right);self.assertIn('中文',right)
            pix=p.get_pixmap();self.assertEqual(pix.pixel(15,25),pix.pixel(255,25))
            self.assertEqual(len(p.get_drawings()),4)
        self.assertTrue(wf.check_fonts(r['state'],r['assignments'])['mechanical_pass'])
        self.assertTrue(pt.check_state(r['state'])['valid'],pt.check_state(r['state']))
        self.assertFalse(pt.check_state(r['state'],True)['valid'])
        self.assertTrue(pt.audit(self.source,r['output'],wf.load(r['state']))['mechanical_pass'])
    def test_shared_images_alpha_masks_and_nested_forms(self):
        image=Image.new('RGBA',(12,12),(200,30,50,128));buf=io.BytesIO();image.save(buf,format='PNG')
        inner=fitz.open();p=inner.new_page(width=240,height=180)
        p.insert_image((15,70,100,150),stream=buf.getvalue());p.insert_text((20,40),'Label')
        outer=fitz.open();p=outer.new_page(width=240,height=180);p.show_pdf_page(p.rect,inner,0)
        self.save_source(outer);inner.close();s=self.extract();r=self.build(s)
        self.assert_left_same(r)
        si=pt.inventory(PdfReader(self.source));oi=pt.inventory(PdfReader(r['output']))
        self.assertEqual({x['signature'] for x in si['images']},{x['signature'] for x in oi['images']})
        self.assertEqual(len(si['images']),len(oi['images']))
        self.assertEqual(len(oi['images']),2) # image and alpha mask, each shared by both panes
    def test_crop_rotation_userunit_and_mixed_sizes(self):
        doc=fitz.open()
        for rotation in (0,90,180,270):
            p=doc.new_page(width=300,height=200);p.insert_text((40,80),'Label');p.draw_rect((60,90,160,140),fill=(1,0,0))
            p.set_cropbox(fitz.Rect(20,30,280,180));p.set_rotation(rotation)
        p=doc.new_page(width=180,height=260);p.insert_text((20,40),'Label')
        doc.xref_set_key(p.xref,'UserUnit','2')
        self.save_source(doc);s=self.extract();r=self.build(s)
        self.assert_left_same(r)
        report=pt.audit(self.source,r['output'],wf.load(r['state']))
        self.assertTrue(report['mechanical_pass'],report['findings'])
    def test_hidden_ocr_cover_and_outline_cover(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180)
        # Simulated raster lettering with an invisible OCR layer.
        image=Image.new('RGB',(80,30),'white');buf=io.BytesIO();image.save(buf,format='PNG')
        p.insert_image((20,20,100,50),stream=buf.getvalue());p.insert_text((20,40),'Scan label',render_mode=3)
        p.draw_rect((30,80,35,95),fill=(0,0,0));p.draw_rect((38,80,44,95),fill=(0,0,0))
        self.save_source(doc);s=self.extract();b=s['pages'][0]['blocks'][0]
        self.assertTrue(b['hidden_ocr'])
        with self.assertRaisesRegex(ValueError,'hidden OCR'):self.build(s)
        b.update(method='cover',cover_bbox=[20,20,100,50],reason='Raster label with hidden OCR',translation='中文')
        p=s['pages'][0];p['blocks'].append({'id':'outline-label','kind':'text','source_text':'Vector label',
            'source_bbox':[25,75,60,100],'glyph_ids':[],'glyph_ranges':[],
            'method':'cover','status':'translated','translation':'项目','allowed_bbox':[25,75,60,100],
            'cover_bbox':[25,75,60,100],'reason':'Vector outlined lettering','font_size':8,'rotation':0,'actual_bbox':None})
        p['expected_blocks']=[b['id'] for b in p['blocks']];p['reading_order']=p['expected_blocks'][:]
        r=self.build(s);self.assert_left_same(r)
        with fitz.open(r['output']) as out:
            right=out[0].get_text(clip=fitz.Rect(240,0,480,180));self.assertNotIn('Scan label',right);self.assertIn('项目',right)
    def test_overflow_source_fingerprint_and_inventory_rejected(self):
        self.make_basic();s=self.extract();s['pages'][0]['blocks'][0]['translation']='中文'*100
        with self.assertRaisesRegex(ValueError,'overflow'):self.build(s)
        self.assertFalse((self.root/'output.pdf').exists())
        s=self.extract_again();s['pages'][0]['glyphs'][0]['text']='X'
        with self.assertRaisesRegex(ValueError,'inventory changed'):self.build(s)
        s['source']['sha256']='bad'
        with self.assertRaisesRegex(ValueError,'fingerprint'):self.build(s)
    def extract_again(self):
        self.sp.unlink();return self.extract()
    def test_glyph_split_preserves_inline_symbols_and_merge(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180);p.insert_text((20,40),'Voltage 12 V');self.save_source(doc)
        s=self.extract();p=s['pages'][0];b=p['blocks'][0];all_ids=b['glyph_ids'][:]
        b.update(glyph_ids=all_ids[:7],glyph_ranges=[[0,7]],source_text='Voltage',source_bbox=[20,28,58,44],allowed_bbox=[20,28,58,44])
        keep=copy.deepcopy(b);keep.update(id='preserved-value',glyph_ids=all_ids[7:],glyph_ranges=[[0,len(all_ids)-7]],method='preserve',translation='12 V',reason='Keep exact numeric unit',source_text='12 V',source_bbox=[58,28,90,44],allowed_bbox=[58,28,90,44])
        p['blocks'].append(keep);p['expected_blocks']=[b['id'],keep['id']];p['reading_order']=p['expected_blocks'][:]
        r=self.build(s)
        with fitz.open(r['output']) as out:self.assertIn('12 V',out[0].get_text(clip=fitz.Rect(240,0,480,180)))
    def test_links_bookmarks_and_subset(self):
        doc=fitz.open();doc.new_page(width=240,height=180);doc.new_page(width=240,height=180)
        for p in doc:p.insert_text((20,40),'Label')
        doc[0].insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(20,70,80,90),'uri':'https://example.com'})
        doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(20,100,80,120),'page':1,'to':fitz.Point(20,40)})
        doc.set_toc([[1,'First',1],[2,'Second',2]]);self.save_source(doc);s=self.extract();r=self.build(s)
        with fitz.open(r['output']) as out:
            self.assertEqual(len(out[0].get_links()),4);self.assertEqual(len(out.get_toc()),2)
            gotos=[l for l in out[0].get_links() if l['kind']==fitz.LINK_GOTO]
            self.assertEqual([l['to'].x for l in gotos],[20,260])
        with self.assertRaisesRegex(ValueError,'exclude a link destination'):ip.build(self.source,self.sp,self.root/'subset.pdf',pages='1')
        sub=ip.build(self.source,self.sp,self.root/'second.pdf',pages='2')
        report=pt.audit(self.source,sub['output'],wf.load(sub['state']))
        self.assertTrue(report['mechanical_pass'],report['findings'])
        self.assertTrue(pt.check_state(sub['state'])['valid'])
        self.assertFalse(pt.check_state(sub['state'],True)['valid'])
    def test_annotations_refused_and_authoring_input_readonly(self):
        doc=fitz.open();p=doc.new_page();p.insert_text((20,40),'Label');p.add_highlight_annot(fitz.Rect(20,25,70,42));self.save_source(doc)
        s=self.extract();ip.write_json(self.sp,s);before=self.sp.read_bytes()
        with self.assertRaisesRegex(ValueError,'Text-markup annotation touches replaced text'):ip.build(self.source,self.sp,self.root/'output.pdf')
        self.assertEqual(before,self.sp.read_bytes())
    def test_stable_ids_deterministic_build_and_shared_subset_font(self):
        self.make_basic();s=self.extract();ids=[b['id'] for b in s['pages'][0]['blocks']]
        s2=self.extract_again();self.assertEqual(ids,[b['id'] for b in s2['pages'][0]['blocks']])
        r=self.build(s2);r2=self.build(s2,'second')
        self.assertEqual(wf.digest(r['output']),wf.digest(r2['output']))
        fonts=pt.inventory(PdfReader(r['output']))['font_streams'];self.assertEqual(len(fonts),1)
        self.assertLess(fonts[0]['encoded_bytes'],self.font.stat().st_size)

    def test_word_wrap_bounded_fit_and_inline_math(self):
        self.make_basic();s=self.extract();fonts=ip.load_fonts(s,self.sp)
        b=copy.deepcopy(s['pages'][0]['blocks'][0]);b.update(allowed_bbox=[10,10,70,110],font_size=10,translation='中文MODEL-123中文,')
        ip.layout_text(b,fonts)
        self.assertTrue(any('MODEL-123' in line for line in b['layout_lines']))
        self.assertFalse(any(line.startswith(',') for line in b['layout_lines']))
        b.update(allowed_bbox=[10,10,40,30],font_size=20,font_size_min=8,translation='中文项目')
        ip.layout_text(b,fonts);self.assertGreaterEqual(b['actual_font_size'],8);self.assertLess(b['actual_font_size'],20)
        s['pages'][0]['blocks'][0].update(translation='I<sub>out2</sub> + V<sup>2</sup>',font_size=8)
        r=self.build(s);self.assertTrue(wf.check_fonts(r['state'],r['assignments'])['mechanical_pass'])
        runs=wf.load(r['assignments'])['runs']
        self.assertTrue(any(v['baseline_shift']>0 for v in runs));self.assertTrue(any(v['baseline_shift']<0 for v in runs))
        self.assertEqual(''.join(v['text'] for v in runs),'Iout2 + V2')
        s['pages'][0]['blocks'][0]['translation']='<b>中文</b>'
        with self.assertRaisesRegex(ValueError,'sub/sup'):self.build(s,'invalid-markup')
    def test_real_glyph_overlap_and_source_color(self):
        self.make_basic();s=self.extract();b=s['pages'][0]['blocks'][0]
        b.update(allowed_bbox=[145,39,220,65],expansion_reason='Deliberately invalid collision fixture')
        with self.assertRaisesRegex(ValueError,'overlaps preserved glyph'):self.build(s)
        b.update(allowed_bbox=[20,30,100,60],color=[1,1,1])
        r=self.build(s)
        with fitz.open(r['output']) as doc:
            colors=[span['color'] for block in doc[0].get_text('dict')['blocks'] if block['type']==0
                    for line in block['lines'] for span in line['spans'] if '中' in span['text']]
            self.assertEqual(colors,[16777215])
    def test_nonorthogonal_and_nested_text_clipping_refused(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180)
        p.insert_text((60,70),'Label',morph=(fitz.Point(60,70),fitz.Matrix(45)))
        self.save_source(doc);s=self.extract()
        self.assertFalse(s['pages'][0]['blocks'][0]['orthogonal'])
        with self.assertRaisesRegex(ValueError,'Non-orthogonal'):self.build(s)
        self.source.unlink();self.sp.unlink()
        inner=fitz.open();p=inner.new_page(width=240,height=180)
        p.insert_text((20,40),'Clip',render_mode=7);p.draw_rect((0,0,200,100),fill=(0,0,0))
        doc=fitz.open();p=doc.new_page(width=240,height=180);p.show_pdf_page(p.rect,inner,0)
        self.save_source(doc);inner.close();s=self.extract()
        for b in s['pages'][0]['blocks']:b.update(method='preserve',reason='Clip fixture',translation=b['source_text'])
        with self.assertRaisesRegex(ValueError,'Text clipping'):self.build(s)

    def test_zero_width_ligature_tail_and_conflicting_assignment(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180)
        p.insert_font(fontname='Fixture',fontfile=str(self.font));p.insert_text((20,40),'ft',fontname='Fixture')
        xref=int(doc.xref_get_key(p.get_fonts()[0][0],'ToUnicode')[1].split()[0])
        cmap=doc.xref_stream(xref).decode()
        cmap=cmap.replace('1 beginbfrange','2 beginbfrange').replace('<0001> <005f> <0020>','<0001> <0046> <0020>\n<0048> <005f> <0067>')
        import re
        cmap=re.sub(r'(\d+) beginbfchar',lambda m:str(int(m[1])+1)+' beginbfchar\n<0047> <00660069>',cmap)
        doc.update_stream(xref,cmap.encode());self.save_source(doc);s=self.extract()
        p=s['pages'][0];zeros=[g for g in p['glyphs'] if fitz.Rect(g['bbox']).is_empty]
        self.assertEqual([g['text'] for g in zeros],['i'])
        self.assertEqual(p['blocks'][0]['source_text'],'fit')
        r=self.build(s);self.assert_left_same(r)
        with fitz.open(r['output']) as out:self.assertNotIn('fit',out[0].get_text(clip=fitz.Rect(240,0,480,180)))
        b=p['blocks'][0];keep=copy.deepcopy(b)
        keep.update(id='tail-preserve',glyph_ids=[zeros[0]['id']],glyph_ranges=[[0,1]],method='preserve',reason='Deliberate invalid split',translation='i')
        b['glyph_ids'].remove(zeros[0]['id']);b['glyph_ranges']=[[0,len(b['glyph_ids'])]]
        p['blocks'].append(keep);p['expected_blocks'].append(keep['id']);p['reading_order'].append(keep['id'])
        with self.assertRaisesRegex(ValueError,'split a ligature'):self.build(s,'split')
    def test_raw_nullable_link_modes_and_rotation(self):
        from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NullObject
        doc=fitz.open();doc.new_page(width=240,height=180);doc.new_page(width=240,height=180)
        for p in doc:p.insert_text((20,40),'Label')
        doc[1].set_cropbox(fitz.Rect(10,10,230,170));doc[1].set_rotation(90)
        self.save_source(doc);writer=PdfWriter(clone_from=self.source)
        for mode,args in [('/XYZ',[NullObject(),FloatObject(100),NullObject()]),('/FitH',[FloatObject(80)])]:
            writer.add_annotation(0,DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Link'),
                NameObject('/Rect'):ArrayObject([FloatObject(v) for v in [20,60,90,80]]),
                NameObject('/Dest'):ArrayObject([writer.pages[0].indirect_reference,NameObject(mode),*args])}))
        writer.add_annotation(1,DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Link'),
            NameObject('/Rect'):ArrayObject([FloatObject(v) for v in [20,60,90,80]]),
            NameObject('/Dest'):ArrayObject([writer.pages[1].indirect_reference,NameObject('/FitH'),FloatObject(80)])}))
        buf=io.BytesIO();writer.write(buf);self.source.write_bytes(buf.getvalue())
        s=self.extract();r=self.build(s);self.assert_left_same(r)
        reader=PdfReader(r['output']);links=[a.get_object()['/Dest'] for a in reader.pages[0]['/Annots']]
        self.assertIsInstance(links[0][2],NullObject);self.assertEqual(float(links[0][3]),100)
        self.assertIsInstance(links[1][2],NullObject);self.assertEqual(float(links[1][3]),100)
        self.assertEqual(str(links[2][1]),'/FitH');self.assertEqual(float(links[2][2]),80)
        rotated=[a.get_object()['/Dest'] for a in reader.pages[1]['/Annots']]
        self.assertEqual(str(rotated[0][1]),'/FitV')
    def test_inflated_source_math_bbox_does_not_erase_formula(self):
        from fontTools.ttLib import TTFont
        huge=self.root/'large-ascent.ttf';make_font(huge)
        font=TTFont(huge);font['hhea'].ascent=3000;font['hhea'].descent=-1000
        font['OS/2'].sTypoAscender=3000;font['OS/2'].sTypoDescender=-1000;font.save(huge);font.close()
        doc=fitz.open();p=doc.new_page(width=240,height=180)
        p.insert_text((20,55),'Label');p.insert_font(fontname='MathFixture',fontfile=str(huge));p.insert_text((20,80),'F',fontname='MathFixture',fontsize=10)
        self.save_source(doc);s=self.extract()
        for b in s['pages'][0]['blocks']:
            if b['source_text']=='F':b.update(method='preserve',reason='Formula symbol',translation='F')
        r=self.build(s);self.assert_left_same(r)
        with fitz.open(r['output']) as out:
            page=out[0];left=page.get_pixmap(clip=fitz.Rect(15,69,35,85));right=page.get_pixmap(clip=fitz.Rect(255,69,275,85))
            self.assertEqual(left.samples,right.samples)
            self.assertIn('F',page.get_text(clip=fitz.Rect(240,0,480,180)))
    def test_external_dependency_and_generated_numbering(self):
        self.make_basic();s=self.extract();dep=self.root/'notes.json';dep.write_text('{}',encoding='utf8')
        s['layout']['inputs']=[{'path':'notes.json','sha256':wf.digest(dep)}]
        s['layout']['pagination_strategy']='physical-total'
        s['pages'][0]['pagination']={'id':'page-label','source_label':None,'text':'1/1','target_bbox':[440,5,475,20],'font_size':8}
        r=self.build(s);built=wf.load(r['state'])
        self.assertTrue(any(v['path']=='notes.json' for v in built['layout']['inputs']))
        self.assertTrue(wf.check_fonts(r['state'],r['assignments'])['mechanical_pass'])
        self.assertTrue(any(run['block']=='page-label' for run in wf.load(r['assignments'])['runs']))
        dep.write_text('{"changed":true}',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'External input fingerprint'):self.build(s,'changed')

    def test_right_link_tracks_reflowed_translation_and_explicit_anchor(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180);p.insert_text((20,40),'Model ABC123 is linked')
        p.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(49,28,90,44),'uri':'https://example.com/model'})
        self.save_source(doc);s=self.extract();b=s['pages'][0]['blocks'][0]
        b.update(translation='中文 ABC123 中文',allowed_bbox=[20,80,200,110],expansion_reason='Blank area for reflowed link fixture')
        s['pages'][0]['link_overrides']=[{'source_link':0,'target_block':b['id'],'target_text':'ABC123','occurrence':1}]
        r=self.build(s)
        with fitz.open(r['output']) as doc:
            links=doc[0].get_links();self.assertEqual(len(links),2)
            self.assertLess(links[0]['from'].y0,50);self.assertGreater(links[1]['from'].y0,75)
            self.assertEqual(links[1]['uri'],'https://example.com/model')
        mapping=wf.load(r['state'])['pages'][0]['link_mappings'][0]
        self.assertGreater(mapping['right_bboxes'][0][1],75)
        self.assert_left_same(r)

    def test_static_annotation_appearances_independent_and_visible(self):
        doc=fitz.open();p=doc.new_page(width=280,height=220)
        p.insert_text((25,40),'Label');p.insert_text((30,95),'12 + 34')
        p.add_highlight_annot(fitz.Rect(28,82,80,98))
        p.add_underline_annot(fitz.Rect(28,82,80,98))
        p.add_strikeout_annot(fitz.Rect(28,82,80,98))
        p.add_squiggly_annot(fitz.Rect(28,82,80,98))
        p.add_rect_annot(fitz.Rect(100,75,155,110))
        p.add_circle_annot(fitz.Rect(170,75,215,110))
        p.add_ink_annot([[(30,135),(50,150),(75,135)]])
        p.add_stamp_annot(fitz.Rect(100,130,210,165))
        p.set_cropbox(fitz.Rect(10,10,260,200))
        doc.xref_set_key(p.xref,'UserUnit','2')
        self.save_source(doc);s=self.extract();r=self.build(s);self.assert_left_same(r)
        reader=PdfReader(r['output']);source_reader=PdfReader(self.source)
        refs=reader.pages[0]['/Annots'];original=source_reader.pages[0]['/Annots']
        self.assertEqual(len(refs),len(original)*2)
        self.assertEqual(len({v.idnum for v in refs}),len(refs))
        for index,ref in enumerate(original):
            data=ref.get_object()['/AP']['/N'].get_data()
            self.assertEqual(refs[index*2].get_object()['/AP']['/N'].get_data(),data)
            self.assertEqual(refs[index*2+1].get_object()['/AP']['/N'].get_data(),data)
        with fitz.open(self.source) as source,fitz.open(r['output']) as output:
            p=source[0];with_annotations=p.get_pixmap(annots=True);without_annotations=p.get_pixmap(annots=False)
            self.assertNotEqual(with_annotations.samples,without_annotations.samples)
            w=p.rect.width
            left=output[0].get_pixmap(clip=fitz.Rect(0,125,w,350),annots=True)
            right=output[0].get_pixmap(clip=fitz.Rect(w,125,2*w,350),annots=True)
            a=Image.frombytes('RGB',(left.width,left.height),left.samples)
            b=Image.frombytes('RGB',(right.width,right.height),right.samples)
            self.assertLessEqual(max(v[1] for v in ImageChops.difference(a,b).getextrema()),16)
        built=wf.load(r['state']);self.assertEqual(len(built['pages'][0]['annotation_mappings']),8)
        report=pt.audit(self.source,r['output'],built)
        self.assertTrue(report['mechanical_pass'],report['findings'])
    def test_static_annotation_complex_features_explicitly_refused(self):
        doc=fitz.open();p=doc.new_page(width=240,height=180);p.insert_text((20,40),'Label')
        p.add_freetext_annot(fitz.Rect(20,70,120,100),'A note')
        self.save_source(doc);s=self.extract()
        with self.assertRaisesRegex(ValueError,'Unsupported visible annotation type'):self.build(s)
        self.source.unlink();self.sp.unlink()
        doc=fitz.open();p=doc.new_page(width=240,height=180);p.insert_text((20,40),'Label')
        p.add_rect_annot(fitz.Rect(20,70,120,100));p.set_rotation(90)
        self.save_source(doc);s=self.extract()
        with self.assertRaisesRegex(ValueError,'Rotated-page annotation'):self.build(s)
    def test_right_region_audit_detects_graphics_change_inside_allowed_box(self):
        self.make_basic();s=self.extract();s['pages'][0]['blocks'][0].update(
            allowed_bbox=[15,25,140,100],expansion_reason='Deliberately broad blank layout allowance')
        r=self.build(s);built=wf.load(r['state'])
        report=pt.audit(self.source,r['output'],built)
        self.assertTrue(report['mechanical_pass'],report['findings'])
        with fitz.open(r['output']) as output:
            output[0].draw_rect(fitz.Rect(270,80,280,90),fill=(1,0,0),color=None)
            changed=self.root/'graphics-changed.pdf';output.save(changed)
        report=pt.audit(self.source,changed,built)
        self.assertFalse(report['mechanical_pass'])
        self.assertTrue(any(v['code']=='right_graphics_changed_outside_recorded_regions' for v in report['findings']))

    def test_link_conflicts_are_batched_across_pages(self):
        doc=fitz.open()
        for i in range(2):
            p=doc.new_page(width=240,height=180);p.insert_text((20,40),'Model ABC123 is linked')
            p.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(49,28,90,44),'uri':'https://example.com/model'})
        self.save_source(doc);s=self.extract()
        for page in s['pages']:page['blocks'][0]['translation']='中文'
        with self.assertRaises(ValueError) as error:self.build(s)
        conflicts=json.loads(str(error.exception))['link_conflicts']
        self.assertEqual([c['page'] for c in conflicts],[1,2])
        self.assertTrue(all(c['source_link']==0 and c['source_bbox'] for c in conflicts))

    def test_overlay_colors_and_legacy_default_preserve_left_and_values(self):
        self.make_basic();s=self.extract();b=s['pages'][0]['blocks'][0]
        b.update(method='cover',cover_bbox=[15,25,125,60],reason='Local image label fixture',
                 cover_fill=[.2,.4,.6],cover_text_color=[1,0,0])
        r=self.build(s,'colored-overlay');self.assert_left_same(r)
        with fitz.open(r['output']) as d:
            self.assertEqual(d[0].get_pixmap().pixel(256,26),(51,102,153))
            self.assertIn('12 + 34 = 46',d[0].get_text())
            spans=[v for block in d[0].get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for v in line['spans']]
            self.assertTrue(any('中文' in v['text'] and v['color']==0xFF0000 for v in spans))
        b.pop('cover_fill');b.pop('cover_text_color');r=self.build(s,'legacy-overlay')
        with fitz.open(r['output']) as d:self.assertEqual(d[0].get_pixmap().pixel(256,26),(255,255,255))
    def test_overlay_rejects_invalid_rgb(self):
        self.make_basic();s=self.extract();b=s['pages'][0]['blocks'][0]
        b.update(method='cover',cover_bbox=[15,25,125,60],reason='Fixture')
        for value in (None,[1,0],[2,0,0],[float('nan'),0,0],['red',0,0]):
            b['cover_fill']=value
            self.assertTrue(any('Overlay color' in str(e) for e in ip.validate_state(s,self.source)))

if __name__=='__main__':unittest.main()
