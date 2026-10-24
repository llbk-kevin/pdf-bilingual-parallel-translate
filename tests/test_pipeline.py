"""Behavioral tests for the practical runner; all attestations below are synthetic fixtures."""
import copy
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pymupdf as fitz
import pipeline as pl
import inplace as ip
import pdf_tools as pt
import workflow as wf
from test_workflow import make_font

class PracticalPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'source.pdf';self.sp=self.root/'recovery'/'state.json'
        self.font=self.root/'fixture.ttf';make_font(self.font,True)
        doc=fitz.open()
        for i in range(2):
            p=doc.new_page(width=240,height=180);p.insert_text((20,40),'Translate label')
            p.insert_text((20,100),'12 + 34 = 46')
        doc.save(self.source);doc.close()
    def tearDown(self):self.tmp.cleanup()
    def args(self,**kw):return Namespace(state=str(self.sp),source=None,pages='all',profile=None,overwrite=False,output=None,previous_state=None,**kw)
    def prepared(self,pages='all',profile='practical'):
        pl.prepare(Namespace(source=str(self.source),state=str(self.sp),pages=pages,profile=profile,overwrite=False,font=[str(self.font)]))
        state=wf.load(self.sp)
        edits={'blocks':[{'page':p['source_page'],'id':b['id'],'method':'replace','translation':'中文','font_size':8,'font_size_min':None}
                         for p in state['pages'] for b in p['blocks'] if b['method']=='unresolved'],
               'inventory_reviewed_pages':[p['source_page'] for p in state['pages']]}
        ep=self.root/'edits.json';pl.save(ep,edits);pl.apply_edits(self.args(edits=str(ep)))
        return wf.load(self.sp)
    def built(self):return pl.build(self.args())
    def observations(self,result):
        sp=Path(result['state']);s=wf.load(sp)
        obs={'reviewer':'synthetic fixture, not human QA','pages':[{'page':p['source_page'],'evidence':'Synthetic pipeline attestation for regression only','viewed_at':'2020-01-01T00:00:00+00:00'} for p in s['pages']]}
        op=self.root/'observations.json';pl.save(op,obs)
        return Namespace(state=str(sp),observations=str(op))
    def test_prepare_apply_and_source_preservation(self):
        before=wf.digest(self.source);s=self.prepared('2')
        self.assertEqual(s['layout']['review_profile'],'practical');self.assertEqual(s['document']['selected_source_pages'],[2])
        self.assertTrue((self.sp.parent/'pipeline.py').exists());self.assertEqual(wf.digest(self.source),before)
        r=self.built();self.assertEqual(r['pages'],[2])
        with fitz.open(r['output']) as d:self.assertIn('12 + 34 = 46',d[0].get_text())
    def test_merged_glyph_ownership_and_invalid_edit_is_atomic(self):
        self.prepared();s=wf.load(self.sp);p=s['pages'][0];parts=p['blocks']
        ep=self.root/'bad.json';pl.save(ep,{'blocks':[{'page':1,'id':parts[0]['id'],'glyphs':[]} ]})
        before=self.sp.read_bytes()
        with self.assertRaisesRegex(ValueError,'Unsupported edit key'):pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(self.sp.read_bytes(),before)
        merge=self.root/'merge.json'
        pl.save(merge,{'blocks':[{'page':1,'id':'merged','merge_ids':[b['id'] for b in parts],
                                 'method':'replace','translation':'中文','font_size':8}]})
        pl.apply_edits(self.args(edits=str(merge)))
        merged=wf.load(self.sp)['pages'][0]['blocks'][0]
        self.assertEqual(merged['glyph_ids'],[g for b in parts for g in b['glyph_ids']])
        self.assertFalse(ip.validate_state(wf.load(self.sp),self.source))
    def test_verify_renders_once_and_build_cache_survives_review(self):
        self.prepared();r=self.built();args=Namespace(state=r['state'],previous_state=None)
        with patch.object(pt,'audit',wraps=pt.audit) as audit:
            v=pl.verify(args);self.assertEqual(audit.call_count,1)
            v2=pl.verify(args);self.assertTrue(v2['cached']);self.assertEqual(audit.call_count,1)
        self.assertEqual(v['review_needed'],[1,2]);self.assertFalse(pt.check_state(r['state'],True)['ready_for_delivery'])
        self.assertTrue(pl.review(self.observations(r))['ready'])
        self.assertTrue(self.built()['cached'])
    def test_explicit_sample_final_and_legacy_full_coverage(self):
        self.prepared('2');r=self.built();pl.verify(Namespace(state=r['state'],previous_state=None))
        self.assertTrue(pl.review(self.observations(r))['ready'])
        s=wf.load(r['state']);s['document'].pop('delivery_scope');pl.save(r['state'],s)
        self.assertIn('source_page_coverage_incomplete',[e['code'] for e in pt.check_state(r['state'],True)['errors']])
    def test_practical_disposition_never_waives_left_damage(self):
        f={'code':'right_graphics_changed_outside_recorded_regions','severity':'error','page':1,'comparison':{'changed_pixels':8}}
        report={'mechanical_pass':False,'findings':[f]};s={'layout':{'review_profile':'practical'},'qc':{}}
        self.assertFalse(wf.audit_accepted(report,s))
        s['qc']['audit_dispositions']=[{'finding_sha256':wf.canonical(f),'decision':'retain','note':'Synthetic confirmed antialias fringe'}]
        self.assertTrue(wf.audit_accepted(report,s));report['findings'].append({'code':'source_visual_changed','severity':'error'})
        self.assertFalse(wf.audit_accepted(report,s));s['layout'].pop('review_profile')
        self.assertFalse(wf.audit_accepted({'mechanical_pass':False,'findings':[f]},s))
    def test_local_change_reuses_unaffected_observation(self):
        self.prepared();r1=self.built();pl.verify(Namespace(state=r1['state'],previous_state=None));pl.review(self.observations(r1))
        s=wf.load(self.sp);b=next(b for b in s['pages'][0]['blocks'] if b['method']=='replace');b['translation']='项目';pl.save(self.sp,s)
        r2=self.built();v=pl.verify(Namespace(state=r2['state'],previous_state=r1['state']))
        self.assertEqual(v['review_needed'],[1]);qc=wf.load(r2['state'])['qc'];rec=qc['page_reviews'][0]
        self.assertEqual(rec['page'],2);self.assertEqual(rec['previous']['reviewed_at'],'2020-01-01T00:00:00+00:00')
        self.assertEqual(rec['reviewed_at'],rec['previous']['reviewed_at'])
    def test_publication_is_byte_identical_and_recoverable(self):
        self.prepared();r=self.built();pl.verify(Namespace(state=r['state'],previous_state=None));pl.review(self.observations(r))
        dest=self.root/'published.pdf';pub=pl.publish(Namespace(state=r['state'],output=str(dest),overwrite=False))
        self.assertEqual(wf.digest(dest),wf.digest(r['output']));self.assertTrue(pt.check_state(r['state'],True)['ready_for_delivery'])
        self.assertTrue(Path(pub['notes']).exists())
    def test_partial_preview_preserves_authoring_and_resource_stability(self):
        self.prepared();before=self.sp.read_bytes();a=self.args();a.pages='1';r=pl.build(a)
        self.assertEqual(r['pages'],[1]);self.assertEqual(self.sp.read_bytes(),before)
        a.output=str(self.root/'second.pdf');r2=pl.build(a)
        self.assertEqual(wf.digest(r['output']),wf.digest(r2['output']))
    def test_no_action_bookmark_and_explicit_outside_sample_link(self):
        doc=fitz.open(self.source);doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(20,20,110,45),'page':1})
        doc.set_toc([[1,'Heading without target',-1,{'kind':fitz.LINK_NONE}],[2,'Second',2]])
        replacement=self.root/'bookmarked.pdf';doc.save(replacement);doc.close();replacement.replace(self.source)
        self.prepared('1');r=self.built()
        self.assertEqual(len(wf.load(r['state'])['pages'][0]['omitted_links']),1)
        with fitz.open(r['output']) as d:self.assertTrue(any(x[1]=='Heading without target' for x in d.get_toc()))

    def test_review_uses_bound_evidence_after_runner_path_changes(self):
        self.prepared();r=self.built();pl.verify(Namespace(state=r['state'],previous_state=None))
        with patch.object(pl,'verification_paths',return_value=self.root/'never-created'):
            self.assertTrue(pl.review(self.observations(r))['ready'])

    def test_pixel_boxes_use_verified_render_scale_and_reject_wrong_source(self):
        self.prepared()
        from PIL import Image
        image=self.root/'source.png';Image.new('RGB',(480,360),'white').save(image)
        index=self.root/'index.json'
        data={'output_sha256':wf.digest(self.source),'dpi':144,'pages':[{'output_page':1,'image':'source.png','pixels':[480,360],'image_sha256':wf.digest(image)}]}
        pl.save(index,data);s=wf.load(self.sp)
        edits={'source_render_index':'index.json','blocks':[{'page':1,'id':'cover','source_bbox':[20,40,180,64],'cover_bbox':[20,40,180,64]}]}
        result=pl.pixel_edits(edits,s,self.sp,self.root/'edits.json')
        self.assertEqual(result['blocks'][0]['cover_bbox'],[10,20,90,32])
        self.assertEqual(edits['blocks'][0]['cover_bbox'],[20,40,180,64])
        edits['blocks'][0]['cover_bbox']=[0,0,481,20]
        with self.assertRaisesRegex(ValueError,'outside'):pl.pixel_edits(edits,s,self.sp,self.root/'edits.json')
        data['output_sha256']='0'*64;pl.save(index,data)
        with self.assertRaisesRegex(ValueError,'original source'):pl.pixel_edits(edits,s,self.sp,self.root/'edits.json')
    def test_cover_review_requires_specific_confirmation(self):
        self.prepared();s=wf.load(self.sp);b=s['pages'][0]['blocks'][0]
        b.update(method='cover',cover_bbox=b['source_bbox'],reason='Synthetic local cover')
        pl.save(self.sp,s);r=self.built();pl.verify(Namespace(state=r['state'],previous_state=None))
        obs=self.observations(r)
        with self.assertRaisesRegex(ValueError,'covers_checked'):pl.review(obs)
        data=wf.load(obs.observations);data['pages'][0]['covers_checked']=True;pl.save(obs.observations,data)
        self.assertTrue(pl.review(obs)['ready'])

    def test_formula_preflight_is_a_nonblocking_local_hint(self):
        doc=fitz.open(self.source)
        doc[0].insert_text((20,130),'x = y = z')
        doc[0].insert_text((20,150),'a = b = c')
        replacement=self.root/'math.pdf';doc.save(replacement);doc.close();replacement.replace(self.source)
        self.prepared()
        risks=wf.load(self.sp.parent/'preflight.json')['risks']
        hint=next(r for r in risks if r['code']=='formula_dense_region_hint')
        self.assertEqual(hint['page'],1);self.assertTrue(hint['heuristic'])
        self.assertTrue(hint['blocks'])
    def test_unknown_edit_envelope_is_rejected_without_state_change(self):
        self.prepared();before=self.sp.read_bytes();ep=self.root/'envelope.json'
        pl.save(ep,{'edits':[{'page':1,'id':'wrong'}]})
        with self.assertRaisesRegex(ValueError,'top-level keys'):pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(self.sp.read_bytes(),before)
    def test_shared_font_change_invalidates_all_page_reviews(self):
        self.prepared();r=self.built()
        s=wf.load(r['state']);before=[wf.page_fingerprint(s,n) for n in (1,2)]
        s['layout']['fonts'][0]['sha256']='0'*64
        self.assertTrue(all(wf.page_fingerprint(s,n)!=before[n-1] for n in (1,2)))
    def test_no_action_parent_retains_nested_destination(self):
        doc=fitz.open(self.source)
        doc.set_toc([[1,'Heading without target',-1,{'kind':fitz.LINK_NONE}],[2,'Second',2]])
        replacement=self.root/'tree.pdf';doc.save(replacement);doc.close();replacement.replace(self.source)
        self.prepared();r=self.built()
        with fitz.open(r['output']) as d:
            toc=d.get_toc()
            self.assertEqual([(x[0],x[1]) for x in toc],[(1,'Heading without target'),(2,'Second')])
            self.assertEqual(toc[1][2],2)

    def test_link_patch_keeps_other_links_and_reports_page(self):
        self.prepared();ep=self.root/'links.json'
        pl.save(ep,{'link_overrides':{'1':[{'source_link':0,'right_bbox':[20,20,50,40]}]}})
        pl.apply_edits(self.args(edits=str(ep)))
        pl.save(ep,{'link_overrides_patch':{'1':[{'source_link':1,'right_bbox':[60,20,90,40]}]}})
        result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(result['changed_pages'],[1])
        self.assertEqual([v['source_link'] for v in wf.load(self.sp)['pages'][0]['link_overrides']],[0,1])
        before=self.sp.read_bytes()
        pl.save(ep,{'link_overrides':{'1':[]},'link_overrides_patch':{'1':[]}})
        with self.assertRaisesRegex(ValueError,'either'):pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(before,self.sp.read_bytes())

    def test_reuse_carries_exact_retained_finding_and_notes(self):
        self.prepared();r1=self.built();pl.verify(Namespace(state=r1['state'],previous_state=None))
        finding={'code':'right_graphics_changed_outside_recorded_regions','severity':'error','page':2,'comparison':{'changed_pixels':3}}
        old=wf.load(r1['state']);audit_path=wf.resolve(Path(r1['state']).parent,old['qc']['audit_path'])
        audit=wf.load(audit_path);audit['findings'].append(finding);audit['mechanical_pass']=False;pl.save(audit_path,audit)
        obs=self.observations(r1);data=wf.load(obs.observations)
        data['pages'][1].update(retain_right_difference='Synthetic harmless fringe',retained=['Synthetic note'])
        pl.save(obs.observations,data);self.assertTrue(pl.review(obs)['ready'])
        s=wf.load(self.sp);s['pages'][0]['blocks'][0]['translation']='项目';pl.save(self.sp,s);r2=self.built()
        original_audit=pt.audit
        def with_finding(*a,**kw):
            report=original_audit(*a,**kw);report['findings'].append(finding);report['mechanical_pass']=False;return report
        with patch.object(pt,'audit',side_effect=with_finding):
            result=pl.verify(Namespace(state=r2['state'],previous_state=r1['state']))
        self.assertEqual(result['review_needed'],[1])
        current=wf.load(r2['state']);self.assertEqual(current['qc']['audit_dispositions'],wf.load(r1['state'])['qc']['audit_dispositions'])
        self.assertEqual(current['qc']['retained_notes'],[{'page':2,'note':'Synthetic note'}])
        newobs=self.observations(r2);data=wf.load(newobs.observations);data['pages']=data['pages'][:1];pl.save(newobs.observations,data)
        self.assertTrue(pl.review(newobs)['ready'])


    def test_local_preview_uses_current_runner_and_selected_pages(self):
        self.prepared();state=wf.load(self.sp);ep=self.root/'local.json'
        pl.save(ep,{'blocks':[{'page':2,'id':state['pages'][1]['blocks'][0]['id'],'translation':'项目'}]})
        result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(result['preview_argv'],[sys.executable,str(Path(pl.__file__).resolve()),'build','--state',str(self.sp.resolve()),'--pages','2'])
        self.assertIn('--previous-state',result['next'])

    def test_failed_cli_reports_diagnostic_on_both_streams_without_building(self):
        import contextlib
        import io
        self.prepared();before=self.sp.read_bytes();stdout=io.StringIO();stderr=io.StringIO()
        with patch.object(ip,'build') as builder, contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code=pl.main(['build','--state',str(self.sp),'--source',str(self.root/'missing.pdf'),'--pages','1'])
        self.assertEqual(code,2);builder.assert_not_called()
        self.assertEqual(stdout.getvalue(),stderr.getvalue())
        summary=json.loads(stderr.getvalue());detail=wf.load(summary['report'])['detail']
        self.assertEqual(detail['code'],'source_override_mismatch')
        self.assertEqual(Path(detail['expected']),self.source.resolve());self.assertFalse(detail['supplied_exists'])
        self.assertIn('Omit --source',detail['action']);self.assertEqual(before,self.sp.read_bytes())

if __name__=='__main__':unittest.main()
