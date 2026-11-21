"""Exercise actual painted references, including skipped or ambiguous Form calls."""
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           NameObject, NumberObject)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import vector_forms as vf


def name(value):
    return NameObject('/' + value)


def numbers(values):
    return ArrayObject(NumberObject(v) for v in values)


def stream(data):
    result = DecodedStreamObject()
    result.set_data(data)
    return result


def form(writer, data, children=None):
    obj = stream(data)
    obj[name('Type')] = name('XObject')
    obj[name('Subtype')] = name('Form')
    obj[name('BBox')] = numbers([0,0,100,100])
    resources = DictionaryObject()
    if children:
        resources[name('XObject')] = DictionaryObject(children)
    obj[name('Resources')] = resources
    return writer._add_object(obj)


class VectorForms(unittest.TestCase):
    def test_only_self_contained_paths(self):
        w = PdfWriter()
        path = form(w,b'0 g 0 0 10 20 re f')
        text = form(w,b'BT 3 Tr (hidden) Tj ET')
        for child in (path,text):
            nested = form(w,b'/Child Do',{name('Child'):child})
            self.assertEqual(vf.leaf_reason(nested.get_object(), w),'resource_dependencies')
        self.assertEqual(vf.leaf_reason(text.get_object(),w),'non_path_operators')
        self.assertIsNone(vf.leaf_reason(path.get_object(),w))
        for key in ('Group','OC'):
            obj = form(w,b'0 0 m n').get_object()
            obj[name(key)] = DictionaryObject()
            self.assertEqual(vf.leaf_reason(obj,w),'form_dictionary')

    def test_marker_survives_real_redaction_and_size_filter(self):
        from unittest.mock import patch
        writer = PdfWriter()
        page = writer.add_blank_page(100,100)
        leaf = form(writer,b'0 g 0 0 20 20 re f')
        page[name('Resources')] = DictionaryObject({
            name('XObject'): DictionaryObject({name('Draw'):leaf})})
        page[name('Contents')] = writer._add_object(stream(b'/Draw Do'))
        data = io.BytesIO()
        writer.write(data)
        with pymupdf.open(stream=data.getvalue(),filetype='pdf') as source:
            source[0].insert_text((10,50),'Delete')
            raw = source.tobytes()
        with pymupdf.open(stream=raw,filetype='pdf') as src, pymupdf.open() as out:
            from pypdf import PdfReader
            with PdfReader(io.BytesIO(raw)) as reader:
                share = vf.VectorSharing()
                share.mark(src,reader,src[0],1)
                self.assertFalse(share.pages)
                share = vf.VectorSharing()
                with patch.object(vf,'MIN_BYTES',1):
                    share.mark(src,reader,src[0],1)
                self.assertEqual(len(share.pages[1]),1)
                right = out.new_page(width=200,height=100)
                right.show_pdf_page(pymupdf.Rect(100,0,200,100),src,0)
                right.add_redact_annot(right.search_for('Delete')[0],fill=False)
                right.apply_redactions(images=0,graphics=0,text=0)
                right.show_pdf_page(pymupdf.Rect(0,0,100,100),src,0,overlay=False)
                self.assertEqual(len(right.search_for('Delete')),1)
                refs = [x for x,_,_,_ in right.get_xobjects()
                        if out.xref_get_key(x,share.key)[0]=='int']
                self.assertEqual(len(set(refs)),2)

    def exercise(self, variant):
        w = PdfWriter()
        shared = vf.VectorSharing()
        colors = [b'1 0 0 rg', b'0 1 0 rg']
        original = []
        rewritten = []
        from hashlib import sha256
        for index, color in enumerate(colors, 1):
            path = color + b' 0 0 10 20 re f'
            original.append(form(w,path))
            rewritten.append(form(w,b'q '+path+b' Q'))
            shared.eligible[index] = sha256(path).digest()
            for ref in (original[-1],rewritten[-1]):
                ref.get_object()[name(shared.key)] = NumberObject(index)
        if variant == 'missing':
            del rewritten[0].get_object()[name(shared.key)]
        for number in (1,2):
            page = w.add_blank_page(200,100)
            wrappers = []
            for side, leaves in enumerate((original,rewritten)):
                ops = b'/A Do /B Do'
                if side and number == 2:
                    if variant == 'clip':
                        ops = b'0 0 10 10 re W n '+ops
                    if variant == 'matrix':
                        ops = b'2 0 0 1 0 0 cm '+ops
                    if variant == 'order':
                        ops = b'/B Do /A Do'
                inner = form(w,ops,dict(zip((name('A'),name('B')),leaves)))
                outer = form(w,b'/Page Do',{name('Page'):inner})
                outer.get_object()[name('Matrix')] = numbers([1,0,0,1,side*100,0])
                wrappers.append(outer)
            page[name('Resources')] = DictionaryObject({name('XObject'):DictionaryObject(
                dict(zip((name('L'), name('R')), wrappers)))})
            page[name('Contents')] = w._add_object(stream(b'q /L Do Q q /R Do Q'))
            shared.pages[number] = {1,2}
        def rendered(data):
            with pymupdf.open(stream=data,filetype='pdf') as doc:
                return [p.get_pixmap().samples for p in doc]
        before = io.BytesIO()
        w.write(before)
        shared.apply(w,[1,2])
        w.compress_identical_objects()
        with TemporaryDirectory() as tmp:
            out = Path(tmp)/'test.pdf'
            w.write(out)
            self.assertNotIn(shared.key.encode(),out.read_bytes())
            self.assertEqual(rendered(before.getvalue()),rendered(out.read_bytes()))
            result = shared.report(out,[1,2])
        return result

    def test_same_source_shared_across_pages(self):
        result = self.exercise('ordinary')
        self.assertEqual(result['shared_objects'],2)
        self.assertEqual(len(result['paint_paths']),4)
        self.assertNotEqual(result['paint_paths'][0]['final_object'],
                            result['paint_paths'][1]['final_object'])

    def test_missing_marker_and_mismatched_placements(self):
        self.assertFalse(self.exercise('missing')['paint_paths'])
        for variant in ('matrix','clip','order'):
            with self.subTest(variant=variant):
                result = self.exercise(variant)
                self.assertEqual([r['source_page'] for r in result['paint_paths']],[1,1])
