"""Verify the build stages, drawing batches and original null navigation."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf as fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject, NullObject, TextStringObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import inplace as ip
from test_workflow import make_font


class BuildPerformance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.pdf'
        self.state = self.root / 'state.json'
        self.font = self.root / 'font.ttf'
        make_font(self.font, True)

    def test_many_glyphs_commit_once_and_report_build_stages(self):
        with fitz.open() as doc:
            p = doc.new_page(width=360, height=180)
            p.insert_text((20, 40), 'Label')
            doc.save(self.source)
        ip.extract(self.source, self.state)
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['layout']['fonts'] = [{
            'name': 'Body', 'source': self.font.name, 'sha256': ip.digest(self.font), 'purpose': 'Fixture',
        }]
        block = state['pages'][0]['blocks'][0]
        text = '中文' * 135
        block.update(method='replace', status='translated', translation=text,
                     font_size=9, allowed_bbox=[10, 15, 350, 170],
                     expansion_reason='Fixture has adjacent blank space')
        ip.write_json(self.state, state)
        images = []
        for garbage in (2, 4):
            events = []
            result = ip.build(self.source, self.state, self.root / f'g{garbage}.pdf',
                              garbage=garbage, state=copy.deepcopy(state), progress=events.append,
                              return_state=True)
            self.assertLess(result['build_metrics']['objects']['mupdf_before_save'], len(text) / 2)
            stages = [event['stage'] for event in events]
            for stage in ('page_composition', 'font_subsetting', 'mupdf_write', 'pypdf_write', 'complete'):
                self.assertIn(stage, stages)
            self.assertEqual(events[-1]['completed_pages'], 1)
            self.assertEqual(result['_state']['pages'][0]['blocks'][0]['translation'], text)
            with fitz.open(result['output']) as out:
                p = out[0]
                chinese = p.get_text(clip=fitz.Rect(360, 0, 720, 180)).replace('\n', '')
                self.assertEqual(chinese, text)
                images.append(p.get_pixmap().samples)
        self.assertEqual(images[0], images[1])

    def test_compact_state_encoding_matches_regular_encoder(self):
        value = {
            'schema_version': 3,
            'layout': {'review_profile': 'practical'},
            'pages': [{'text': '汉字'}, {'text': 'variable α'}],
            'qc': {'evidence': []},
        }
        ip.write_json(self.state, value)
        expected = json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n'
        self.assertEqual(self.state.read_bytes(), expected.encode('utf-8'))

    def test_explicitly_null_actions_are_preserved_without_destination(self):
        writer = PdfWriter()
        writer.add_blank_page(240, 180)
        destination = ArrayObject([NullObject(), NameObject('/XYZ'), NullObject(),
                                   NullObject(), NullObject()])
        writer.add_named_destination_array(TextStringObject('missing'), destination)
        outline = writer.add_outline_item('Missing target', None).get_object()
        outline[NameObject('/Dest')] = TextStringObject('missing')
        for value in (TextStringObject('missing'), destination):
            writer.add_annotation(0, DictionaryObject({
                NameObject('/Subtype'): NameObject('/Link'),
                NameObject('/Rect'): ArrayObject([FloatObject(v) for v in (20, 25, 90, 45)]),
                NameObject('/Border'): ArrayObject([FloatObject(v) for v in (0, 0, 1)]),
                NameObject('/A'): DictionaryObject({
                    NameObject('/S'): NameObject('/GoTo'),
                    NameObject('/D'): value,
                }),
            }))
        writer.write(self.source)
        ip.extract(self.source, self.state, profile='practical')
        state = json.loads(self.state.read_text(encoding='utf-8'))
        state['layout']['fonts'] = [{
            'name': 'Body', 'source': self.font.name, 'sha256': ip.digest(self.font), 'purpose': 'Fixture',
        }]
        result = ip.build(self.source, self.state, self.root / 'practical.pdf',
                          state=copy.deepcopy(state), return_state=True)
        self.assertEqual(result['_state']['pages'][0]['null_links'],
                         [{'source_link': 0}, {'source_link': 1}])
        self.assertEqual(result['_state']['layout']['null_bookmarks'],
                         [{'bookmark': 0, 'title': 'Missing target'}])
        reader = PdfReader(result['output'])
        nav = ip.RawNavigation(reader)
        outline = list(nav.outlines())
        self.assertEqual([(d, item['/Title']) for d, item in outline], [(0, 'Missing target')])
        self.assertEqual(nav.parse(outline[0][1], heading=True), (None, None))
        links = [ref.get_object() for ref in reader.pages[0]['/Annots']]
        self.assertEqual(len(links), 4)
        for link in links:
            self.assertNotIn('/A', link)
            self.assertNotIn('/Dest', link)
            self.assertEqual(link['/Border'], [0, 0, 1])
            self.assertEqual(nav.parse(link, allow_actionless=True), ('null', None))
        state['layout']['review_profile'] = 'strict'
        with self.assertRaisesRegex(ValueError, 'Unknown raw destination page'):
            ip.build(self.source, self.state, self.root / 'strict.pdf', state=state)
        self.assertFalse((self.root / 'strict.pdf').exists())


if __name__ == '__main__':
    unittest.main()
