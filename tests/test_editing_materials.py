"""Translation materials and actionable preview ranges, with synthetic inputs."""
import copy
import unittest
from argparse import Namespace
from unittest.mock import patch
import test_pipeline as fixture

pl, ip, wf = fixture.pl, fixture.ip, fixture.wf


class EditingMaterials(unittest.TestCase):
    setUp = fixture.PracticalPipeline.setUp
    tearDown = fixture.PracticalPipeline.tearDown
    args = fixture.PracticalPipeline.args
    prepared = fixture.PracticalPipeline.prepared

    def test_group_boundaries_and_unresolved_only_template(self):
        def block(identifier, group=1, rotation=0, method='unresolved', line=0):
            return dict(id=identifier,source_group=group,rotation=rotation,method=method,
                        source_line=line,source_text=identifier,source_bbox=[0,0,10,10])
        blocks = [block('a'),block('b',line=1),block('c',rotation=90),
                  block('formula',method='preserve'),block('d'),block('e',group=None),
                  block('f',group=None),block('g',line=4),block('h',line=7)]
        state = {'pages':[{'source_page':1,'blocks':blocks},
                          {'source_page':2,'blocks':[block('other')]}]}
        original = copy.deepcopy(state)
        groups, template = pl.editing_materials(state)
        self.assertEqual(groups['pages'][0]['groups'][0]['block_ids'],['a','b'])
        self.assertEqual(len(groups['pages'][0]['groups']),8)
        self.assertEqual(template['blocks'][0]['merge_ids'],['a','b'])
        self.assertNotIn('formula',[b['id'] for b in template['blocks']])
        self.assertEqual(state,original)
        self.assertEqual(pl.editing_materials(state),(groups,template))

    def test_prepare_package_template_apply_and_increment(self):
        result = pl.prepare(Namespace(source=str(self.source),state=str(self.sp),pages='all',
                                     profile='practical',overwrite=False,font=[str(self.font)]))
        self.assertTrue(pl.load(result['groups'])['pages'])
        template = pl.load(result['edits_template'])
        for edit in template['blocks']:
            edit.update(translation='中文',font_size=8,font_size_min=7)
        ep = self.root/'filled.json';pl.save(ep,template)
        applied = pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(applied['unresolved_count'],0)
        target = template['blocks'][0]
        pl.save(ep,{'blocks':[{'page':target['page'],'id':target['id'],'translation':'文中'}]})
        self.assertEqual(pl.apply_edits(self.args(edits=str(ep)))['unresolved_count'],0)
        package = pl.package(Namespace(state=self.sp,pages='1',out=self.root/'package',owner='fixture'))
        self.assertEqual([p['page'] for p in pl.load(package['groups'])['pages']],[1])
        self.assertEqual(pl.load(package['edits_template']),{'blocks':[]})

    def test_group_inspection_is_read_only_filtered_and_paginated(self):
        self.prepared()
        before = self.sp.read_bytes()
        args = Namespace(state=str(self.sp),pages='1',block=None,detail='groups',limit=1,offset=0)
        first = pl.inspect_state(args)
        self.assertEqual(len(first['items']),1)
        self.assertEqual(first['next_offset'],1)
        args.offset=1
        second=pl.inspect_state(args)
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        args.block=[first['items'][0]['block_ids'][0]];args.offset=0
        self.assertEqual(pl.inspect_state(args)['total_items'],1)
        args.pages='all'
        with self.assertRaisesRegex(ValueError,'explicit --pages'):
            pl.inspect_state(args)
        self.assertEqual(self.sp.read_bytes(),before)

    def test_ready_pending_and_overflow_pages_are_separated(self):
        doc = ip.fitz.open(self.source)
        page=doc.new_page(width=240,height=180);page.insert_text((20,40),'Third page')
        third=self.root/'three.pdf';doc.save(third);doc.close();self.source=third
        state=self.prepared()
        edits=[]
        for page in state['pages']:
            block=next(b for b in page['blocks'] if b['method']=='replace')
            edit={'page':page['source_page'],'id':block['id']}
            if page['source_page']==1:edit['translation']='文中'
            elif page['source_page']==2:edit['method']='unresolved'
            else:edit['translation']='中文'*100
            edits.append(edit)
        ep=self.root/'mixed.json';pl.save(ep,{'blocks':edits})
        result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(result['preview_argv'][-1],'1')
        self.assertEqual(result['preview_skipped_pages'],[2,3])
        self.assertEqual(result['preview_blocked_by_page'][0]['reasons'],['pending_translation'])

    def test_global_font_failure_still_saves_edits_without_preview(self):
        state=self.prepared()
        edit={'page':1,'id':state['pages'][0]['blocks'][0]['id'],'translation':'文中'}
        ep=self.root/'edit.json';pl.save(ep,{'blocks':[edit]})
        with patch.object(ip,'load_fonts',side_effect=RuntimeError('font unavailable')):
            result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertIsNone(result['preview_argv'])
        self.assertEqual(result['preview_skipped_pages'],[1])
        self.assertEqual(result['preview_blocked_by_page'][0]['reasons'],['layout_check_failed'])
        self.assertEqual(pl.load(self.sp)['pages'][0]['blocks'][0]['translation'],'文中')

    def test_width_and_overlap_findings_block_only_their_pages(self):
        state=self.prepared()
        first=next(b for b in state['pages'][0]['blocks'] if b['method']=='replace')
        second=next(b for b in state['pages'][1]['blocks'] if b['method']=='replace')
        ep=self.root/'width.json'
        x0,y0,x1,y1=first['source_bbox']
        pl.save(ep,{'blocks':[{'page':1,'id':first['id'],'allowed_bbox':[x0,y0,x0+.01,y1]},
                             {'page':2,'id':second['id'],'translation':'文中'}]})
        result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(result['preview_argv'][-1],'2')
        self.assertIn('single_glyph_too_wide',result['preview_blocked_by_page'][0]['reasons'])
        # Model two validly measured translations colliding: the gate uses all
        # layout findings, not just needs_attention or overflow counters.
        report={'counts':{},'groups':{},'findings':[{'page':2,'code':'translation_overlap'}]}
        with patch.object(ip,'layout_preflight',return_value=({},report)):
            result=pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(result['preview_argv'][-1],'1')
        self.assertEqual(result['preview_blocked_by_page'],[{'page':2,'reasons':['translation_overlap']}])
