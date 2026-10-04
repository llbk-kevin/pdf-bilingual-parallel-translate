"""Fixed-pane and explicitly confirmed pagination regressions; generated PDF fixtures only."""
import copy
import io
import json
import unittest
from pathlib import Path
import test_workflow as fixture
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

t, w, builder = fixture.t, fixture.w, fixture.builder


class EqualPanesAndPagination(unittest.TestCase):
    setUp = fixture.Upgrade.setUp
    tearDown = fixture.Upgrade.tearDown
    save = fixture.Upgrade.save
    built = fixture.Upgrade.built

    def labels(self, strategy, texts):
        self.state['layout']['pagination_strategy'] = strategy
        for page, text in zip(self.state['pages'], texts):
            page['pagination'] = {'id': 'p%s-number' % page['source_page'],
                'source_label': text or None if strategy == 'preserve-source' else None,
                'text': text, 'target_bbox': [400, 5, 460, 20], 'font_size': 8}
        self.save(self.state)

    def test_mixed_fractional_pages_build_with_equal_panes(self):
        sizes = [(240,300), (360.25,240.125)]
        c = canvas.Canvas(str(self.source), invariant=1)
        for width,height in sizes:
            c.setPageSize((width,height)); c.drawString(20,height-30,'Source'); c.showPage()
        c.save()
        self.state['source']['sha256'] = w.digest(self.source)
        del self.state['layout']['pane_width_pt']
        for page,(width,height) in zip(self.state['pages'],sizes):
            page['source_rect'] = [0,0,width,height]
            page['blocks'][0]['target_bbox'] = [width+20,30,2*width-20,100]
        self.save(self.state)
        r,s = self.built()
        actual = [(float(p.mediabox.width),float(p.mediabox.height)) for p in PdfReader(r['output']).pages]
        self.assertEqual(actual,[(2*a,b) for a,b in sizes])
        audit = t.audit(self.source,r['output'],s,dpi=72)
        self.assertTrue(audit['mechanical_pass'],audit['findings'])
        self.assertTrue(all(p['pane_geometry']['passed'] for p in audit['pages']))

    def test_legacy_width_cannot_widen_or_narrow(self):
        for width in (260,220,float('nan'),True):
            with self.subTest(width=width):
                self.state['layout']['pane_width_pt'] = width; self.save(self.state)
                with self.assertRaisesRegex(ValueError,'pane width must equal'):
                    self.built()
                self.assertFalse((self.root/'output.pdf').exists())
        self.state['layout']['pane_width_pt'] = 240.05; self.save(self.state)
        r,s = self.built()
        self.assertEqual(float(PdfReader(r['output']).pages[0].mediabox.width),480)

    def test_audit_rejects_unequal_size_and_displaced_source(self):
        r,s = self.built()
        for width,height in [(490,300),(470,300),(480,310),(480,290)]:
            with self.subTest(size=(width,height)):
                writer=PdfWriter(clone_from=r['output'])
                for page in writer.pages:
                    page.mediabox.upper_right=(width,height);page.cropbox.upper_right=(width,height)
                dest=self.root/('%s-%s.pdf'%(width,height));writer.write(dest)
                audit=t.audit(self.source,dest,s,dpi=72)
                self.assertFalse(audit['mechanical_pass'])
                findings=[x for x in audit['findings'] if x['code']=='unequal_pane_geometry']
                self.assertEqual(len(findings),2)
                self.assertEqual(findings[0]['expected_output_size_pt'],[480,300])
                self.assertEqual(findings[0]['actual_output_size_pt'],[width,height])
        for rect in ([.2,0,240.2,300],[0,.2,240,300.2]):
            shifted=copy.deepcopy(s);shifted['pages'][0]['source_rect']=rect
            audit=t.audit(self.source,r['output'],shifted,dpi=72)
            self.assertIn('source_region_misplaced',{x['code']for x in audit['findings']})

    def test_geometry_tolerance_is_not_relaxed(self):
        r,s=self.built()
        for delta,expected in [(.05,True),(.15,False)]:
            writer=PdfWriter(clone_from=r['output'])
            for page in writer.pages:
                page.mediabox.upper_right=(480+delta,300)
                page.cropbox.upper_right=(480+delta,300)
            out=self.root/('delta%s.pdf'%delta);writer.write(out)
            result=t.audit(self.source,out,s,dpi=72)
            self.assertEqual(result['pages'][0]['pane_geometry']['passed'],expected)

    def test_source_labels_preserve_unnumbered_cover_and_roman_page(self):
        self.labels('preserve-source',['','iv'])
        r,s=self.built()
        runs=w.load(r['assignments'])['runs']
        self.assertFalse(any(x['block']=='p1-number' for x in runs))
        self.assertEqual(''.join(x['text']for x in runs if x['block']=='p2-number'),'iv')
        self.assertIn('iv',PdfReader(r['output']).pages[1].extract_text())
        self.assertTrue(w.check_fonts(r['state'],r['assignments'])['mechanical_pass'])
        self.assertTrue(t.check_state(r['state'])['valid'])

    def test_physical_labels_have_actual_font_runs_and_survive_rebuild(self):
        self.labels('physical-total',['1/2','2/2'])
        before=self.sp.read_bytes();r,s=self.built('first');again,_=self.built('again')
        self.assertEqual(r['sha256'],again['sha256']);self.assertEqual(before,self.sp.read_bytes())
        self.assertTrue(w.check_fonts(r['state'],r['assignments'])['mechanical_pass'])
        for n,page in enumerate(PdfReader(r['output']).pages,1):
            self.assertIn('%s/2'%n,page.extract_text())
        assignments=w.load(r['assignments'])
        assignments['runs']=[x for x in assignments['runs']if x['block']!='p1-number']
        Path(r['assignments']).write_text(json.dumps(assignments),encoding='utf-8')
        self.assertIn('font_run_text_mismatch',{x['code']for x in w.check_fonts(r['state'],r['assignments'])['errors']})
        old=w.page_fingerprint(s,1)
        s['pages'][0]['pagination']['target_bbox'][0]-=1
        self.assertNotEqual(old,w.page_fingerprint(s,1))

    def test_inconsistent_labels_and_invalid_geometry_are_rejected(self):
        self.labels('physical-total',['1/2','2/2'])
        valid=copy.deepcopy(self.state)
        changes=[{'text':'1/4'},{'source_label':'i'},{'id':'p1-body'},
                 {'target_bbox':[230,0,260,20]},{'target_bbox':[400,5,460,5]},
                 {'font_size':0},{'target_bbox':[400,5,401,6]}]
        for fields in changes:
            with self.subTest(fields=fields):
                self.state=copy.deepcopy(valid);self.state['pages'][0]['pagination'].update(fields)
                self.save(self.state)
                with self.assertRaises(ValueError):self.built()
                self.assertFalse((self.root/'output.pdf').exists())
        self.state=copy.deepcopy(valid);self.state['pages'][0]['pagination']['text']='1/4';self.save(self.state)
        self.assertIn('invalid_pagination',{x['code']for x in t.check_state(self.sp)['errors']})
        self.state=copy.deepcopy(valid);self.state['layout']=None;self.save(self.state)
        report=t.check_state(self.sp)
        self.assertFalse(report['valid'])
        self.assertIn('missing_layout',{x['code']for x in report['errors']})


if __name__ == '__main__':
    unittest.main()
