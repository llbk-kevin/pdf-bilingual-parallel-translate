"""Persistent authoring diagnostics, atomic patch simulation and figure anchors."""
import copy
import json
from argparse import Namespace
from unittest.mock import patch
import unittest
import test_pipeline as fixture

pl,ip,wf=fixture.pl,fixture.ip,fixture.wf


class EditChecks(unittest.TestCase):
    setUp=fixture.PracticalPipeline.setUp
    tearDown=fixture.PracticalPipeline.tearDown
    args=fixture.PracticalPipeline.args
    prepared=fixture.PracticalPipeline.prepared

    def submit(self,blocks):
        ep=self.root/'batch.json';pl.save(ep,{'blocks':blocks})
        return pl.apply_edits(self.args(edits=str(ep)))

    def progress(self):
        return pl.status(Namespace(state=self.sp,pages='all'))

    def test_other_page_does_not_erase_blocker_and_status_is_read_only(self):
        state=self.prepared();a=state['pages'][0]['blocks'][0]['id'];b=state['pages'][1]['blocks'][0]['id']
        self.submit([{'page':1,'id':a,'translation':'中文'*100}])
        r=self.submit([{'page':2,'id':b,'translation':'文中'}])
        self.assertEqual(r['preflight_blocked_pages'],[1])
        self.assertEqual(r['preview_argv'][-1],'2')
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        status=self.progress()
        self.assertEqual(status['preflight_blocked_pages'],[1])
        self.assertNotIn('build --state',status['next'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        # State, registered font and source mutations invalidate the relevant result.
        s=pl.load(self.sp);s['pages'][1]['blocks'][0]['translation']='中文';pl.save(self.sp,s)
        self.assertIn(2,self.progress()['preflight_unchecked_pages'])
        self.assertEqual(self.progress()['preflight_blocked_pages'],[1])
        self.font.write_bytes(self.font.read_bytes()+b'changed')
        self.assertEqual(self.progress()['preflight_unchecked_pages'],[1,2])
        self.font.write_bytes(self.font.read_bytes()[:-7])
        self.source.write_bytes(self.source.read_bytes()+b'\n')
        self.assertEqual(self.progress()['preflight_unchecked_pages'],[1,2])

    def test_unchecked_pages_and_checker_changes_are_never_passed(self):
        pl.prepare(Namespace(source=str(self.source),state=str(self.sp),pages='all',profile='practical',overwrite=False,font=[str(self.font)]))
        self.assertEqual(self.progress()['preflight_unchecked_pages'],[1,2])
        s=pl.load(self.sp)
        self.submit([{'page':p['source_page'],'id':b['id'],'method':'replace',
                      'translation':'中文','font_size':8}
                     for p in s['pages'] for b in p['blocks'] if b['method']=='unresolved'])
        self.assertEqual(self.progress()['preflight_passed_pages'],[1,2])
        with patch.object(pl.ec,'dependency_key',return_value='different-checker'):
            self.assertEqual(self.progress()['preflight_unchecked_pages'],[1,2])

    def test_cli_batch_summary_has_all_pages_and_keeps_details_on_disk(self):
        import contextlib,io
        self.prepared();ep=self.root/'invalid.json'
        pl.save(ep,{'blocks':[{'page':n,'id':'missing','translation':'中文'} for n in (1,2)]})
        out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pl.main(['apply','--state',str(self.sp),'--edits',str(ep)]),2)
        result=json.loads(out.getvalue())
        self.assertEqual(result['affected_pages'],[1,2])
        self.assertEqual(len(pl.load(result['report'])['detail']['edit_errors']),2)

    def test_batch_reports_independent_and_dependent_errors_without_writes(self):
        s=self.prepared();a=s['pages'][0]['blocks'][0]['id']
        original=self.sp.read_bytes();inventory=self.sp.with_name('inventory.json').read_bytes()
        with self.assertRaises(ValueError) as failure:
            self.submit([{'page':1,'id':'new','merge_ids':['missing-a'],'translation':'中文'},
                         {'page':1,'id':'after','merge_ids':['new',a],'translation':'中文'},
                         {'page':2,'id':'other','merge_ids':['missing-b'],'translation':'中文'}])
        errors=json.loads(str(failure.exception))['edit_errors']
        self.assertEqual(len(errors),3)
        self.assertEqual(errors[1]['code'],'edit_dependency_blocked')
        self.assertEqual(errors[2]['missing_ids'],['missing-b'])
        self.assertEqual(self.sp.read_bytes(),original)
        self.assertEqual(self.sp.with_name('inventory.json').read_bytes(),inventory)

    def test_sequential_merge_update_and_owner_hint(self):
        s=self.prepared();a=s['pages'][0]['blocks'][0]['id']
        self.submit([{'page':1,'id':'merged','merge_ids':[a],'translation':'中文'},
                     {'page':1,'id':'merged','translation':'文中'}])
        self.assertEqual(pl.load(self.sp)['pages'][0]['blocks'][0]['translation'],'文中')
        with self.assertRaises(ValueError) as failure:
            self.submit([{'page':1,'id':'again','merge_ids':[a],'translation':'中文'}])
        row=json.loads(str(failure.exception))['edit_errors'][0]
        self.assertEqual(row['current_owner_hints'][a],['merged'])
        with self.assertRaisesRegex(ValueError,'duplicate_edit_target'):
            self.submit([{'page':1,'id':'merged','translation':'中文'},
                         {'page':1,'id':'merged','translation':'文中'}])

    def test_geometry_errors_name_the_edit_file_and_block(self):
        s=self.prepared();bid=s['pages'][0]['blocks'][0]['id'];before=self.sp.read_bytes()
        with self.assertRaises(ValueError) as failure:
            self.submit([{'page':1,'id':bid,'allowed_bbox':[-20,0,100,200]}])
        errors=json.loads(str(failure.exception))['edit_errors']
        self.assertTrue(all(e.get('edit_file')==str(self.root/'batch.json') and e.get('block')==bid for e in errors))
        self.assertEqual(self.sp.read_bytes(),before)

    def test_package_patch_chain_is_atomic_and_replayable(self):
        s=self.prepared();a=s['pages'][0]['blocks'][0]['id']
        package=pl.package(Namespace(state=self.sp,pages='1',out=self.root/'package',owner='translator'))
        first=self.root/'initial.json';repair=self.root/'repair.json'
        pl.save(first,{'blocks':[{'page':1,'id':'merged','merge_ids':[a],'translation':'中文'}]})
        pl.save(repair,{'blocks':[{'page':1,'id':'merged','translation':'文中'}]})
        args=self.args(edits=[str(first),str(repair)],package=[package['package']]*2)
        result=pl.apply_edits(args)
        self.assertEqual(result['changed_pages'],[1])
        self.assertEqual(pl.load(self.sp)['pages'][0]['blocks'][0]['translation'],'文中')
        saved=self.sp.read_bytes()
        self.assertEqual(pl.apply_edits(args)['state_written_bytes'],0)
        self.assertEqual(self.sp.read_bytes(),saved)

    def test_package_partial_prior_commit_still_requires_fresh_baseline(self):
        s=self.prepared();a=s['pages'][0]['blocks'][0]['id']
        package=pl.package(Namespace(state=self.sp,pages='1',out=self.root/'package',owner='translator'))
        first=self.root/'first.json';second=self.root/'second.json'
        pl.save(first,{'blocks':[{'page':1,'id':a,'translation':'文中'}]})
        pl.save(second,{'blocks':[{'page':1,'id':a,'translation':'中文'}]})
        pl.apply_edits(self.args(edits=[str(first)],package=[package['package']]))
        before=self.sp.read_bytes()
        with self.assertRaisesRegex(ValueError,'package_baseline_changed'):
            pl.apply_edits(self.args(edits=[str(first),str(second)],package=[package['package']]*2))
        self.assertEqual(self.sp.read_bytes(),before)
        # Shared dependency changes are not waived by the batch mechanism.
        s=pl.load(self.sp);s['issues']=['Shared note'];pl.save(self.sp,s)
        with self.assertRaisesRegex(ValueError,'shared dependencies changed'):
            pl.apply_edits(self.args(edits=[str(second)],package=[package['package']]))

    def test_layout_collision_and_anchor_are_reported_in_one_apply(self):
        doc=ip.fitz.open(self.source)
        doc[1].insert_link({'kind':ip.fitz.LINK_GOTO,'from':ip.fitz.Rect(20,28,45,42),'page':0})
        self.source=self.root/'links.pdf';doc.save(self.source);doc.close()
        s=self.prepared();a=s['pages'][0]['blocks'][0];b=s['pages'][1]['blocks'][0]
        r=self.submit([{'page':1,'id':a['id'],'translation':'中文'*100},
                       {'page':2,'id':b['id'],'allowed_bbox':[20,88,150,106],
                        'expansion_reason':'Synthetic collision injection'}])
        report=pl.load(r['layout_check']['details'])
        self.assertTrue({'height_overflow','preserved_or_cover_collision','link_anchor_unresolved'}<=report['groups'].keys())
        self.assertIsNone(r['preview_argv'])
        self.assertEqual(pl.load(self.sp)['pages'][0]['blocks'][0]['translation'],'中文'*100)
        self.assertIn(1,r['preflight_unchecked_pages'])

    def figure_source(self,anchor='Figure 12'):
        doc=ip.fitz.open();p=doc.new_page(width=240,height=180)
        p.insert_text((20,40),'See '+anchor+' now.')
        region=p.search_for(anchor)[0]
        doc.new_page(width=240,height=180).insert_text((20,40),'Caption')
        doc[0].insert_link({'kind':ip.fitz.LINK_GOTO,'from':region,'page':1})
        self.source=self.root/'figure.pdf';doc.save(self.source);doc.close()

    def test_unique_figure_anchor_build_keeps_destination(self):
        self.figure_source();s=self.prepared();bid=s['pages'][0]['blocks'][0]['id']
        r=self.submit([{'page':1,'id':bid,'translation':'中文 图 12'}])
        self.assertFalse(r['preflight_blocked_pages'])
        built=pl.build(self.args())
        with ip.fitz.open(built['output']) as doc:
            links=doc[0].get_links()
            self.assertEqual(len(links),2)
            self.assertEqual([link['page'] for link in links],[1,1])
            self.assertGreater(max(link['from'].x0 for link in links),240)
        self.assertFalse(pl.load(self.sp)['pages'][0].get('link_overrides'))

    def test_duplicate_or_missing_figure_anchor_requires_explicit_mapping(self):
        self.figure_source();s=self.prepared();bid=s['pages'][0]['blocks'][0]['id']
        for text in ['图 12 图 12','图 123','中文']:
            r=self.submit([{'page':1,'id':bid,'translation':text}])
            self.assertIn('link_anchor_unresolved',pl.load(r['layout_check']['details'])['groups'])
    def test_incomplete_source_figure_anchor_is_not_guessed(self):
        self.figure_source(anchor='Figure');s=self.prepared();bid=s['pages'][0]['blocks'][0]['id']
        r=self.submit([{'page':1,'id':bid,'translation':'中文 图 12'}])
        self.assertIn('link_anchor_unresolved',pl.load(r['layout_check']['details'])['groups'])

    def test_font_suggestion_does_not_change_declared_lower_bound(self):
        s=self.prepared();b=s['pages'][0]['blocks'][0]
        x0,y0,x1,y1=b['source_bbox']
        r=self.submit([{'page':1,'id':b['id'],'font_size':12,'font_size_min':11,
                       'allowed_bbox':[x0,y0,x1,y0+5]}])
        row=next(f for f in pl.load(r['layout_check']['details'])['findings'] if f['code']=='height_overflow')
        self.assertTrue(row['fit_suggestion']['below_declared_minimum'])
        self.assertEqual(pl.load(self.sp)['pages'][0]['blocks'][0]['font_size_min'],11)
        self.assertTrue(row['fit_suggestion']['requires_readability_confirmation'])
