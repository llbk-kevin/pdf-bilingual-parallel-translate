"""Document naming tests; all artifacts are synthetic."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workflow as w


class Naming(unittest.TestCase):
    def test_explicit_roles(self):
        for fn in (w.document_filename, w.ti_filename):
            with self.assertRaises(TypeError): fn('Title', '标题')
        with self.assertRaises(ValueError): w.document_filename('Title', '标题', role='pdf')
        self.assertEqual(w.document_filename('Title', '标题', role='original'), 'Title_标题.pdf')
        self.assertEqual(w.document_filename('Title', '标题', role='generated-translation'),
                         'Title_标题_双语左右对照翻译.pdf')

    def test_generic_identifiers_keep_official_form(self):
        for identity in ('DOC-012A', 'AB1200', '12345'):
            self.assertTrue(w.document_filename('Title', '标题', identity, role='original').startswith(identity+'_'))
        self.assertTrue(w.ti_filename('Title', '标题', 'SLVA317B', role='original').startswith('slva317b_'))
        with self.assertRaises(ValueError): w.ti_filename('Title', '标题', 'DOC-012A', role='original')

    def test_missing_numbers_and_non_english_titles(self):
        for number in (None, '', ' '):
            self.assertEqual(w.document_filename('日本語の文章', '日文文章', number, role='original'),
                             '日本語の文章_日文文章.pdf')
        self.assertEqual(w.document_filename('中文文章', '中文文章', role='original', source_is_chinese=True), '中文文章.pdf')
        self.assertEqual(w.document_filename(chinese_title='官方中文标题', role='official-chinese'), '官方中文标题.pdf')
        self.assertEqual(w.ti_filename(chinese_title='中文', english_document_id='SNVAA43', role='official-chinese'),
                         'snvaa43_中文.pdf')

    def test_papers_omit_identifiers_and_versions_remain(self):
        self.assertEqual(w.document_filename('Article', '论文', '10.0000/example', paper=True,
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
