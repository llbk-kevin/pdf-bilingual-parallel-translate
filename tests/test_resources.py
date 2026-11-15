"""Regression cases for shared resource admission and dynamic PDF handoffs."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import resources as rs
import coordination as co


class Resources(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.db=self.root/'budget.sqlite3'

    def test_worker_request(self):
        self.assertEqual(rs.worker_request('auto'),'auto')
        self.assertEqual(rs.worker_request('12'),12)
        for value in (0,-1,'1.5',True,'unlimited'):
            with self.assertRaises(ValueError):rs.worker_request(value)

    def test_cpu_memory_and_small_task_bound_actual_count(self):
        with patch.object(rs,'usable_cpus',return_value=8),patch.object(rs.psutil,'virtual_memory',return_value=SimpleNamespace(available=16*1024**3)):
            with rs.WorkerBudget('auto',20,64*rs.MIB,'test',self.db) as budget:
                self.assertEqual(budget.workers,8)
            with rs.WorkerBudget('auto',1,64*rs.MIB,'test',self.db) as budget:
                self.assertEqual(budget.workers,1)
            with rs.WorkerBudget('auto',20,64*rs.MIB,'test',self.db,parallel_hint=1) as budget:
                self.assertEqual(budget.workers,1)
        with patch.object(rs,'usable_cpus',return_value=1),patch.object(rs.psutil,'virtual_memory',return_value=SimpleNamespace(available=16*1024**3)):
            with rs.WorkerBudget(12,20,64*rs.MIB,'test',self.db) as budget:self.assertEqual(budget.workers,1)
        with patch.object(rs.psutil,'virtual_memory',return_value=SimpleNamespace(available=32*rs.MIB)):
            with self.assertRaises(MemoryError):
                with rs.WorkerBudget('auto',2,64*rs.MIB,'test',self.db):pass

    def test_shared_budget_waits_then_releases_on_failure(self):
        done=threading.Event();result=[]
        def waiting():
            with rs.WorkerBudget(1,1,64*rs.MIB,'second',self.db) as budget:
                result.append(budget.workers)
            done.set()
        with patch.object(rs,'usable_cpus',return_value=1),patch.object(rs.psutil,'virtual_memory',return_value=SimpleNamespace(available=8*1024**3)):
            with self.assertRaisesRegex(RuntimeError,'fixture'):
                with rs.WorkerBudget('auto',10,64*rs.MIB,'first',self.db):
                    worker=threading.Thread(target=waiting);worker.start()
                    self.assertFalse(done.wait(.1))
                    raise RuntimeError('fixture')
            self.assertTrue(done.wait(5));worker.join()
        self.assertEqual(result,[1])
        with rs.registry(self.db) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM leases').fetchone()[0],0)

    def test_dead_owner_and_reused_pid_are_cleaned(self):
        process=rs.psutil.Process()
        with rs.registry(self.db) as db:
            db.execute('INSERT INTO leases VALUES (?,?,?,?,?)',('dead',2147483647,0,99,999999))
            db.execute('INSERT INTO leases VALUES (?,?,?,?,?)',('reused',process.pid,0,99,999999))
        with rs.WorkerBudget(1,1,64*rs.MIB,'new',self.db):pass
        with rs.registry(self.db) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM leases').fetchone()[0],0)

    def test_registry_rolls_back_and_closes_after_exception(self):
        with self.assertRaises(RuntimeError):
            with rs.registry(self.db) as db:
                db.execute('INSERT INTO leases VALUES (?,?,?,?,?)',('rollback',1,0,1,1))
                raise RuntimeError()
        with rs.registry(self.db) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM leases').fetchone()[0],0)


class Coordination(unittest.TestCase):
    def test_host_probe_is_read_only_and_reports_unconfigured_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'config.toml'
            self.assertTrue(co.host_settings(config)['capacity_choice_needed'])
            config.write_text('[agents]\nmax_concurrent_threads_per_session = 64\n',encoding='utf-8')
            original=config.read_bytes()
            self.assertEqual(co.host_settings(config)['configured_capacity'],64)
            self.assertEqual(config.read_bytes(),original)
            config.write_text('[agents]\nenabled = false\n',encoding='utf-8')
            self.assertFalse(co.host_settings(config)['enabled'])

    def test_ready_queue_has_no_role_quota_and_resumes_after_completion(self):
        tasks=[]
        for document in ('a','b','c'):
            tasks.extend([{'id':document+'-t','document':document,'phase':'translate','status':'queued','depends_on':[]},
                          {'id':document+'-r','document':document,'phase':'review','status':'queued','depends_on':[document+'-t']}])
        self.assertEqual(len(co.ready_tasks(tasks,20)),3)
        self.assertEqual(len(co.ready_tasks(tasks,1)),1)
        self.assertEqual(co.ready_tasks(tasks,0),[])
        tasks[0].update(status='completed',agent_id='translator-a')
        self.assertEqual(co.ready_tasks(tasks,1)[0]['id'],'a-r')
        tasks[1].update(status='completed',agent_id='new-reviewer-a')
        tasks[2].update(status='running',agent_id='lost-agent-b')
        tasks[2].update(status='queued',agent_id=None)
        self.assertEqual(co.ready_tasks(tasks,1)[0]['id'],'b-t')
        tasks[2]['status']='complete'
        with self.assertRaisesRegex(ValueError,'Invalid coordination status'):co.ready_tasks(tasks,1)
        for task in tasks:task['status']='completed'
        self.assertEqual(co.ready_tasks(tasks,20),[])


if __name__=='__main__':unittest.main()
