import copy
import unittest
import test_inplace
ip=test_inplace.ip

class LayoutPreflight(unittest.TestCase):
    setUp=test_inplace.Inplace.setUp
    tearDown=test_inplace.Inplace.tearDown
    make_basic=test_inplace.Inplace.make_basic
    save_source=test_inplace.Inplace.save_source
    extract=test_inplace.Inplace.extract
    def test_fixed_bounded_and_exhausted(self):
        self.make_basic()
        state=self.extract()
        block=state['pages'][0]['blocks'][0]
        block.update(method='replace',translation='中文',font_size=12,allowed_bbox=[0,0,100,11])
        page={'source_page':1,'blocks':[block]}
        fonts=ip.load_fonts(state,self.sp)
        _,fixed=ip.layout_preflight([page],fonts)
        self.assertEqual(fixed['findings'][0]['code'],'height_overflow')
        block['font_size_min']=6
        cache,fit=ip.layout_preflight([page],fonts)
        self.assertFalse(fit['findings'])
        self.assertEqual(fit['counts']['adapted'],1)
        self.assertEqual(cache[(1,block['id'])][4:],ip.layout_text(block,fonts)[4:])
        block['allowed_bbox']=[0,0,100,1]
        _,failed=ip.layout_preflight([page],fonts)
        self.assertTrue(failed['findings'][0]['at_font_minimum'])
        block['allowed_bbox']=[0,0,.01,100]
        _,failed=ip.layout_preflight([page],fonts)
        self.assertEqual(failed['findings'][0]['code'],'single_glyph_too_wide')

    def test_duplicate_requires_complete_matching_appearance_and_review(self):
        point=(79,10.,20.)
        before=ip.VisibleTrace([point,point]);before.appearances=[('same',),('same',)]
        after=ip.VisibleTrace([point]);after.appearances=[('same',)]
        protected={point:[({'bbox':[9,19,11,21]},'out'),({'bbox':[9,19,11,21]},'out')]}
        index=ip.CollisionIndex()
        check=lambda profile:ip.preserved_glyph_conflicts(1,protected,before,after,index,profile=profile)
        self.assertEqual(check('practical')[0]['code'],'preserved_duplicate_reduced')
        self.assertEqual(check('strict')[0]['code'],'preserved_glyph_removed')
        before.appearances[1]=('other color',)
        self.assertEqual(check('practical')[0]['code'],'preserved_glyph_removed')
        after.clear();after.appearances=[]
        self.assertEqual(check('practical')[0]['code'],'preserved_glyph_removed')


    def test_actual_trace_and_moved_duplicate(self):
        doc=ip.fitz.open()
        page=doc.new_page()
        page.insert_text((100,100),'OUT')
        page.insert_text((100,100),'OUT')
        before=ip.right_visible_trace(page,0)
        self.assertIsNotNone(before.appearances[0])
        after=ip.VisibleTrace(before[:3]);after.appearances=before.appearances[:3]
        protected={before[0]:[({'bbox':[99,89,110,101]},'out')]*2}
        rows=ip.preserved_glyph_conflicts(1,protected,before,after,ip.CollisionIndex(),profile='practical')
        self.assertEqual(rows[0]['code'],'preserved_duplicate_reduced')
        after.append((79,150,100));after.appearances.append(before.appearances[0])
        rows=ip.preserved_glyph_conflicts(1,protected,before,after,ip.CollisionIndex(),profile='practical')
        self.assertEqual(rows[0]['code'],'preserved_glyph_removed')
        doc.close()

    def test_duplicate_disposition_required(self):
        import workflow as wf
        finding={'severity':'error','code':'preserved_duplicate_reduced','page':1,'before_count':2,'after_count':1}
        report={'mechanical_pass':False,'findings':[finding]}
        state={'layout':{'review_profile':'practical'},'qc':{}}
        self.assertFalse(wf.audit_accepted(report,state))
        state['qc']['audit_dispositions']=[{'finding_sha256':wf.canonical(finding),'decision':'retain','note':'Native label inspected and readable'}]
        self.assertTrue(wf.audit_accepted(report,state))
        state['layout']['review_profile']='strict'
        self.assertFalse(wf.audit_accepted(report,state))

    def test_zero_leading_reset_keeps_native_overprints(self):
        doc=ip.fitz.open();page=doc.new_page(width=240,height=180)
        page.insert_font(fontname='helv')
        page.insert_text((20,140),'Translate footer',fontsize=10)
        xref=doc.get_new_xref();doc.update_object(xref,'<<>>')
        raw=b'BT /helv 10 Tf 0 TL 1 0 0 1 100 100 Tm (OUT) Tj 0 0 0 rg T* (OUT) Tj ET'
        doc.update_stream(xref,raw)
        contents=page.get_contents()+[xref]
        doc.xref_set_key(page.xref,'Contents','['+' '.join(str(x)+' 0 R' for x in contents)+']')
        self.save_source(doc)
        state=self.extract()
        for block in state['pages'][0]['blocks']:
            if 'OUT' in block['source_text']:
                block.update(method='preserve',reason='Native label')
        ip.write_json(self.sp,state)
        result=ip.build(self.source,self.sp,self.root/'fixed.pdf')
        test_inplace.Inplace.assert_left_same(self,result)
        with ip.fitz.open(result['output']) as output:
            trace=ip.right_visible_trace(output[0],240)
            positions=[v for v in trace if v[0]==79]
            self.assertEqual(len(positions),2)
            self.assertAlmostEqual(positions[0][1],positions[1][1],places=3)
        self.assertEqual(ip.split_zero_leading_resets(b'BT 4 Tr (X) Tj T* (X) Tj ET')[1],0)
        self.assertEqual(ip.split_zero_leading_resets(b'BT 12 TL (X) Tj T* (X) Tj ET')[1],0)
        data=b'BT 2 TL 1 0 0 1 10 20 Tm (X) Tj q 0 TL T* (X) Tj Q T* (Y) Tj ET'
        self.assertEqual(ip.split_zero_leading_resets(data)[1],1)

    def test_text_reset_skips_transparency_and_groups(self):
        from pypdf.generic import DictionaryObject, NameObject, FloatObject, BooleanObject
        def page(gs):
            return {'/Resources':{'/ExtGState':{'/GS':gs}}}
        self.assertTrue(ip.native_reset_context_safe(page(DictionaryObject())))
        for key,value in [('/ca',FloatObject(.5)),('/CA',FloatObject(.5)),
                          ('/SMask',NameObject('/Mask')),('/BM',NameObject('/Multiply')),
                          ('/TK',BooleanObject(False)),('/AIS',BooleanObject(True))]:
            self.assertFalse(ip.native_reset_context_safe(page(DictionaryObject({NameObject(key):value}))))
        self.assertFalse(ip.native_reset_context_safe({'/Group':{'/S':'/Transparency'}}))
        self.assertFalse(ip.native_reset_context_safe({'/Resources':{'/Pattern':{'/P':{}}}}))
