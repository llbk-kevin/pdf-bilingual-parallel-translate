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
                                            'blocked_tasks':0,'resume_count':2})
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
