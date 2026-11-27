"""Behavioral tests for confirmed work plans and explicit model dispatch."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import coordination as co


def task(identifier, phase, pages, dependencies=(), document='d01'):
    return {'id':identifier, 'name':identifier.replace('_',' | '), 'document':document,
            'pages':pages, 'phase':phase, 'owns_edits':phase != 'review',
            'model':'gpt-6-luna', 'reasoning_effort':'xhigh', 'fork_turns':'none',
            'responsibilities':'Translate and merge' if phase != 'review' else 'Independent review',
            'handoff':'work/'+identifier, 'depends_on':list(dependencies), 'status':'queued'}


def plan():
    return {'documents':[{'id':'d01','pages':[1,2],'state_writer':'d01_translate'}],
            'tasks':[task('d01_translate','translate',[1,2]),
                     task('d01_review','review',[1,2],['d01_translate'])], 'launches':[]}


class WorkPlans(unittest.TestCase):
    def test_record_events_are_idempotent_atomic_and_keep_model_identity(self):
        with tempfile.TemporaryDirectory() as root:
            ledger=Path(root)/'台账 空格.json';co.write(ledger,plan())
            event={'id':'launch-1','type':'launch','task':'d01_translate','agent_id':'original',
                   'requested_model':'gpt-6-luna','requested_effort':'xhigh'}
            self.assertEqual(co.record_event(ledger,event)['summary']['created_agents'],1)
            original=ledger.read_bytes()
            self.assertTrue(co.record_event(ledger,event)['replayed'])
            self.assertEqual(ledger.read_bytes(),original)
            with self.assertRaisesRegex(ValueError,'different content'):co.record_event(ledger,{**event,'requested_effort':'high'})
            resumed=co.record_event(ledger,{'id':'resume-1','type':'resume','task':'d01_translate','agent_id':'original'})
            self.assertEqual((resumed['summary']['created_agents'],resumed['summary']['resume_count']),(1,1))
            original=ledger.read_bytes()
            with self.assertRaises(ValueError):co.record_event(ledger,{'id':'wrong','type':'status','task':'d01_translate','status':'lost'})
            self.assertEqual(ledger.read_bytes(),original)
            checked=co.record_event(ledger,{'id':'model-1','type':'model-evidence','task':'d01_translate',
                'agent_id':'original','actual_model':'gpt-6-luna','actual_effort':'xhigh','evidence':'host-record','evidence_agent_id':'original'})
            self.assertEqual(checked['models'][0]['status'],'verified')
            with self.assertRaises(ValueError):co.record_event(ledger,{'id':'review-launch','type':'launch',
                'task':'d01_review','agent_id':'original','requested_model':'gpt-6-luna','requested_effort':'xhigh'})
            result=co.record_event(ledger,{'id':'finish','type':'status','task':'d01_translate','status':'completed',
                                           'artifacts':{'candidate':'work/candidate.pdf'}})
            self.assertEqual(result['summary']['running_agents'],0)

    def assert_invalid(self, value, text):
        result=co.validate_plan(value)
        self.assertFalse(result['ok'], result)
        self.assertIn(text, '\n'.join(result['errors']))

    def test_short_and_multiple_documents_have_independent_coverage(self):
        value=plan(); self.assertTrue(co.validate_plan(value)['ok'])
        second=copy.deepcopy(value)
        for doc in second['documents']:
            doc.update(id='d02',state_writer='d02_translate')
        second['tasks']=[task('d02_translate','translate',[1,2],document='d02'),
                         task('d02_review','review',[1,2],['d02_translate'],'d02')]
        value['documents']+=second['documents'];value['tasks']+=second['tasks']
        self.assertTrue(co.validate_plan(value)['ok'])
        value['tasks'][-1]['pages']=[1]
        self.assert_invalid(value,'incomplete independent review coverage')

    def test_split_document_writer_is_not_a_second_editing_owner(self):
        value=plan(); value['tasks'][0].update(owns_edits=False,depends_on=['part_a','part_b'])
        value['tasks'] += [task('part_a','translate',[1]),task('part_b','translate',[2])]
        self.assertTrue(co.validate_plan(value)['ok'])
        value['tasks'][0]['owns_edits']=True
        self.assert_invalid(value,'overlapping editing ownership')

    def test_first_page_worker_freezes_terra_writer_even_with_one_slot(self):
        for writer_translates in (True, False):
            with self.subTest(writer_translates=writer_translates), tempfile.TemporaryDirectory() as temp:
                ledger = Path(temp) / 'plan.json'
                value = plan()
                writer, reviewer = value['tasks']
                writer.update(model='gpt-6.1-terra', reasoning_effort='high', owns_edits=writer_translates)
                writer['pages'] = [1] if writer_translates else [1, 2]
                value['tasks'].append(task('other', 'translate', [2]))
                reviewer['depends_on'].append('other')
                if not writer_translates:
                    value['tasks'].append(task('first', 'translate', [1]))
                    writer['depends_on'] = ['first', 'other']
                co.write(ledger, value)
                event = {'type':'launch', 'id':'first-launch', 'task':'other', 'agent_id':'a',
                         'requested_model':'gpt-6-luna', 'requested_effort':'xhigh'}
                summary = co.record_event(ledger, event)['summary']
                extra = int(not writer_translates)
                self.assertEqual(summary['staffing_by_document']['d01'],
                                 {'translators':2, 'reviewers':1, 'merge_only':extra, 'total':3 + extra})
                self.assertEqual(summary['running_agents'], 1)
                saved = json.loads(ledger.read_text(encoding='utf-8'))
                self.assertEqual(saved['launches'][0]['initial_writer'],
                                 {'id':writer['id'], 'document':'d01', 'model':'gpt-6.1-terra',
                                  'reasoning_effort':'high'})
                self.assertTrue(co.validate_plan(saved)['ok'])
                for change in ('state_writer', 'model', 'reasoning_effort'):
                    bad = copy.deepcopy(saved)
                    if change == 'state_writer':
                        bad['documents'][0][change] = 'other'
                    else:
                        bad['tasks'][0][change] = 'changed'
                    self.assert_invalid(bad, 'differs from first dispatch')

    def test_failed_launch_does_not_freeze_writer_and_explicit_choice_is_kept(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / 'plan.json'
            value = plan()
            value['tasks'][0].update(model='gpt-6.1-terra', reasoning_effort='high')
            co.write(ledger, value)
            before = ledger.read_bytes()
            event = {'type':'launch', 'id':'lead', 'task':'d01_translate', 'agent_id':'lead',
                     'requested_model':'gpt-6-luna', 'requested_effort':'xhigh'}
            with self.assertRaisesRegex(ValueError, 'differs from confirmed task'):
                co.record_event(ledger, event)
            self.assertEqual(ledger.read_bytes(), before)
            result = co.record_event(ledger, dict(event, requested_model='gpt-6.1-terra',
                                                 requested_effort='high'))
            self.assertTrue(result['ok'])
            saved = json.loads(ledger.read_text(encoding='utf-8'))
            self.assertEqual(saved['launches'][0]['initial_writer']['model'], 'gpt-6.1-terra')

    def test_single_translator_keeps_writer_assignment_when_help_arrives(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / 'plan.json'
            co.write(ledger, plan())
            first = {'type':'launch', 'id':'lead', 'task':'d01_translate', 'agent_id':'lead',
                     'requested_model':'gpt-6-luna', 'requested_effort':'xhigh'}
            co.record_event(ledger, first)
            saved = json.loads(ledger.read_text(encoding='utf-8'))
            initial = copy.deepcopy(saved['launches'][0]['initial_writer'])
            saved['tasks'][0]['pages'] = [1]
            saved['tasks'].append(task('helper', 'translate', [2]))
            saved['tasks'][1]['depends_on'].append('helper')
            co.write(ledger, saved)
            result = co.record_event(ledger, dict(first, id='second', task='helper', agent_id='helper'))
            self.assertTrue(result['ok'])
            self.assertEqual(result['summary']['staffing_by_document']['d01'],
                             {'translators':2, 'reviewers':1, 'merge_only':0, 'total':3})
            launches = json.loads(ledger.read_text(encoding='utf-8'))['launches']
            self.assertEqual(launches[0]['initial_writer'], initial)
            self.assertNotIn('initial_writer', launches[1])

    def test_names_models_context_dependencies_and_page_bounds(self):
        for mutate, error in [
            (lambda p:p['tasks'][1].update(id='d01_translate'),'Task IDs'),
            (lambda p:p['tasks'][1].update(name=p['tasks'][0]['name']),'display name'),
            (lambda p:p['tasks'][0].pop('model'),'missing model'),
            (lambda p:p['tasks'][0].pop('reasoning_effort'),'missing reasoning_effort'),
            (lambda p:p['tasks'][1].update(fork_turns='all'),'fresh context'),
            (lambda p:p['tasks'][1].update(depends_on=['missing']),'unknown dependency'),
            (lambda p:p['tasks'][0].update(depends_on=['d01_review']),'dependency cycle'),
            (lambda p:p['tasks'][1].update(depends_on=[]),'missing dependency'),
            (lambda p:p['tasks'][0].update(pages=[1,3]),'outside document'),
        ]:
            with self.subTest(error=error):
                value=plan();mutate(value);self.assert_invalid(value,error)

    def test_translation_and_review_identities_cannot_be_shared(self):
        value=plan()
        for t in value['tasks']:t['agent_id']='same'
        self.assert_invalid(value,'also translated/repaired')
        value['tasks'][0]['agent_id']='new-editor'
        value['launches']=[{'task':'d01_translate','agent_id':'same',
                            'requested_model':'gpt-6-luna','requested_effort':'xhigh'}]
        self.assert_invalid(value,'historical translation identity')

    def test_original_worker_resume_is_not_another_created_agent(self):
        value=plan();value['tasks'][0].update(agent_id='original',status='running',resume_count=2)
        value['launches']=[{'task':'d01_translate','agent_id':'original',
                            'requested_model':'gpt-6-luna','requested_effort':'xhigh'}]
        result=co.validate_plan(value)
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['models'][0]['status'],'unverified')
        self.assertEqual(result['summary'],{'created_agents':1,'work_agents':1,'probe_agents':0,'running_agents':1,'queued_tasks':1,
                                            'blocked_tasks':0,'resume_count':2,
                                            'staffing_by_document':{'d01':{'translators':1,'reviewers':1,'merge_only':0,'total':2}}})
        value['model_checks']=[{'agent_id':'probe','model':'gpt-6-luna'}]
        summary=co.validate_plan(value)['summary']
        self.assertEqual((summary['created_agents'],summary['work_agents'],summary['probe_agents']),(2,1,1))
        value['launches']*=2
        self.assert_invalid(value,'duplicate launch')

    def test_review_waits_for_pending_repair_before_recheck(self):
        value=plan();value['tasks'][0]['status']='completed'
        value['tasks'].append(task('repair_p1','repair',[1],['d01_translate']))
        self.assert_invalid(value,'missing dependency on pending repair')
        value['tasks'][1]['depends_on']=['repair_p1']
        self.assertTrue(co.validate_plan(value)['ok'])

    def test_model_evidence_never_silently_substitutes(self):
        self.assertEqual(co.check_model_result('luna','xhigh')['status'],'unverified')
        self.assertEqual(co.check_model_result('luna','xhigh',error='tool rejected model')['status'],'failed')
        self.assertEqual(co.check_model_result('luna','xhigh',actual_model='terra')['status'],'mismatch')
        self.assertEqual(co.check_model_result('luna','xhigh',actual_model='luna',actual_effort='xhigh')['status'],'unverified')
        self.assertEqual(co.check_model_result('luna','xhigh',actual_model='luna',actual_effort='xhigh',
                         evidence='host log',agent_id='worker',evidence_agent_id='worker')['status'],'verified')
        # A stale/static catalog is deliberately not an authority for actual capability.
        verified=plan();verified['available_models']=['gpt-6.1-terra']
        verified['launches']=[{'task':'d01_translate','agent_id':'luna-agent',
            'requested_model':'gpt-6-luna','requested_effort':'xhigh',
            'actual_model':'gpt-6-luna','actual_effort':'xhigh','evidence':'host turn context',
            'evidence_agent_id':'luna-agent'}]
        self.assertEqual(co.validate_plan(verified)['models'][0]['status'],'verified')
        self.assertTrue(co.validate_plan(verified)['ok'])
        value=plan();value['launches']=[{'task':'d01_translate','agent_id':'actual',
                  'requested_model':'terra','requested_effort':'high','actual_model':'terra','actual_effort':'high'}]
        self.assert_invalid(value,'no automatic substitution')
        self.assert_invalid(value,'differs from confirmed task')

    def test_probe_evidence_does_not_verify_a_different_work_agent(self):
        for evidence_id in (None,'probe'):
            result=co.check_model_result('luna','xhigh',actual_model='luna',actual_effort='xhigh',
                     evidence='successful probe host record',agent_id='worker',evidence_agent_id=evidence_id)
            self.assertEqual(result['status'],'unverified')

    def test_cli_is_read_only_and_rejects_invalid_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'计划 with spaces.json'
            path.write_text(json.dumps(plan(),ensure_ascii=False),encoding='utf-8')
            before=path.read_bytes()
            command=[sys.executable,str(Path(co.__file__)),'validate-plan','--plan',str(path)]
            result=subprocess.run(command,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['ok'])
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(list(Path(temp).iterdir()),[path])
            path.write_text('{"tasks":[]}',encoding='utf-8')
            result=subprocess.run(command,capture_output=True,encoding='utf-8')
            self.assertEqual(result.returncode,1)
            self.assertFalse(json.loads(result.stdout)['ok'])

    def test_memory_reserve_floor_override_and_lightweight_progress(self):
        gib=1024**3
        memory=SimpleNamespace(total=32*gib,available=4*gib)
        self.assertEqual(co.memory_status(snapshot=memory)['reserve_bytes'],int(3.2*gib))
        self.assertEqual(co.memory_status(snapshot=SimpleNamespace(total=8*gib,available=4*gib))['reserve_bytes'],2*gib)
        self.assertEqual(co.memory_status(reserve_bytes=gib,snapshot=memory)['reserve_bytes'],gib)
        tasks=[task('heavy','translate',[1]),task('light','translate',[2])]
        tasks[1]['resource_class']='light'
        memory.available=gib
        self.assertEqual(co.ready_tasks(tasks,2,memory),[tasks[1]])
        self.assertEqual(co.ready_tasks(tasks,0,memory),[])
        with patch.object(co.psutil,'virtual_memory',side_effect=AssertionError('must not inspect memory')):
            self.assertEqual(co.ready_tasks(tasks,2,check_memory=False),tasks)


if __name__=='__main__':
    unittest.main()
