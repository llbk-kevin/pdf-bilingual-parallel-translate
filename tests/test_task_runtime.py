"""Process-level lifecycle tests; all commands and data are synthetic."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import task_runtime as tr
import coordination as co
import psutil


class Jobs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.task = Path(self.temp.name)/('中文 task '+'长目录 '*8).rstrip()
        (self.task/'work').mkdir(parents=True)
        self.count = 0
        self.jobs = []

    def tearDown(self):
        for job in self.jobs:
            if (job/'job.json').exists():
                tr.cancel(job)
                try:
                    self.wait(job)
                except AssertionError:
                    pass
        self.temp.cleanup()

    def launch(self, code):
        self.count += 1
        args = self.task/'work'/f'args-{self.count}.json'
        tr.write(args,[sys.executable,'-X','utf8','-c',code])
        job = self.task/'work'/f'job-{self.count}'
        self.jobs.append(job)
        result = tr.start(self.task,job,args)
        return job,result

    def wait(self, job, terminal=True):
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            result = tr.status(job)
            if result['status'] in ('succeeded','failed','cancelled','orphaned','interrupted') if terminal else result['status']=='running':
                return result
            time.sleep(.05)
        self.fail('Job did not reach expected state')

    def test_large_unicode_stdout_is_on_disk_not_in_status(self):
        job,_ = self.launch("import sys; print('中文'); sys.stdout.write('x'*(8*1024*1024))")
        result = self.wait(job)
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(result['exit_code'],0)
        self.assertGreater((job/'stdout.log').stat().st_size,8*1024*1024)
        self.assertLess(len(json.dumps(result)),5000)
        self.assertTrue((job/'stdout.log').read_bytes().startswith('中文'.encode()))
        # Renaming logs on Windows catches leaked supervisor file handles.
        (job/'stdout.log').rename(job/'renamed.log')

    def test_failure_has_bounded_tail_and_start_error_is_saved(self):
        job,_ = self.launch("import sys; sys.stderr.write('E'*100000); sys.exit(7)")
        result = self.wait(job)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['exit_code'],7)
        self.assertEqual(len(result['stderr_tail']),2000)
        args = self.task/'work'/'missing.json'
        tr.write(args,[str(self.task/'missing.exe')])
        job = self.task/'work'/'bad';self.jobs.append(job)
        tr.start(self.task,job,args)
        result = self.wait(job)
        self.assertEqual(result['status'],'failed')
        self.assertTrue(result['error'])

    def test_cancel_and_orphan_recovery_do_not_kill_other_jobs(self):
        other = subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
        self.addCleanup(lambda: other.poll() is None and (other.kill(),other.wait()))
        childfile = self.task/'work'/'child.json'
        job,_ = self.launch(
            "import subprocess,sys,time,json,psutil;from pathlib import Path;"
            "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
            f"Path({str(childfile)!r}).write_text(json.dumps({{'pid':c.pid,'started':psutil.Process(c.pid).create_time()}}));"
            "time.sleep(60)")
        running = self.wait(job,False)
        deadline = time.monotonic()+5
        while not childfile.exists() and time.monotonic()<deadline:
            time.sleep(.05)
        descendant = tr.read(childfile)
        tr.cancel(job)
        self.assertEqual(self.wait(job)['status'],'cancelled')
        self.assertIsNone(tr.same_process(running['worker']))
        self.assertIsNone(tr.same_process(descendant))
        self.assertIsNone(other.poll())
        job,_ = self.launch("import time; time.sleep(60)")
        running = self.wait(job,False)
        supervisor = tr.same_process(running['supervisor'])
        supervisor.kill();supervisor.wait(timeout=5)
        deadline = time.monotonic()+5
        while tr.status(job)['status'] != 'orphaned' and time.monotonic()<deadline:
            time.sleep(.05)
        self.assertEqual(tr.status(job)['status'],'orphaned')
        tr.cancel(job)
        self.assertEqual(tr.status(job)['status'],'cancelled')
        self.assertIsNone(tr.same_process(running['worker']))
        self.assertIsNone(other.poll())

    def test_pid_reuse_never_terminates_a_different_identity(self):
        proc = subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(),proc.wait()))
        record = tr.identity(proc.pid)
        record['started'] -= 10
        self.assertEqual(tr.terminate_tree(record),[])
        self.assertIsNone(proc.poll())

    def test_paths_and_overwrite_are_rejected(self):
        args = self.task/'work'/'args.json'
        tr.write(args,[sys.executable,'-c','pass'])
        with self.assertRaises(ValueError):
            tr.start(self.task,self.task.parent/'outside',args)
        job,_ = self.launch('pass')
        self.wait(job)
        with self.assertRaises(FileExistsError):
            tr.start(self.task,job,args)
        tr.write(args,'not an argument array')
        with self.assertRaises(ValueError):
            tr.start(self.task,self.task/'work'/'invalid',args)


class SessionLifecycle(unittest.TestCase):
    def test_register_verify_reset_and_resume_with_new_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);(root/'work').mkdir()
            fake = SimpleNamespace(pid=123,cmdline=lambda:['node','/tool/kernel.js','--session-id','fixture'],
                                   create_time=lambda:42.,memory_info=lambda:SimpleNamespace(rss=100))
            result = co.register_session(root,'/root/fixture',fake)
            checkpoint = root/'work'/'checkpoint.json';checkpoint.write_text('{}')
            co.mark_session(result['record'],'cleanup_required',checkpoint)
            with patch.object(co.psutil,'Process',side_effect=psutil.NoSuchProcess(123)),patch.object(co.psutil,'process_iter',return_value=[]):
                observed = co.session_status(root)
            self.assertEqual(observed['sessions'][0]['status'],'reset_observed')
            fake.pid=124
            newer = co.register_session(root,'/root/fixture',fake)
            self.assertNotEqual(newer['record'],result['record'])
            self.assertEqual(newer['status'],'running')
            co.mark_session(newer['record'],'cleanup_unavailable',checkpoint)

    def test_unverified_caller_and_missing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = SimpleNamespace(pid=123,cmdline=lambda:['unrelated'],name=lambda:'node',parent=lambda:None)
            with self.assertRaisesRegex(ValueError,'unverified_tool_caller'):
                co.register_session(temp,'fixture',fake)

    def test_dynamic_memory_queue_and_override(self):
        memory = SimpleNamespace(total=32*1024**3, available=int(2.5*1024**3))
        task = {'id':'a','status':'queued','phase':'translate','depends_on':[]}
        self.assertEqual(co.ready_tasks([task],64,memory),[])
        self.assertEqual(co.ready_tasks([task],64,memory,reserve_bytes=2*1024**3),[task])
        self.assertGreaterEqual(co.memory_status(snapshot=memory)['reserve_bytes'],2*1024**3)


if __name__=='__main__':
    unittest.main()
