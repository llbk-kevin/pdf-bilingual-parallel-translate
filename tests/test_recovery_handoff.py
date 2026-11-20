"""Transactional recovery and isolated package handoffs on generated documents."""
import copy
import json
import os
from argparse import Namespace
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pipeline as pl
import inplace as ip
import pdf_tools as pt
import workflow as wf
import test_pipeline as fixtures


class RecoveryHandoff(unittest.TestCase):
    setUp=fixtures.PracticalPipeline.setUp
    tearDown=fixtures.PracticalPipeline.tearDown
    args=fixtures.PracticalPipeline.args
    prepared=fixtures.PracticalPipeline.prepared
    built=fixtures.PracticalPipeline.built

    def prepare_args(self,overwrite=False):
        return Namespace(source=str(self.source),state=str(self.sp),pages='all',
                         profile='practical',overwrite=overwrite,font=[str(self.font)])

    def test_prepare_failure_does_not_publish_partial_state_or_modify_user_files(self):
        self.sp.parent.mkdir()
        keep=self.sp.parent/'用户 字体.txt';keep.write_text('保留',encoding='utf-8')
        for target in ('freeze_runtime','preflight'):
            with self.subTest(stage=target),patch.object(pl,target,side_effect=RuntimeError('injected')):
                with self.assertRaisesRegex(RuntimeError,'injected'):pl.prepare(self.prepare_args())
            self.assertFalse(self.sp.exists())
            self.assertEqual(list(self.sp.parent.iterdir()),[keep])
        args=self.prepare_args();args.font=[str(self.root/'missing.ttf')]
        with self.assertRaises(FileNotFoundError):pl.prepare(args)
        self.assertFalse(self.sp.exists())
        self.assertEqual(keep.read_text(encoding='utf-8'),'保留')
        pl.prepare(self.prepare_args())
        self.assertTrue(self.sp.exists())

    def test_staged_prepare_never_overwrites_an_input_even_with_overwrite(self):
        original=self.source.read_bytes()
        args=self.prepare_args(True);args.state=str(self.source)
        with self.assertRaisesRegex(ValueError,'overwrite source or font'):pl.prepare(args)
        self.assertEqual(self.source.read_bytes(),original)
        font=self.sp.parent/'runtime.py';font.parent.mkdir();font.write_bytes(self.font.read_bytes())
        original=font.read_bytes();args=self.prepare_args();args.font=[str(font)]
        with self.assertRaisesRegex(ValueError,'overwrite source or font'):pl.prepare(args)
        self.assertEqual(font.read_bytes(),original)

    def test_commit_failure_rolls_back_existing_recovery_and_keeps_state_last(self):
        self.prepared()
        original={p.name:p.read_bytes() for p in self.sp.parent.iterdir() if p.is_file()}
        replace=Path.replace
        committed=[]
        def fail_state(p,target):
            committed.append(Path(target).name)
            if Path(target).resolve()==self.sp.resolve():raise OSError('commit interrupted')
            return replace(p,target)
        with patch.object(Path,'replace',fail_state):
            with self.assertRaisesRegex(OSError,'commit interrupted'):pl.prepare(self.prepare_args(True))
        self.assertEqual(committed[-1],self.sp.name)
        self.assertEqual(original,{p.name:p.read_bytes() for p in self.sp.parent.iterdir() if p.is_file()})

    @unittest.skipUnless(os.name=='nt','Native cross-drive path semantics')
    def test_cross_drive_references_resolve_without_copying(self):
        self.assertEqual(wf.resolve(Path('C:/recovery'),ip.relative('D:/资料/原文.pdf','C:/recovery')),Path('D:/资料/原文.pdf'))
        self.assertFalse(Path(ip.relative('C:/资料/原文.pdf','C:/recovery')).is_absolute())

    def test_generated_commands_run_isolated_and_package_paths_are_correct(self):
        prepared=pl.prepare(self.prepare_args())
        for name in ('status_argv','inspect_argv','source_render_argv'):
            result=subprocess.run(prepared['commands'][name],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
        package=pl.package(Namespace(state=self.sp,pages='1',out=self.root/'包 空格',owner='translator'))
        result=subprocess.run(package['commands']['inspect_argv'],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['page_count'],1)

    def test_refreeze_preserves_authorship_and_old_package_then_merges_fresh_patch(self):
        state=self.prepared()
        old_builder=self.sp.parent/'inplace.py'
        old_builder.write_text(old_builder.read_text(encoding='utf-8')+'\n# Earlier frozen version\n',encoding='utf-8')
        next(item for item in state['layout']['inputs'] if item['path']=='inplace.py')['sha256']=wf.digest(old_builder)
        pl.save(self.sp,state)
        snapshot={p.name:p.read_bytes() for p in self.sp.parent.iterdir() if p.is_file()}
        package=pl.package(Namespace(state=self.sp,pages='1',out=self.root/'old-package',owner='translator'))
        updated=pl.refreeze(Namespace(state=self.sp,out=self.root/'recovery-v2'))
        sp=Path(updated['state']);new=wf.load(sp)
        self.assertEqual(new['pages'],state['pages'])
        self.assertEqual(wf.digest(pl.source_path(new,sp)),state['source']['sha256'])
        self.assertEqual(snapshot,{p.name:p.read_bytes() for p in self.sp.parent.iterdir() if p.is_file()})
        edits=self.root/'patch.json';pl.save(edits,{'blocks':[{'page':1,'id':new['pages'][0]['blocks'][0]['id'],'translation':'文中'}]})
        with self.assertRaisesRegex(ValueError,'shared dependencies changed'):
            pl.apply_edits(Namespace(state=sp,edits=[str(edits)],package=[package['package']]))
        fresh=pl.package(Namespace(state=sp,pages='1',out=self.root/'new-package',owner='translator'))
        result=pl.apply_edits(Namespace(state=sp,edits=[str(edits)],package=[fresh['package']]))
        self.assertEqual(result['changed_pages'],[1])
        build=pl.build(Namespace(state=sp,pages='1',source=None,output=None,overwrite=False))
        self.assertTrue(Path(build['output']).exists())
        with self.assertRaisesRegex(ValueError,'new recovery directory'):pl.refreeze(Namespace(state=self.sp,out=sp.parent))

    def test_refreeze_rejects_candidates_and_failure_keeps_old_bytes(self):
        self.prepared();result=self.built()
        with self.assertRaisesRegex(ValueError,'authoring'):pl.refreeze(Namespace(state=result['state'],out=self.root/'candidate-copy'))
        old=self.sp.read_bytes()
        with patch.object(pl,'preflight',side_effect=RuntimeError('injected')):
            with self.assertRaisesRegex(RuntimeError,'injected'):pl.refreeze(Namespace(state=self.sp,out=self.root/'failed'))
        self.assertFalse((self.root/'failed').exists())
        self.assertEqual(self.sp.read_bytes(),old)

    def test_zero_area_preserve_must_match_immutable_glyphs_and_never_relaxes_replace(self):
        state=self.prepared();page=copy.deepcopy(state['pages'][0])
        glyph=page['glyphs'][0]
        glyph.update(bbox=[20,40,20,40],text='0')
        block=page['blocks'][0]
        block.update(source_bbox=[20,40,20,40],allowed_bbox=[20,40,20,40],glyph_ids=[glyph['id']],
                     glyph_ranges=[[0,1]],method='preserve',reason='Zero source fixture',source_text='0')
        page['glyphs']=[glyph];page['blocks']=[block]
        page['expected_blocks']=[block['id']];page['reading_order']=[block['id']]
        self.assertEqual(ip.validate_page(page,copy.deepcopy(page),final=True),[])
        for method in ('replace','cover'):
            invalid=copy.deepcopy(page);invalid['blocks'][0]['method']=method
            self.assertTrue(ip.validate_page(invalid,page,final=True))
        invalid=copy.deepcopy(page);invalid['glyphs'][0]['bbox']=[20,40,25,50]
        self.assertTrue(ip.validate_page(invalid,invalid,final=True))
        for box in ([20,40,19,40],[20,float('nan'),20,40]):
            invalid=copy.deepcopy(page);invalid['blocks'][0]['source_bbox']=box
            self.assertTrue(ip.validate_page(invalid,page,final=True))


if __name__=='__main__':unittest.main()
