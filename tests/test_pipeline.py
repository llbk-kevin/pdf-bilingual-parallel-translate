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
    def test_apply_keeps_translation_and_reports_local_layout(self):
        state=self.prepared()
        block=next(b for b in state['pages'][0]['blocks'] if b['method']=='replace')
        ep=self.root/'overflow.json'
        pl.save(ep,{'blocks':[{'page':1,'id':block['id'],'translation':'中文'*100,'font_size':8,'font_size_min':8}]})
        result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(result['changed_pages'],[1])
        self.assertIsNone(result['preview_argv'])
        self.assertEqual(result['preview_skipped_pages'],[1])
        self.assertIn('height_overflow',result['preview_blocked_by_page'][0]['reasons'])
        self.assertGreater(result['layout_check']['counts']['needs_attention'],0)
        saved=wf.load(self.sp)
        self.assertEqual(next(b for b in saved['pages'][0]['blocks'] if b['id']==block['id'])['translation'],'中文'*100)
        report=wf.load(result['layout_check']['details'])
        self.assertEqual(report['groups']['height_overflow']['pages'],[1])
        with patch.object(ip.fitz.Page,'apply_redactions',side_effect=AssertionError('redaction must not start')):
            with self.assertRaisesRegex(ValueError,'height_overflow'):
                self.built()

    def test_duplicate_finding_requires_specific_review_disposition(self):
        self.prepared()
        built=self.built()
        sp=Path(built['state']);state=wf.load(sp)
        state['pages'][0]['build_findings']=[{'code':'preserved_duplicate_reduced','page':1,
            'block':'synthetic','character':'X','origin':[20,40],'before_count':2,'after_count':1}]
        pl.save(sp,state)
        verified=pl.verify(Namespace(state=str(sp),previous_state=None))
        reviewed=self.observations(verified)
        obs=wf.load(reviewed.observations)
        obs['pages'][0]['retain_right_difference']='Viewed synthetic native label and retained its overprint reduction'
        pl.save(reviewed.observations,obs)
        result=pl.review(reviewed)
        final=wf.load(sp)
        self.assertTrue(final['qc']['audit_dispositions'])
        audit=wf.load(wf.resolve(sp.parent,final['qc']['audit_path']))
        self.assertTrue(wf.audit_accepted(audit,final))

    def test_inspect_is_bounded_read_only_and_uses_glyph_ownership(self):
        state = self.prepared()
        original = self.sp.read_bytes()
        args = Namespace(state=str(self.sp),pages='all',block=None,detail='summary',limit=20,offset=0)
        result = pl.inspect_state(args)
        self.assertEqual(result['page_count'],2)
        args.detail='blocks'
        with self.assertRaisesRegex(ValueError,'explicit --pages'):
            pl.inspect_state(args)
        args.pages='1';args.limit=1
        result = pl.inspect_state(args)
        self.assertEqual(len(result['items']),1)
        self.assertIn('next_offset',result)
        args.detail='glyphs'
        with self.assertRaisesRegex(ValueError,'--block'):
            pl.inspect_state(args)
        args.block=[state['pages'][0]['blocks'][0]['id']]
        glyphs = pl.inspect_state(args)
        self.assertEqual(glyphs['items'][0]['block'],args.block[0])
        self.assertEqual(self.sp.read_bytes(),original)
        import contextlib,io
        before = {file.relative_to(self.root) for file in self.root.rglob('*') if file.is_file()}
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pl.main(['inspect','--state',str(self.sp),'--detail','glyphs']),2)
        self.assertEqual(before,{file.relative_to(self.root) for file in self.root.rglob('*') if file.is_file()})
    def observations(self,result):
        sp=Path(result['state']);s=wf.load(sp)
        obs={'reviewer':'synthetic fixture, not human QA','pages':[{'page':p['source_page'],'evidence':'Synthetic pipeline attestation for regression only','viewed_at':'2020-01-01T00:00:00+00:00'} for p in s['pages']]}
        index = wf.resolve(sp.parent, s['qc']['audit_path']).parent/'renders'/'index.json'
        obs.update(output_sha256=s['output']['sha256'], render_index_sha256=wf.digest(index))
        op=self.root/'observations.json';pl.save(op,obs)
        return Namespace(state=str(sp),observations=str(op))


    def test_preview_checks_links_to_final_pages_before_serialization(self):
        doc=fitz.open(self.source)
        doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(20,28,50,43),'page':1})
        source=self.root/'linked.pdf';doc.save(source);doc.close();self.source=source
        self.prepared()
        args=self.args();args.pages='1'
        with patch.object(fitz.Document,'save') as writer:
            with self.assertRaises(ValueError) as error:
                pl.build(args)
        writer.assert_not_called()
        self.assertEqual(json.loads(str(error.exception))['link_conflicts'][0]['page'],1)
        package=self.root/'package'
        pl.package(Namespace(state=self.sp,pages='1',out=package,owner='fixture'))
        args.state=package/'state.json';args.pages='all'
        with self.assertRaisesRegex(ValueError,'link_conflicts'):
            pl.build(args)

    def test_actual_sample_may_omit_outside_link(self):
        doc=fitz.open(self.source)
        doc[0].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(20,28,50,43),'page':1})
        source=self.root/'linked.pdf';doc.save(source);doc.close();self.source=source
        self.prepared(pages='1')
        result=self.built()
        self.assertEqual(wf.load(result['state'])['pages'][0]['omitted_links'][0]['target_page'],2)

    def test_preview_skips_unresolved_changed_page(self):
        self.prepared()
        state=wf.load(self.sp)
        edits=self.root/'incomplete.json'
        pl.save(edits,{'blocks':[{'page':1,'id':state['pages'][0]['blocks'][0]['id'],'method':'unresolved'},
                                {'page':2,'id':state['pages'][1]['blocks'][0]['id'],'translation':'文中'}]})
        result=pl.apply_edits(self.args(edits=str(edits)))
        self.assertEqual(result['changed_pages'],[1,2])
        self.assertEqual(result['preview_skipped_pages'],[1])
        self.assertEqual(result['preview_argv'][-1],'2')

    def test_handoff_template_is_bound_and_unobserved(self):
        self.prepared();result=self.built()
        verified=pl.verify(Namespace(state=result['state'],previous_state=None))
        template=wf.load(verified['observations_template'])
        self.assertEqual(template['pages'],[])
        self.assertEqual(template['reviewer'],'')
        self.assertEqual(template['output_sha256'],verified['output_sha256'])
        self.assertEqual(wf.load(verified['review_handoff'])['review_needed'],[1,2])
        args=self.observations(result);obs=wf.load(args.observations)
        obs.pop('output_sha256');pl.save(args.observations,obs)
        with self.assertRaisesRegex(ValueError,'observation_fields_missing'):
            pl.review(args)

    def test_runtime_probe_works_in_isolated_process_and_checks_versions(self):
        self.prepared()
        state=wf.load(self.sp)
        self.assertIn('-I',pl.probe_runtime(state,self.sp))
        config=wf.load(self.sp.parent/'runtime.json');config['packages']['Pillow']='0.0'
        pl.save(self.sp.parent/'runtime.json',config)
        with self.assertRaisesRegex(ValueError, 'frozen_runtime_probe_failed'):
            pl.probe_runtime(state,self.sp)

    def test_each_cli_failure_keeps_its_diagnostic(self):
        import contextlib,io
        self.prepared()
        for name in ('bad-a','bad-b'):
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(pl.main(['build','--state',str(self.sp),'--pages',name]),2)
        files=list((self.sp.parent/'diagnostics').glob('*.json'))
        self.assertEqual(len(files),2)
        self.assertTrue(all(wf.load(f)['command']=='build' for f in files))
        self.assertIn(Path(wf.load(self.sp.parent/'last-error.json')['diagnostic']).resolve(),[file.resolve() for file in files])

    def test_package_handoff_atomic_replay_and_reassignment(self):
        self.prepared()
        one = self.root/'work'/'package-a'
        two = self.root/'work'/'package-b'
        for directory, page, owner in ((one, '1', 'initial-worker'), (two, '2', 'replacement-worker')):
            pl.package(Namespace(state=self.sp, pages=page, out=directory, owner=owner))
        self.assertEqual(pl.load(one/'context.json')['read_only'][0]['page'], 2)
        self.assertEqual(pl.load(two/'package.json')['owner'], 'replacement-worker')
        original = pl.load(self.sp)
        files = [d/'edits.json' for d in (one, two)]
        manifests = [d/'package.json' for d in (one, two)]
        for page, path in enumerate(files, 1):
            block = original['pages'][page-1]['blocks'][0]
            pl.save(path, {'blocks': [{'page':page, 'id':block['id'], 'translation':'文中'}]})
        local = Namespace(state=one/'state.json', edits=str(files[0]))
        pl.apply_edits(local)
        preview_args = self.args()
        preview_args.state = one/'state.json'
        preview = pl.build(preview_args)
        self.assertTrue(pl.load(preview['state'])['output']['preview'])
        pl.verify(Namespace(state=preview['state'], previous_state=None))
        pl.review(self.observations(preview))
        with self.assertRaisesRegex(ValueError, 'preview_cannot_be_published'):
            pl.publish(Namespace(state=preview['state'], output=str(self.root/'preview.pdf'), overwrite=False))

        batch = self.args(edits=files, package=manifests)
        before = self.sp.read_bytes()
        wrong = pl.load(files[1]); wrong['blocks'][0]['page'] = 1; pl.save(files[1], wrong)
        with self.assertRaisesRegex(ValueError, 'outside its assignment'):
            pl.apply_edits(batch)
        self.assertEqual(self.sp.read_bytes(), before)
        wrong['blocks'][0]['page'] = 2; pl.save(files[1], wrong)
        self.assertEqual(pl.apply_edits(batch)['changed_pages'], [1, 2])
        saved = self.sp.read_bytes()
        self.assertEqual(pl.apply_edits(batch)['state_written_bytes'], 0)
        self.assertEqual(self.sp.read_bytes(), saved)
        wrong['blocks'][0]['translation'] = '中文'; pl.save(files[1], wrong)
        with self.assertRaisesRegex(ValueError, 'package_baseline_changed'):
            pl.apply_edits(batch)
        self.assertEqual(self.sp.read_bytes(), saved)
        progress = pl.status(Namespace(state=self.sp, pages='all', packages=[one,two], candidate=[preview['state']]))
        self.assertEqual(progress['packages'][0]['built_pages'], '1')
        self.assertEqual(progress['packages'][0]['reviewed_pages'], '1')
        self.assertEqual(progress['packages'][1]['applied_edits'], '2')
        self.assertEqual(progress['packages'][1]['published_pages'], '')

    def test_preview_observations_and_page_render_reuse(self):
        self.prepared()
        previews = []
        for n in (1, 2):
            args = self.args(); args.pages = str(n)
            candidate = pl.build(args)
            previews.append(candidate['state'])
            pl.verify(Namespace(state=candidate['state'], previous_state=None))
            self.assertTrue(pl.review(self.observations(candidate))['observations_saved'])
        full = self.built()
        first = pl.verify(Namespace(state=full['state'], previous_state=previews))
        self.assertEqual(first['review_needed'], [])
        self.assertEqual(first['reused_pages'], [1,2])
        self.assertEqual(first['source_rendered_pages'], 0)
        original = pl.load(self.sp)
        edit = self.root/'reverse-text.json'
        pl.save(edit, {'blocks':[{'page':1, 'id':original['pages'][0]['blocks'][0]['id'], 'translation':'文中'}]})
        pl.apply_edits(self.args(edits=str(edit)))
        revised = self.built()
        second = pl.verify(Namespace(state=revised['state'], previous_state=[full['state']]))
        self.assertEqual(second['review_needed'], [1])
        self.assertEqual(second['reused_pages'], [2])
        self.assertEqual(second['source_rendered_pages'], 0)
        self.assertEqual(second['rendered_pages'], 1)
        self.assertEqual(second['mechanical_reused_pages'], 1)
        original = pl.load(full['state'])['qc']['page_reviews'][1]
        carried = pl.load(revised['state'])['qc']['page_reviews'][0]
        for field in ('reviewer', 'reviewed_at', 'evidence'):
            self.assertEqual(original[field], carried[field])

    def test_inventory_reuse_requires_matching_review_and_preserves_chain(self):
        self.prepared()
        author = pl.load(self.sp)
        for page in author['pages']:
            page.update(inventory_reviewed=False, visual_text_review='pending')
        pl.save(self.sp, author)
        old = self.built()
        pl.verify(Namespace(state=old['state'], previous_state=None))
        obs = self.observations(old)
        data = pl.load(obs.observations)
        data['pages'][1]['inventory_reviewed'] = True
        pl.save(obs.observations, data)
        pl.review(obs)
        original = pl.load(old['state'])['qc']['page_reviews'][1]

        # A changed page cannot inherit even an acknowledged old page.
        author = pl.load(self.sp)
        author['pages'][1]['blocks'][0]['translation'] = '项目'
        pl.save(self.sp, author)
        changed = self.built()
        checked = pl.verify(Namespace(state=changed['state'], previous_state=[old['state']]))
        self.assertEqual(checked['reused_pages'], [1])
        self.assertEqual(checked['inventory_review_needed'], '1-2')

        # Restore page 2, alter page 1 and reuse its actual old observation.
        author['pages'][1]['blocks'][0]['translation'] = '中文'
        author['pages'][0]['blocks'][0]['translation'] = '项目'
        pl.save(self.sp, author)
        middle = self.built()
        checked = pl.verify(Namespace(state=middle['state'], previous_state=[old['state']]))
        self.assertEqual(checked['reused_pages'], [2])
        self.assertEqual(checked['inventory_review_needed'], '1')
        page = pl.load(middle['state'])['pages'][1]
        self.assertTrue(page['inventory_reviewed'])
        self.assertEqual(page['visual_text_review'], 'reviewed')

        author['pages'][0]['blocks'][0]['translation'] = '文中'
        pl.save(self.sp, author)
        final = self.built()
        checked = pl.verify(Namespace(state=final['state'], previous_state=[middle['state']]))
        self.assertEqual(checked['reused_pages'], [2])
        self.assertEqual(checked['inventory_review_needed'], '1')
        record = pl.load(final['state'])['qc']['page_reviews'][0]
        for field in ('reviewer', 'reviewed_at', 'evidence'):
            self.assertEqual(record[field], original[field])
            self.assertEqual(record['previous'][field], original[field])

    def test_inventory_reuse_obeys_first_source_and_current_review_priority(self):
        self.prepared()
        author = pl.load(self.sp)
        for page in author['pages']:
            page.update(inventory_reviewed=False, visual_text_review='pending')
        pl.save(self.sp, author)
        candidate = self.built()
        pl.verify(Namespace(state=candidate['state'], previous_state=None))
        pl.review(self.observations(candidate))
        original = pl.load(candidate['state'])
        first = copy.deepcopy(original)
        first['pages'][0].update(inventory_reviewed=True, visual_text_review='reviewed')
        second = copy.deepcopy(original)
        second['pages'][1].update(inventory_reviewed=True, visual_text_review='reviewed')
        first_path = Path(candidate['state']).with_name('first.state.json')
        second_path = first_path.with_name('second.state.json')
        pl.save(first_path, first); pl.save(second_path, second)
        target_path = first_path.with_name('target.state.json')
        target = copy.deepcopy(original); target['qc'] = {}
        pl.save(target_path, target)
        result = pl.verify(Namespace(state=target_path, previous_state=[first_path, second_path]))
        self.assertEqual(result['reused_pages'], [1, 2])
        self.assertEqual(result['inventory_review_needed'], '2')

        # Disjoint sources each supply their own acknowledgement.
        first['qc']['page_reviews'] = first['qc']['page_reviews'][:1]
        pl.save(first_path, first)
        pl.save(target_path, target)
        result = pl.verify(Namespace(state=target_path, previous_state=[first_path, second_path]))
        self.assertEqual(result['reused_pages'], [1, 2])
        self.assertEqual(result['inventory_review_needed'], '')
        saved = pl.load(target_path)
        self.assertEqual(saved['qc']['content_sha256'], pt.content_hash(saved))
        final = pt.check_state(target_path, final=True)
        self.assertTrue(final['ready_for_delivery'], final['errors'])
        before = target_path.read_bytes()
        repeated = pl.verify(Namespace(state=target_path, previous_state=[first_path, second_path]))
        self.assertEqual(repeated['inventory_review_needed'], '')
        self.assertEqual(repeated['state_written_bytes'], 0)
        self.assertEqual(target_path.read_bytes(), before)
        self.assertEqual(pl.load(target_path)['qc']['content_sha256'], pt.content_hash(pl.load(target_path)))
        self.assertTrue(pt.check_state(target_path, final=True)['ready_for_delivery'])

        # An already validated current review wins over both prior states.
        first['qc']['page_reviews'] = original['qc']['page_reviews']
        pl.save(first_path, first)
        current = copy.deepcopy(original)
        current['qc']['page_reviews'] = current['qc']['page_reviews'][:1]
        pl.save(target_path, current)
        result = pl.verify(Namespace(state=target_path, previous_state=[first_path, second_path]))
        self.assertEqual(result['inventory_review_needed'], '1-2')
        records = pl.load(target_path)['qc']['page_reviews']
        self.assertEqual([r['mode'] for r in records], ['viewed', 'reused'])

    def test_inventory_acknowledgement_reuses_mechanical_evidence_and_status(self):
        self.prepared()
        state = pl.load(self.sp)
        state['pages'][0].update(inventory_reviewed=False, visual_text_review='pending')
        pl.save(self.sp, state)
        candidate = self.built()
        args = Namespace(state=candidate['state'], previous_state=None)
        with patch.object(pt, 'audit', wraps=pt.audit) as audit:
            verified = pl.verify(args)
            self.assertEqual(verified['inventory_review_needed'], '1')
            self.assertEqual(verified['rendered_pages'], 2)
            before = {p: p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()}
            with patch.object(sys, 'stdout', new_callable=__import__('io').StringIO) as stdout:
                self.assertEqual(pl.main(['status', '--state', args.state, '--pages', '1-2']), 0)
                self.assertEqual(json.loads(stdout.getvalue())['inventory_review_needed'], '1')
            self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.root.rglob('*') if p.is_file()})
            observations = self.observations(candidate)
            observation = pl.load(observations.observations)
            observation['pages'] = [dict(observation['pages'][0], inventory_reviewed=True)]
            pl.save(observations.observations, observation)
            self.assertFalse(pl.review(observations)['ready'])
            for _ in range(2):
                again = pl.verify(args)
                self.assertEqual(again['render_index_sha256'], verified['render_index_sha256'])
                self.assertEqual(again['inventory_review_needed'], '')
                self.assertEqual(again['rendered_pages'], 0)
                self.assertEqual(again['state_written_bytes'], 0)
                self.assertEqual(again['review_needed'], [2])
            self.assertEqual(audit.call_count, 1)
        output = Path(candidate['output'])
        output.write_bytes(output.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Candidate fingerprint changed'):
            pl.verify(args)

    def test_batches_are_ordered_atomic_and_retry_after_interruption(self):
        self.prepared()
        state = pl.load(self.sp)
        first = self.root / 'chapter-1.json'
        second = self.root / 'chapter-2.json'
        p = state['pages'][0]
        pl.save(first, {'blocks': [{'page': 1, 'id': 'joined',
                                   'merge_ids': [b['id'] for b in p['blocks']],
                                   'method': 'replace', 'translation': '中文'}]})
        pl.save(second, {'blocks': [{'page': 1, 'id': 'missing', 'method': 'replace'}]})
        before = self.sp.read_bytes()
        with self.assertRaisesRegex(ValueError, 'chapter-2.json'):
            pl.apply_edits(self.args(edits=[str(first), str(second)]))
        self.assertEqual(self.sp.read_bytes(), before)
        pl.save(second, {'blocks': [{'page': 1, 'id': 'joined', 'translation': '中文中文'}]})
        with patch.object(Path, 'replace', side_effect=OSError('simulated interruption')):
            with self.assertRaises(OSError):
                pl.apply_edits(self.args(edits=[str(first), str(second)]))
        self.assertEqual(self.sp.read_bytes(), before)
        result = pl.apply_edits(self.args(edits=[str(first), str(second)]))
        self.assertEqual(result['changed_pages'], [1])
        self.assertEqual(pl.load(self.sp)['pages'][0]['blocks'][0]['translation'], '中文中文')
        self.assertEqual(len(self.sp.read_text(encoding='utf-8').splitlines()), 1)

    def test_verify_retries_after_interrupted_audit_and_detects_modified_evidence(self):
        self.prepared()
        candidate = self.built()
        args = Namespace(state=candidate['state'], previous_state=None)
        with patch.object(pt, 'audit', side_effect=OSError('simulated interrupted audit')):
            with self.assertRaises(OSError):
                pl.verify(args)
        result = pl.verify(args)
        self.assertEqual(result['rendered_pages'], 2)
        image = Path(result['render_index']).parent / 'page-0001.png'
        image.write_bytes(b'corrupted render')
        with self.assertRaisesRegex(ValueError, 'Immutable verification evidence changed'):
            pl.verify(args)

    def test_full_scope_link_is_omitted_only_in_preview(self):
        with fitz.open(self.source) as doc:
            doc[0].insert_link({'kind': fitz.LINK_GOTO, 'from': fitz.Rect(160,50,210,80), 'page': 1})
            doc.saveIncr()
        self.prepared()
        args = self.args()
        args.pages = '1'
        preview = pl.build(args)
        s = pl.load(preview['state'])
        self.assertEqual(s['pages'][0]['omitted_links'][0]['target_page'], 2)
        pl.verify(Namespace(state=preview['state'], previous_state=None))
        pl.review(self.observations(preview))
        with self.assertRaisesRegex(ValueError, 'preview_cannot_be_published'):
            pl.publish(Namespace(state=preview['state'], output=str(self.root/'preview-out.pdf'), overwrite=False))
        final = self.built()
        with fitz.open(final['output']) as doc:
            self.assertEqual([link['page'] for link in doc[0].get_links()], [1, 1])

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
    def test_explicit_sample_final_and_incomplete_full_coverage(self):
        self.prepared('2');r=self.built();pl.verify(Namespace(state=r['state'],previous_state=None))
        self.assertTrue(pl.review(self.observations(r))['ready'])
        pub = pl.publish(Namespace(state=r['state'], output=str(self.root/'sample.pdf'), overwrite=False))
        self.assertEqual(pub['scope'], 'sample')
        self.assertTrue(pt.check_state(r['state'], True)['ready_for_delivery'])
        s=wf.load(r['state']);s['document']['delivery_scope']='full';pl.save(r['state'],s)
        self.assertIn('source_page_coverage_incomplete',[e['code'] for e in pt.check_state(r['state'],True)['errors']])
    def test_unsupported_states_fail_before_authoring_or_build(self):
        valid = self.prepared(profile=None)
        self.assertEqual(valid['layout']['review_profile'], 'practical')
        edits = self.root/'edits.json'
        pl.save(edits, {'inventory_reviewed_pages': [1, 2]})
        for version, profile, code in [(1, 'practical', 'unsupported_state_schema'),
                                       (2, 'strict', 'unsupported_state_schema'),
                                       (3, None, 'invalid_review_profile'),
                                       (3, 'other', 'invalid_review_profile')]:
            with self.subTest(version=version, profile=profile):
                state = copy.deepcopy(valid)
                state['schema_version'] = version
                if profile is None:
                    del state['layout']['review_profile']
                else:
                    state['layout']['review_profile'] = profile
                pl.save(self.sp, state)
                before = self.sp.read_bytes()
                report = pt.check_state(self.sp, True)
                self.assertFalse(report['ready_for_delivery'])
                self.assertEqual(report['errors'][0]['code'], code)
                with self.assertRaisesRegex(ValueError, code):
                    pl.apply_edits(self.args(edits=str(edits)))
                with self.assertRaisesRegex(ValueError, code):
                    self.built()
                with self.assertRaisesRegex(ValueError, code):
                    ip.build(self.source, self.sp, self.root/'rejected.pdf')
                with self.assertRaisesRegex(ValueError, code):
                    wf.check_fonts(self.sp, self.root/'unused.json')
                self.assertEqual(self.sp.read_bytes(), before)
                self.assertFalse((self.root/'rejected.pdf').exists())

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
    def test_strict_publication_is_byte_identical_and_recoverable(self):
        self.prepared(profile='strict');r=self.built();pl.verify(Namespace(state=r['state'],previous_state=None));pl.review(self.observations(r))
        dest=self.root/'published.pdf';pub=pl.publish(Namespace(state=r['state'],output=str(dest),overwrite=False))
        self.assertEqual(wf.digest(dest),wf.digest(r['output']));self.assertTrue(pt.check_state(r['state'],True)['ready_for_delivery'])
        self.assertEqual(Path(pub['notes']),(self.root/'交付说明.md').resolve())
        note = Path(pub['notes']).read_text(encoding='utf-8')
        self.assertIn(wf.digest(self.source), note)
        self.assertIn(wf.digest(dest), note)
        self.assertEqual(pt.check_state(r['state'], True)['review_profile'], 'strict')
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
        self.prepared();r1=self.built()
        finding={'code':'right_graphics_changed_outside_recorded_regions','severity':'error','page':2,'comparison':{'changed_pixels':3}}
        original_audit=pt.audit
        def with_finding(*a,**kw):
            report=original_audit(*a,**kw);report['findings'].append(finding);report['mechanical_pass']=False;return report
        with patch.object(pt,'audit',side_effect=with_finding):
            pl.verify(Namespace(state=r1['state'],previous_state=None))
        obs=self.observations(r1);data=wf.load(obs.observations)
        data['pages'][1].update(retain_right_difference='Synthetic harmless fringe',retained=['Synthetic note'])
        pl.save(obs.observations,data);self.assertTrue(pl.review(obs)['ready'])
        s=wf.load(self.sp);s['pages'][0]['blocks'][0]['translation']='项目';pl.save(self.sp,s);r2=self.built()
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
        self.assertEqual(result['preview_argv'],pl.runtime_prefix(wf.load(self.sp),self.sp)+[str(Path(pl.__file__).resolve()),'build','--state',str(self.sp.resolve()),'--pages','2'])
        self.assertIn('--previous-state',result['next'])

    def test_missing_frozen_fields_are_rejected(self):
        self.prepared()
        state=wf.load(self.sp);state['layout'].pop('runtime_launcher')
        pl.save(self.sp,state)
        with self.assertRaisesRegex(ValueError,'incomplete_current_task_state'):
            self.built()

    def test_publication_recovery_uses_versioned_runner_and_accepted_state(self):
        import subprocess
        self.sp=self.root/'recovery-v2'/'state.json'
        self.prepared()
        with patch.object(ip,'__file__',str(self.sp.parent/'inplace.py')):
            result=self.built()
        pl.verify(Namespace(state=result['state'],previous_state=None));pl.review(self.observations(result))
        destination=self.root/'published.pdf'
        pub=pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False))
        argv=pub['recovery_argv'];before=wf.digest(destination)
        self.assertEqual(Path(argv[5]),(self.sp.parent/'pipeline.py').resolve())
        self.assertEqual(Path(argv[8]),Path(result['state']))
        self.assertEqual(Path(argv[10]),(self.root/'work'/'rebuild'/'accepted.rebuilt.pdf').resolve())
        completed=subprocess.run(argv,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        restored=json.loads(completed.stdout)
        with fitz.open(restored['output']) as doc:
            self.assertEqual(len(doc),2);self.assertIn('中文',doc[0].get_text())
        self.assertEqual(wf.digest(destination),before)
        self.assertEqual({p.name for p in (self.root/'work'/'rebuild').iterdir()},
                         {'accepted.rebuilt.pdf','accepted.rebuilt.state.json','accepted.rebuilt.font-runs.json','accepted.rebuilt.build.json','accepted.rebuilt.job.json'})


    def test_partial_review_acknowledges_save_without_allowing_publication(self):
        import contextlib
        import io
        self.prepared();result=self.built();pl.verify(Namespace(state=result['state'],previous_state=None))
        args=self.observations(result);data=wf.load(args.observations);data['pages']=data['pages'][:1];pl.save(args.observations,data)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            code=pl.main(['review','--state',result['state'],'--observations',args.observations])
        report=json.loads(stream.getvalue())
        self.assertEqual(code,0);self.assertTrue(report['observations_saved']);self.assertFalse(report['ready'])
        self.assertEqual(report['saved_pages'],[1]);self.assertEqual(report['review_needed'],[2])
        self.assertIn('--previous-state',report['next'])
        with self.assertRaises(ValueError):
            pl.publish(Namespace(state=result['state'],output=str(self.root/'not-ready.pdf'),overwrite=False))
        self.assertFalse((self.root/'not-ready.pdf').exists())


    def accepted(self,output=None):
        self.prepared();args=self.args();args.output=str(output) if output else None
        result=pl.build(args);pl.verify(Namespace(state=result['state'],previous_state=None))
        pl.review(self.observations(result));return result

    def test_publish_writes_only_pdf_outside_task_and_does_not_rebuild(self):
        self.sp=self.root/'任务 空格'/'recovery'/'state.json'
        result=self.accepted();destination=self.root/'译文 空格.pdf'
        before={p.name for p in self.root.iterdir()};state_before=wf.load(result['state'])
        with patch.object(ip,'build',side_effect=AssertionError('publish must not rebuild')):
            published=pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False))
        self.assertEqual({p.name for p in self.root.iterdir()}-before,{destination.name})
        self.assertEqual(Path(published['notes']),(self.sp.parent.parent/'交付说明.md').resolve())
        self.assertFalse((self.sp.parent.parent/'work'/'rebuild').exists())
        current=wf.load(result['state']);self.assertEqual(current['qc'],state_before['qc'])
        self.assertTrue(pt.check_state(result['state'],True)['ready_for_delivery'])

    def test_unknown_state_location_requires_explicit_task_dir_before_copy(self):
        result=self.accepted(self.root/'自定 路径'/'candidate.pdf')
        destination=self.root/'published.pdf';before=Path(result['state']).read_bytes()
        with self.assertRaisesRegex(ValueError,'--task-dir'):
            pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False))
        self.assertFalse(destination.exists());self.assertEqual(Path(result['state']).read_bytes(),before)
        import contextlib
        import io
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            code=pl.main(['publish','--state',result['state'],'--output',str(destination),'--task-dir',str(self.root)])
        self.assertEqual(code,0);published=json.loads(output.getvalue())
        self.assertEqual(Path(published['notes']),(self.root/'交付说明.md').resolve())
        self.assertEqual(Path(published['recovery_argv'][-1]),(self.root/'work'/'rebuild'/'accepted.rebuilt.pdf').resolve())

    def test_publication_conflicts_are_found_before_copy_or_state_change(self):
        result=self.accepted();destination=self.root/'published.pdf'
        before=Path(result['state']).read_bytes()
        note=self.root/'交付说明.md';record=Path(result['state']).parent/'publication.json'
        for conflicting in (note,record,destination):
            with self.subTest(path=conflicting):
                conflicting.write_text('Existing user file',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'target exists'):
                    pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False))
                self.assertEqual(conflicting.read_text(encoding='utf-8'),'Existing user file')
                self.assertEqual(Path(result['state']).read_bytes(),before)
                if conflicting!=destination:self.assertFalse(destination.exists())
                conflicting.unlink()
        note.mkdir()
        with self.assertRaisesRegex(ValueError,'target exists'):
            pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=True))
        self.assertFalse(destination.exists());note.rmdir()
        note.write_text('Previous note',encoding='utf-8')
        self.assertTrue(pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=True))['ready'])

    def test_invalid_task_directory_is_rejected_before_publication(self):
        result=self.accepted();destination=self.root/'published.pdf';before=Path(result['state']).read_bytes()
        with self.assertRaisesRegex(ValueError,'inside --task-dir'):
            pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False,task_dir=str(self.root/'unrelated')))
        self.assertFalse(destination.exists());self.assertEqual(Path(result['state']).read_bytes(),before)


    def test_publication_directory_failures_leave_pdf_and_state_untouched(self):
        result=self.accepted();destination=self.root/'published.pdf';before=Path(result['state']).read_bytes()
        with patch.object(pl.tempfile,'TemporaryFile',side_effect=PermissionError('Fixture directory is not writable')):
            with self.assertRaises(PermissionError):
                pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False))
        self.assertFalse(destination.exists());self.assertEqual(Path(result['state']).read_bytes(),before)
        blocked=self.root/'work'/'rebuild';blocked.write_text('Not a directory',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Rebuild parent'):
            pl.publish(Namespace(state=result['state'],output=str(destination),overwrite=False))
        self.assertFalse(destination.exists());self.assertEqual(blocked.read_text(encoding='utf-8'),'Not a directory')

    def test_partial_reviews_survive_local_repair_and_merge_with_current_observations(self):
        source = self.root/'three-pages.pdf'
        with fitz.open(self.source) as doc:
            page = doc.new_page(width=240, height=180)
            page.insert_text((20, 40), 'Another label')
            doc.save(source)
        self.source = source
        self.prepared()
        previous = self.built()
        verified = pl.verify(Namespace(state=previous['state'], previous_state=None))
        self.assertEqual(verified['review_needed'], [1, 2, 3])
        obs = self.observations(previous)
        data = wf.load(obs.observations)
        data['pages'] = data['pages'][1:2]
        pl.save(obs.observations, data)
        self.assertFalse(pl.review(obs)['ready'])
        original = wf.load(previous['state'])['qc']['page_reviews'][0]

        state = wf.load(self.sp)
        block = next(b for b in state['pages'][0]['blocks'] if b['method'] == 'replace')
        edits = self.root/'repair.json'
        pl.save(edits, {'blocks': [{'page': 1, 'id': block['id'], 'translation': '项目'}]})
        preview = pl.apply_edits(self.args(edits=str(edits)))
        preview_args = self.args()
        preview_args.pages = preview['preview_argv'][-1]
        self.assertEqual(pl.build(preview_args)['pages'], [1])
        final = self.built()
        self.assertEqual(final['pages'], [1, 2, 3])
        args = Namespace(state=final['state'], previous_state=None)
        pl.verify(args)
        stale_args = Namespace(state=final['state'], observations=obs.observations)
        before = Path(final['state']).read_bytes()
        with self.assertRaisesRegex(ValueError, 'observation_fingerprint_mismatch'):
            pl.review(stale_args)
        self.assertEqual(Path(final['state']).read_bytes(), before)

        current = self.observations(final)
        bound = wf.load(current.observations)
        for field in ('output_sha256', 'render_index_sha256'):
            pl.save(current.observations, {**bound, field: '0' * 64})
            with self.assertRaisesRegex(ValueError, 'observation_fingerprint_mismatch'):
                pl.review(current)
            self.assertEqual(Path(final['state']).read_bytes(), before)
        pl.save(current.observations, bound)
        data = wf.load(current.observations)
        page1 = data['pages'][0]
        data['reviewer'] = 'Current fixture'
        data['pages'] = data['pages'][2:]
        pl.save(current.observations, data)
        self.assertFalse(pl.review(current)['ready'])
        args.previous_state = previous['state']
        checked = pl.verify(args)
        self.assertTrue(checked['cached'])
        self.assertEqual(checked['reused_pages'], [2])
        self.assertEqual(checked['review_needed'], [1])
        records = wf.load(final['state'])['qc']['page_reviews']
        for field in ('reviewer', 'reviewed_at', 'evidence'):
            self.assertEqual(records[0][field], original[field])
        self.assertEqual(records[1]['reviewer'], 'Current fixture')
        dest = self.root/'accepted.pdf'
        with self.assertRaises(ValueError):
            pl.publish(Namespace(state=final['state'], output=str(dest), overwrite=False))
        self.assertFalse(dest.exists())
        data['pages'] = [page1]
        pl.save(current.observations, data)
        self.assertTrue(pl.review(current)['ready'])
        self.assertTrue(pl.publish(Namespace(state=final['state'], output=str(dest), overwrite=False))['ready'])

    def test_one_bad_previous_page_does_not_discard_other_observations(self):
        self.prepared()
        old = self.built()
        old_check = pl.verify(Namespace(state=old['state'], previous_state=None))
        pl.review(self.observations(old))
        state = wf.load(self.sp)
        state['pages'][0]['blocks'][0]['translation'] = '项目'
        pl.save(self.sp, state)
        current = self.built()
        index_path = Path(old_check['render_index'])
        index = wf.load(index_path)
        old_state = wf.load(old['state'])
        duplicate = old_state['qc']['page_reviews'][0].copy()
        old_state['qc']['page_reviews'].append(duplicate)
        valid, _ = wf.checked_page_reviews(old_state, old['state'])
        self.assertEqual(set(valid), {2})
        old_state['qc']['page_reviews'].pop()
        (index_path.parent/index['pages'][0]['image']).write_bytes(b'changed')
        valid, errors = wf.checked_page_reviews(old_state, old['state'])
        self.assertEqual(set(valid), {2})
        self.assertEqual([x['page'] for x in errors], [1])
        result = pl.verify(Namespace(state=current['state'], previous_state=old['state']))
        self.assertEqual(result['reused_pages'], [2])
        self.assertEqual(result['review_needed'], [1])

    def test_aes_preflight_uses_declared_link_scope(self):
        from pypdf import PdfWriter
        plain = self.root/'plain.pdf'
        with fitz.open(self.source) as doc:
            doc[0].insert_link({'kind': fitz.LINK_GOTO, 'from': fitz.Rect(20, 60, 80, 80), 'page': 1})
            doc.save(plain)
        writer = PdfWriter(clone_from=plain)
        writer.encrypt('', algorithm='AES-128')
        writer.write(self.source)
        self.prepared()
        risks = wf.load(self.sp.parent/'preflight.json')['risks']
        self.assertFalse(any('link' in r['code'] or r['code'] == 'interaction_preflight' for r in risks))
        with fitz.open(self.built()['output']) as doc:
            self.assertEqual([link['page'] for link in doc[0].get_links()], [1, 1])
        self.sp = self.root/'sample'/'recovery'/'state.json'
        self.prepared('1')
        risks = wf.load(self.sp.parent/'preflight.json')['risks']
        self.assertIn('sample_link_omitted', {r['code'] for r in risks})
        sample = wf.load(self.built()['state'])
        self.assertEqual(len(sample['pages'][0]['omitted_links']), 1)

    def test_encryption_dependency_and_password_errors_are_distinct(self):
        from pypdf import PdfWriter
        from pypdf.errors import DependencyError
        locked = self.root/'locked.pdf'
        writer = PdfWriter(clone_from=self.source)
        writer.encrypt('test-password', algorithm='AES-128')
        writer.write(locked)
        self.source = locked
        with patch('pdf_tools.PdfReader.decrypt', side_effect=DependencyError('Missing AES backend')):
            with self.assertRaisesRegex(ValueError, 'missing_encryption_dependency'):
                self.prepared()
        with self.assertRaisesRegex(ValueError, 'password_required'):
            self.prepared()
        self.assertFalse(self.sp.exists())

    def test_edit_reports_remaining_blocks_and_stale_merge_sources(self):
        pl.prepare(Namespace(source=str(self.source), state=str(self.sp), pages='all',
                             profile='practical', overwrite=False, font=[str(self.font)]))
        state = wf.load(self.sp)
        first, numeric = state['pages'][0]['blocks']
        edits = self.root/'edits.json'
        pl.save(edits, {'blocks': [{'page': 1, 'id': 'merged', 'merge_ids': [first['id']],
                                    'method': 'replace', 'translation': '中文', 'font_size': 8}]})
        result = pl.apply_edits(self.args(edits=str(edits)))
        self.assertEqual(result['unresolved_count'], 1)
        self.assertEqual(result['unresolved_by_page'], [
            {'page': 2, 'blocks': [state['pages'][1]['blocks'][0]['id']]}])
        self.assertEqual(wf.load(self.sp)['pages'][0]['blocks'][1]['id'], numeric['id'])
        before = self.sp.read_bytes()
        with self.assertRaises(ValueError) as failure:
            pl.apply_edits(self.args(edits=str(edits)))
        error = json.loads(str(failure.exception))
        self.assertEqual((error['code'], error['page'], error['block']), ('invalid_merge_ids', 1, 'merged'))
        self.assertEqual(error['missing_ids'], [first['id']])
        self.assertEqual(self.sp.read_bytes(), before)


if __name__=='__main__':unittest.main()
