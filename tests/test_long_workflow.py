"""Long-document handoff and bounded source preflight regressions."""
import json
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import test_pipeline as fixture
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject

pl, ip, pt, wf = fixture.pl, fixture.ip, fixture.pt, fixture.wf


class LongWorkflow(unittest.TestCase):
    setUp = fixture.PracticalPipeline.setUp
    tearDown = fixture.PracticalPipeline.tearDown
    args = fixture.PracticalPipeline.args
    prepared = fixture.PracticalPipeline.prepared
    accepted = fixture.PracticalPipeline.accepted
    observations = fixture.PracticalPipeline.observations

    def test_notes_only_republish_keeps_pdf_and_review(self):
        result = self.accepted()
        state = Path(result['state'])
        original = wf.load(state)['qc']['page_reviews']
        destination = self.root/'published.pdf'
        args = Namespace(state=state, output=destination, overwrite=False)
        first = pl.publish(args)
        pdf_hash = wf.digest(destination)
        notes = self.root/'work'/'delivery-notes.json'
        with patch.object(ip,'build',side_effect=AssertionError('Notes must not cause a build')):
            pl.save(notes,[{'description':'Released issue','status':'open'}])
            with self.assertRaisesRegex(ValueError,'unresolved_issue'):
                pl.publish(args)
            status = pl.verify(Namespace(state=state,previous_state=None))
            self.assertFalse(status['ok'])
            self.assertEqual(status['rendered_pages'],0)
            self.assertEqual(status['review_needed'],[])
            pl.save(notes,[{'description':f'Updated remark {i}','status':'retained','note':'Harmless detail'}
                           for i in range(3)])
            status = pl.verify(Namespace(state=state,previous_state=None))
            self.assertTrue(status['ok'])
            self.assertEqual(status['review_needed'],[])
            self.assertEqual(status['rendered_pages'],0)
            args.overwrite = True
            modified = pl.publish(args)
        self.assertEqual(wf.digest(destination),pdf_hash)
        self.assertEqual(wf.load(state)['qc']['page_reviews'],original)
        self.assertEqual(first['notes'],modified['notes'])
        self.assertIn('Updated remark 2',Path(modified['notes']).read_text(encoding='utf-8'))

    def test_three_packages_validate_and_save_once_or_leave_state_unchanged(self):
        with fixture.fitz.open(self.source) as two_pages:
            two_pages.fullcopy_page(0)
            two_pages.saveIncr()
        state = self.prepared()
        dirs = []
        for page in state['pages']:
            n = page['source_page']
            directory = self.root/f'package-{n}'
            package = pl.package(Namespace(state=self.sp,pages=str(n),out=directory,owner=f'writer-{n}'))
            edits = directory/'edits.json'
            pl.save(edits,{'blocks':[{'page':n,'id':page['blocks'][0]['id'],'translation':'文中'}]})
            pl.apply_edits(Namespace(state=package['state'],edits=edits))
            dirs.append(directory)
        main_before = self.sp.read_bytes()
        args = Namespace(state=self.sp,package=dirs)
        last = dirs[-1]/'package.json'
        original = pl.load(last)
        stale = {**original,'baseline':{'3':'0'*64}}
        stale['id'] = wf.canonical([stale['dependencies'],stale['baseline']])
        pl.save(last,stale)
        with self.assertRaisesRegex(ValueError,'package_baseline_changed') as context:
            pl.import_package(args)
        finding = json.loads(str(context.exception))
        self.assertEqual(Path(finding['package']),dirs[-1].resolve())
        self.assertEqual(finding['detail']['pages'],[3])
        self.assertEqual(self.sp.read_bytes(),main_before)
        pl.save(last,original)
        with patch.object(pt,'check_state',wraps=pt.check_state) as check, patch.object(pl,'save_edits',wraps=pl.save_edits) as write:
            self.assertEqual(pl.import_package(args)['changed_pages'],[1,2,3])
            check.assert_called_once()
            write.assert_called_once()
        self.assertEqual(pl.import_package(args)['state_written_bytes'],0)
        edits = self.root/'later-edits.json'
        pl.save(edits,{'blocks':[{'page':1,'id':state['pages'][0]['blocks'][0]['id'],'translation':'中文'}]})
        pl.apply_edits(self.args(edits=edits))
        later = self.sp.read_bytes()
        with self.assertRaisesRegex(ValueError,'package_baseline_changed'):
            pl.import_package(args)
        self.assertEqual(self.sp.read_bytes(),later)

    def test_review_files_bind_pages_and_register_atomically(self):
        with fixture.fitz.open(self.source) as two_pages:
            two_pages.fullcopy_page(0)
            two_pages.saveIncr()
        self.prepared(pages='2-3')
        built = pl.build(self.args())
        candidate = Path(built['state'])
        verify = pl.verify(Namespace(state=candidate,previous_state=None,review_pages=['2','3']))
        handoff = pl.load(verify['review_handoff'])
        expected = []
        for number, assignment in enumerate(handoff['assignments'],1):
            self.assertEqual(assignment['pages'],[number+1])
            draft = pl.load(assignment['template'])
            draft['reviewer'] = f'fixture reviewer {number}'
            row, = draft['pages']
            self.assertEqual((row['page'],row['output_page']),(number+1,number))
            row.update(decision='pass',evidence=f'Synthetic fixture {number}')
            expected.append(draft)
            pl.save(assignment['observations'],draft)
        paths = [a['observations'] for a in handoff['assignments']]
        before = candidate.read_bytes()
        args = Namespace(state=candidate,observations=paths)
        pl.save(paths[0],expected[1])
        with self.assertRaisesRegex(ValueError,'outside this reviewer file assignment'): pl.review(args)
        self.assertEqual(candidate.read_bytes(),before)
        pl.save(paths[0],expected[0])
        for wrong, message in [
            ({'page':2,'output_page':1},'Duplicate observation'),
            ({'output_page':1},'Candidate page does not match'),
            ({'decision':'repair'},'Repair requires a note'),
        ]:
            bad = {**expected[1],'pages':[{**expected[1]['pages'][0],**wrong}]}
            pl.save(paths[1],bad)
            with self.assertRaisesRegex(ValueError,message): pl.review(args)
            self.assertEqual(candidate.read_bytes(),before)
        pl.save(paths[1],expected[1])
        self.assertTrue(pl.review(args)['ready'])
        self.assertEqual([r['reviewer'] for r in wf.load(candidate)['qc']['page_reviews']],
                         ['fixture reviewer 1','fixture reviewer 2'])

    def test_token_retry_is_local_and_prepare_points_to_nested_object_on_failure(self):
        try:
            from pypdf._configuration import apply_configuration, get_configuration
        except ImportError:
            self.skipTest('This supported pypdf release predates the configurable content-stream limit')
        writer = PdfWriter()
        writer.add_blank_page(240,180)
        page = writer.add_blank_page(240,180)

        def stream(data, form=False):
            obj = DecodedStreamObject()
            obj.set_data(data)
            if form:
                obj[NameObject('/Subtype')] = NameObject('/Form')
                obj[NameObject('/BBox')] = ArrayObject([NumberObject(x) for x in (0,0,100,100)])
            return writer._add_object(obj)

        inner = stream(b'0 0 m 2 2 l S\n'*300, form=True)
        outer = stream(b'/Inner Do', form=True)
        for obj, label, ref in [(page,'/Outer',outer),(outer.get_object(),'/Inner',inner)]:
            obj[NameObject('/Resources')] = DictionaryObject({
                NameObject('/XObject'):DictionaryObject({NameObject(label):ref})})
        page[NameObject('/Contents')] = stream(b'/Outer Do')
        with self.source.open('wb') as out:
            writer.write(out)
        with apply_configuration(stream_parsing_work_maximum_count=100):
            with pt.checked_reader(self.source) as reader:
                self.assertEqual(list(ip.check_content_streams(reader,[1,2])),[])
            self.assertEqual(get_configuration().stream_parsing_work_maximum_count,100)
            with patch.object(ip,'CONTENT_STREAM_RETRY_LIMIT',200), patch.object(ip,'extract') as extract:
                with self.assertRaisesRegex(ValueError,'source_content_preflight') as context:
                    pl.prepare(Namespace(source=self.source,state=self.sp,font=[],overwrite=False,pages='all'))
                extract.assert_not_called()
            self.assertEqual(get_configuration().stream_parsing_work_maximum_count,100)
        finding, = json.loads(str(context.exception))['findings']
        self.assertEqual((finding['page'],finding['code'],finding['token_limit']),(2,'content_stream_limit',200))
        self.assertEqual(finding['object_path'],['/Contents',f'/Outer ({outer.idnum} 0 R)',f'/Inner ({inner.idnum} 0 R)'])
