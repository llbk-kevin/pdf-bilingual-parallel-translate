"""Naming and historical relocation tests; all artifacts are synthetic."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow as w
import pdf_tools as t


class Naming(unittest.TestCase):
    def test_explicit_roles(self):
        for fn in (w.document_filename, w.ti_filename):
            with self.assertRaises(TypeError): fn('Title', '标题')
        with self.assertRaises(ValueError): w.document_filename('Title', '标题', role='pdf')
        self.assertEqual(w.document_filename('Title', '标题', role='original'), 'Title_标题.pdf')
        self.assertEqual(w.document_filename('Title', '标题', role='generated-translation'),
                         'Title_标题_双语左右对照翻译.pdf')

    def test_generic_identifiers_keep_official_form(self):
        for identity in ('5989-7894EN', 'AP24026', 'CDL6566', '12345'):
            self.assertTrue(w.document_filename('Title', '标题', identity, role='original').startswith(identity+'_'))
        self.assertTrue(w.ti_filename('Title', '标题', 'SLVA317B', role='original').startswith('slva317b_'))
        with self.assertRaises(ValueError): w.ti_filename('Title', '标题', '5989-7894EN', role='original')

    def test_missing_numbers_and_non_english_titles(self):
        for number in (None, '', ' '):
            self.assertEqual(w.document_filename('日本語の文章', '日文文章', number, role='original'),
                             '日本語の文章_日文文章.pdf')
        self.assertEqual(w.document_filename('中文文章', '中文文章', role='original', source_is_chinese=True), '中文文章.pdf')
        self.assertEqual(w.document_filename(chinese_title='官方中文标题', role='official-chinese'), '官方中文标题.pdf')
        self.assertEqual(w.ti_filename(chinese_title='中文', english_document_id='SNVAA43', role='official-chinese'),
                         'snvaa43_中文.pdf')

    def test_papers_omit_identifiers_and_versions_remain(self):
        self.assertEqual(w.document_filename('Article', '论文', '10.3390/s22145127', paper=True,
                         version='V2', role='original'), 'Article_论文（V2）.pdf')
        self.assertEqual(w.document_filename('Title', '标题（Rev1.7）', version='Rev1.7', role='original'),
                         'Title_标题（Rev1.7）.pdf')

    def test_suffix_cleanup_is_role_specific_and_repeatable(self):
        for role, suffix in [('original',''), ('generated-translation',w.TRANSLATION_SUFFIX)]:
            args = ('Title', '标题'+w.TRANSLATION_SUFFIX*2)
            a = w.document_filename(*args, role=role, version='V3.5')
            self.assertEqual(a, 'Title_标题（V3.5）'+suffix+'.pdf')
            self.assertEqual(a, w.document_filename(*args, role=role, version='V3.5'))

    def test_filename_safety_without_silent_truncation(self):
        self.assertEqual(w.document_filename('First\nTitle: A/B', '标题', role='original'),
                         'First Title - A／B_标题.pdf')
        with self.assertRaises(ValueError): w.document_filename('x'*255, '标题', role='original')
        with self.assertRaises(ValueError): w.document_filename('CON', role='original', source_is_chinese=True)


class Relocation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sp = self.root/'state.json'
        self.history = self.root/'history'
        self.history.mkdir()
        self.state = {'schema_version':1,'source':{'path':'original.pdf','sha256':'a'*64},
                      'output':{'path':'translated.pdf','sha256':'b'*64},'layout':{},
                      'glossary':[],'pages':[],'issues':[],'qc':{}}
        self.state['qc'] = {'content_sha256':t.content_hash(self.state), 'reviewer':'synthetic fixture'}
        self.write(self.sp,self.state)

    def tearDown(self): self.temp.cleanup()
    def write(self,p,s): p.write_text(json.dumps(s),encoding='utf-8')
    def move(self,s,number,target):
        previous=self.history/('before-'+str(number)+'.json')
        self.write(previous,s)
        moved=copy.deepcopy(s)
        moved['source']['path']=target
        moved['output']['path']='new-'+str(number)+'.pdf'
        moved['migration']={'kind':'path-only','performed_at':'2000-01-01T00:00:00Z','reason':'test rename',
                            'previous_state':{'path':str(previous.relative_to(self.root)),
                                              'sha256':w.digest(previous),'base_path':'.'},
                            'old_source':s['source']['path'],'new_source':target}
        self.write(self.sp,moved)
        return moved

    def test_multiple_moves_and_return_to_original_path(self):
        one=self.move(self.state,1,'second.pdf')
        self.assertTrue(w.validate_relocation(one,self.sp,t.content_hash))
        two=self.move(one,2,'third.pdf')
        self.assertTrue(w.validate_relocation(two,self.sp,t.content_hash))
        three=self.move(two,3,'original.pdf')
        self.assertEqual(t.content_hash(three),self.state['qc']['content_sha256'])
        self.assertTrue(w.validate_relocation(three,self.sp,t.content_hash))

    def test_chain_rejects_tampering_missing_snapshot_and_cycle(self):
        one=self.move(self.state,1,'second.pdf');two=self.move(one,2,'third.pdf')
        old=self.history/'before-1.json';original=old.read_bytes()
        old.write_bytes(original+b' ')
        self.assertFalse(w.validate_relocation(two,self.sp,t.content_hash))
        old.unlink()
        self.assertFalse(w.validate_relocation(two,self.sp,t.content_hash))
        old.write_bytes(original)
        two['migration']['previous_state']={'path':'state.json','sha256':w.digest(self.sp)}
        self.assertFalse(w.validate_relocation(two,self.sp,t.content_hash))

    def test_chain_rejects_content_layout_qc_or_pdf_changes(self):
        one=self.move(self.state,1,'second.pdf');two=self.move(one,2,'third.pdf')
        for key,value in [('pages',[{'translation':'changed'}]),('layout',{'body_size_pt':6}),
                          ('qc',{'content_sha256':t.content_hash(two)}),
                          ('output',{'path':'new.pdf','sha256':'c'*64})]:
            changed=copy.deepcopy(two);changed[key]=value
            self.assertFalse(w.validate_relocation(changed,self.sp,t.content_hash),key)
        broken=copy.deepcopy(two);broken['migration']['previous_state']['base_path']='missing-base'
        self.assertFalse(w.validate_relocation(broken,self.sp,t.content_hash))

    def test_legacy_single_snapshot_without_base_path(self):
        original=self.root/'before.json';self.write(original,self.state)
        moved=self.move(self.state,1,'second.pdf')
        moved['migration']['previous_state']={'path':'before.json','sha256':w.digest(original)}
        self.assertTrue(w.validate_relocation(moved,self.sp,t.content_hash))


if __name__ == '__main__': unittest.main()
