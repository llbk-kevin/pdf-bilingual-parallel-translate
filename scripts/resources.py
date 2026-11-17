"""Machine-wide admission for independent PDF extraction and rendering processes."""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid

import psutil

MIB = 1024 ** 2


def worker_request(value):
    if value == 'auto':
        return value
    if isinstance(value, bool):
        raise ValueError('workers must be auto or a positive integer')
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise ValueError('workers must be auto or a positive integer') from None
    if number < 1 or str(number) != str(value):
        raise ValueError('workers must be auto or a positive integer')
    return number


def usable_cpus():
    process = psutil.Process()
    if hasattr(process, 'cpu_affinity'):
        return max(1, len(process.cpu_affinity()))
    return max(1, os.cpu_count() or 1)


def peak_memory():
    info = psutil.Process().memory_info()
    if os.name == 'nt':
        return info.peak_wset
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if __import__('sys').platform == 'darwin' else peak * 1024


def registry_path():
    user = hashlib.sha256(psutil.Process().username().encode('utf-8')).hexdigest()[:16]
    return Path(tempfile.gettempdir())/'pdf-bilingual-resources'/user/'workers.sqlite3'


def alive(pid, started):
    try:
        process = psutil.Process(pid)
        return abs(process.create_time()-started) < .01 and process.is_running()
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


@contextmanager
def registry(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    try:
        with connection:
            connection.execute('CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, pid INTEGER, started REAL, cpu INTEGER, memory INTEGER)')
            connection.execute('CREATE TABLE IF NOT EXISTS children (lease TEXT, pid INTEGER, started REAL, PRIMARY KEY(lease,pid))')
            connection.commit()
            connection.execute('BEGIN IMMEDIATE')
            yield connection
    
    finally:
        connection.close()

def cleanup(connection):
    for lease, pid, started in connection.execute('SELECT id,pid,started FROM leases').fetchall():
        if alive(pid, started):
            continue
        children = connection.execute('SELECT pid,started FROM children WHERE lease=?', (lease,)).fetchall()
        remaining = False
        for child, created in children:
            if alive(child, created):
                # These read-only workers belong to a terminated coordinator.
                try:
                    psutil.Process(child).terminate()
                    remaining = True
                except psutil.NoSuchProcess:
                    pass
        if not remaining:
            connection.execute('DELETE FROM children WHERE lease=?', (lease,))
            connection.execute('DELETE FROM leases WHERE id=?', (lease,))


def register_worker(database, lease):
    process = psutil.Process()
    with registry(database) as connection:
        if not connection.execute('SELECT 1 FROM leases WHERE id=?', (lease,)).fetchone():
            raise RuntimeError('PDF worker lease is unavailable')
        connection.execute('INSERT INTO children VALUES (?,?,?)', (lease, process.pid, process.create_time()))


class WorkerBudget:
    def __init__(self, requested, pages, bytes_per_worker, phase, database=None, parallel_hint=None):
        self.requested = worker_request(requested)
        self.pages = pages
        self.bytes_per_worker = max(64*MIB, math.ceil(bytes_per_worker * 1.5))
        self.phase = phase
        self.parallel_hint = parallel_hint
        self.database = Path(database) if database else registry_path()
        self.id = uuid.uuid4().hex
        self.started = time.perf_counter()
        self.cpu_seconds = 0.
        self.peak_bytes = 0
        self.workers = 0

    def __enter__(self):
        if self.pages < 1:
            raise ValueError('PDF budget requires at least one page')
        process = psutil.Process()
        while True:
            with registry(self.database) as connection:
                cleanup(connection)
                used_cpu, reserved = connection.execute(
                    'SELECT COALESCE(SUM(cpu),0),COALESCE(SUM(memory),0) FROM leases').fetchone()
                cpu = max(0, usable_cpus()-used_cpu)
                available = psutil.virtual_memory().available
                memory = max(0, int(available*.75)-reserved)
                requested = min(self.pages, self.parallel_hint or self.pages) if self.requested == 'auto' else self.requested
                count = min(requested, self.pages, cpu, memory//self.bytes_per_worker)
                if count:
                    connection.execute('INSERT INTO leases VALUES (?,?,?,?,?)',
                                       (self.id, process.pid, process.create_time(), count, count*self.bytes_per_worker))
                    self.workers = count
                    self.selection = {'available_cpu_slots':cpu, 'memory_budget_bytes':memory,
                                      'estimated_worker_bytes':self.bytes_per_worker, 'parallel_hint':self.parallel_hint}
                    break
                if not used_cpu and memory < self.bytes_per_worker:
                    raise MemoryError(json.dumps({
                        'code':'insufficient_worker_memory', 'phase':self.phase,
                        'available_bytes':available, 'headroom_bytes':available-int(available*.75),
                        'reserved_bytes':reserved, 'memory_budget_bytes':memory,
                        'estimated_worker_bytes':self.bytes_per_worker,
                        'coordinator_rss_bytes':process.memory_info().rss,
                        'action':'Free verified idle tool sessions or wait for available memory; do not retry unchanged inputs.'
                    }))
            time.sleep(.5)
        self.wait_seconds = time.perf_counter()-self.started
        return self

    def record(self, result):
        self.cpu_seconds += result.get('worker_cpu_seconds', 0.)
        self.peak_bytes = max(self.peak_bytes, result.get('worker_peak_bytes', 0))

    def report(self):
        return {'phase':self.phase, 'requested':self.requested, 'workers':self.workers,
                'selection':self.selection, 'wait_seconds':round(self.wait_seconds,3),
                'wall_seconds':round(time.perf_counter()-self.started,3),
                'worker_cpu_seconds':round(self.cpu_seconds,3), 'worker_peak_bytes':self.peak_bytes}

    def __exit__(self, *exc):
        with registry(self.database) as connection:
            connection.execute('DELETE FROM children WHERE lease=?', (self.id,))
            connection.execute('DELETE FROM leases WHERE id=?', (self.id,))
