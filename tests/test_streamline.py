"""Current authoring/hand-off contract, with generated source material."""
import copy
import shutil
import unittest
from argparse import Namespace
from pathlib import Path
import test_pipeline as fixture

pl, ip, wf = fixture.pl, fixture.ip, fixture.wf


class Streamline(unittest.TestCase):
    setUp = fixture.PracticalPipeline.setUp
    tearDown = fixture.PracticalPipeline.tearDown
    args = fixture.PracticalPipeline.args
    prepared = fixture.PracticalPipeline.prepared
    observations = fixture.PracticalPipeline.observations

    def test_import_current_results_is_atomic_scoped_idempotent_and_clean(self):
        state=self.prepared();initial=copy.deepcopy(state)
        out=self.root/'包 空格';package=pl.package(Namespace(state=self.sp,pages='1',out=out,owner='translator'))
        sp=Path(package['state']);bid=state['pages'][0]['blocks'][0]['id']
        ep=out/'edits.json'
        for text in ('文中','项目'):
            pl.save(ep,{'blocks':[{'page':1,'id':bid,'translation':text}]})
            pl.apply_edits(Namespace(state=sp,edits=str(ep)))
        local=pl.load(sp);local['qc']={'forged':'must not import'}
        local['pages'][0]['inventory_reviewed']=True
        pl.save(sp,local);args=Namespace(state=self.sp,package=out)
        original=self.sp.read_bytes();bad=copy.deepcopy(local)
        bad['pages'][0]['glyphs'][0]['text']='X';pl.save(sp,bad)
        with self.assertRaises(ValueError):pl.import_package(args)
        self.assertEqual(self.sp.read_bytes(),original)
        pl.save(sp,local);self.assertEqual(pl.import_package(args)['changed_pages'],[1])
        imported=pl.load(self.sp)
        self.assertEqual(imported['pages'][0]['blocks'][0]['translation'],'项目')
        self.assertEqual(imported['pages'][1],initial['pages'][1])
        self.assertEqual(imported['layout'],initial['layout'])
        self.assertEqual(imported['qc'],{})
        self.assertFalse(imported['pages'][0]['inventory_reviewed'])
        saved=self.sp.read_bytes();self.assertEqual(pl.import_package(args)['state_written_bytes'],0)
        self.assertEqual(self.sp.read_bytes(),saved)
        local['pages'][0]['blocks'][0]['translation']='文中';pl.save(sp,local)
        with self.assertRaisesRegex(ValueError,'package_baseline_changed'):pl.import_package(args)

    def test_wrong_state_and_partial_repair_never_publish(self):
        self.prepared();built=pl.build(self.args());sp=Path(built['state'])
        before=sp.read_bytes();ep=self.root/'edit.json';pl.save(ep,{'issues':['wrong stage']})
        with self.assertRaisesRegex(ValueError,'wrong_state_purpose'):
            pl.apply_edits(Namespace(state=sp,edits=str(ep)))
        self.assertEqual(sp.read_bytes(),before)
        with self.assertRaisesRegex(ValueError,'wrong_state_purpose'):
            pl.verify(Namespace(state=self.sp,previous_state=None))
        pl.verify(Namespace(state=sp,previous_state=None))
        args=self.observations(built);obs=pl.load(args.observations)
        obs['pages'][1]['decision']='repair';obs['pages'][1]['notes']=['Synthetic table issue']
        pl.save(args.observations,obs);result=pl.review(args)
        self.assertEqual(result['repair_pages'],[2]);self.assertEqual(result['reviewed_pages'],[1])
        pl.verify(Namespace(state=sp,previous_state=None))
        with self.assertRaises(ValueError):pl.publish(Namespace(state=sp,output=self.root/'accepted.pdf',overwrite=False))
        obs['pages']=obs['pages'][1:];obs['pages'][0]['decision']='pass';pl.save(args.observations,obs)
        self.assertTrue(pl.review(args)['ready'])

    def test_package_relocation_rejection_and_recovery_from_interrupted_import(self):
        from unittest.mock import patch
        state=self.prepared();initial=self.sp.read_bytes()
        original=self.root/'original';pl.package(Namespace(state=self.sp,pages='1',out=original,owner='translator'))
        moved=self.root/'relocated';shutil.copytree(original,moved)
        sp=moved/'state.json';local=pl.load(sp)
        pl.relocate_state(local,original,moved);pl.save(sp,local)
        args=Namespace(state=self.sp,package=moved)
        for case in ('scope','source','font','glyph','candidate'):
            bad=copy.deepcopy(local)
            if case=='scope':bad['pages'].append(copy.deepcopy(state['pages'][1]))
            elif case=='source':bad['source']['sha256']='0'*64
            elif case=='font':bad['layout']['fonts'][0]['sha256']='0'*64
            elif case=='glyph':bad['pages'][0]['blocks'][0]['glyph_ids']=[]
            else:bad['output']={'sha256':'0'*64}
            pl.save(sp,bad)
            with self.subTest(case=case),self.assertRaises(ValueError):pl.import_package(args)
            self.assertEqual(self.sp.read_bytes(),initial)
        pl.save(sp,local)
        with patch.object(pl,'save_edits',side_effect=OSError('interrupted before atomic commit')):
            with self.assertRaises(OSError):pl.import_package(args)
        self.assertEqual(self.sp.read_bytes(),initial)
        self.assertEqual(pl.import_package(args)['changed_pages'],[1])
        pl.save(sp,{**local,'pages':[{**local['pages'][0],'glyphs':[]}]})
        with self.assertRaises(ValueError):pl.import_package(args)

    def test_nested_quote_is_right_private_and_keeps_text_positions(self):
        doc=ip.fitz.open();p=doc.new_page(width=240,height=180)
        p.insert_text((20,150),'Translate footer',fontsize=10)
        resources=doc.xref_get_key(p.xref,'Resources')[1]
        leaf=doc.get_new_xref()
        doc.update_object(leaf,'<< /Type /XObject /Subtype /Form /BBox [0 0 240 180] /Resources '+resources+' >>')
        doc.update_stream(leaf,b"BT /helv 10 Tf 12 TL 20 120 Td (OUT) Tj (GND)' ET")
        nested=doc.get_new_xref()
        doc.update_object(nested,f'<< /Type /XObject /Subtype /Form /BBox [0 0 240 180] /Resources << /XObject << /Child {leaf} 0 R >> >> >>')
        doc.update_stream(nested,b'/Child Do')
        doc.xref_set_key(int(resources.split()[0]),'XObject',f'<< /Nested {nested} 0 R >>')
        extra=doc.get_new_xref();doc.update_object(extra,'<<>>');doc.update_stream(extra,b'/Nested Do')
        doc.xref_set_key(p.xref,'Contents','['+' '.join(f'{n} 0 R' for n in p.get_contents()+[extra])+']')
        doc.save(self.source);doc.close()
        state=self.prepared()
        for b in state['pages'][0]['blocks']:
            if b['source_text'] in ('OUT','GND'):
                b.update(method='preserve',translation=b['source_text'],reason='Native pin')
        pl.save(self.sp,state)
        built=pl.build(self.args())
        with ip.fitz.open(self.source) as src, ip.fitz.open(built['output']) as out:
            self.assertEqual(src[0].get_pixmap().samples,
                             out[0].get_pixmap(clip=src[0].rect).samples)
            before=ip.right_visible_trace(src[0],0)
            after=ip.right_visible_trace(out[0],240)
            for char in before:
                if char[2]<100:
                    self.assertTrue(any(v[0]==char[0] and abs(v[1]-char[1])<.001 and abs(v[2]-char[2])<.001 for v in after))
        normalized=pl.load(built['state'])['pages'][0]['native_text_normalization']
        self.assertEqual(sum(f['quote_operators'] for f in normalized['forms']),1)

    def test_cells_not_recommended_or_explicitly_merged_and_split_restores(self):
        doc=ip.fitz.open();p=doc.new_page(width=240,height=180)
        p.insert_text((20,40),'First line',fontsize=10)
        p.insert_text((20,55),'Second line',fontsize=10)
        p.insert_text((130,40),'Other cell',fontsize=10)
        p.draw_line((110,10),(110,100))
        doc.save(self.source);doc.close()
        state=self.prepared();p=state['pages'][0]
        a,b,c=sorted(p['blocks'],key=lambda b:(b['source_bbox'][0],b['source_bbox'][1]))
        for item in p['blocks']:item.update(source_group=1,method='unresolved')
        groups=pl.grouped_inventory(state)['pages'][0]['groups']
        self.assertTrue(all(not({a['id'],c['id']}<=set(g['block_ids'])) for g in groups))
        state=pl.load(self.sp);p=state['pages'][0]
        ep=self.root/'edit.json';original=self.sp.read_bytes()
        pl.save(ep,{'blocks':[{'page':1,'id':a['id'],'merge_ids':[a['id'],c['id']],'translation':'中文'}]})
        with self.assertRaisesRegex(ValueError,'merge_crosses_separator'):
            pl.apply_edits(self.args(edits=str(ep)))
        self.assertEqual(self.sp.read_bytes(),original)
        pl.save(ep,{'blocks':[{'page':1,'id':a['id'],'merge_ids':[a['id'],b['id']],'translation':'中文'}]})
        pl.apply_edits(self.args(edits=str(ep)))
        pl.save(ep,{'blocks':[{'page':1,'id':a['id'],'split':True}]})
        pl.apply_edits(self.args(edits=str(ep)))
        restored=pl.load(self.sp)['pages'][0]
        self.assertEqual(restored['glyphs'],p['glyphs'])
        self.assertEqual({b['id'] for b in restored['blocks']},{b['id'] for b in p['blocks']})
        self.assertEqual(restored['split_notes'][0]['translation'],'中文')


if __name__ == '__main__':unittest.main()
