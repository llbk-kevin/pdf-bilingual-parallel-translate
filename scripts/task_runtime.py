#!/usr/bin/env python3
"""File-backed supervisor for frozen PDF commands."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import uuid

import psutil


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def identity(pid):
    proc = psutil.Process(pid)
    return {'pid': proc.pid, 'started': proc.create_time()}


def same_process(record):
    if not record:
        return None
    try:
        proc = psutil.Process(record['pid'])
        if abs(proc.create_time() - record['started']) < .01 and proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            return proc
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return None


def inside(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Job paths must stay within the task work directory')
    return path


def tail(path, limit=2000):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size-limit))
            return stream.read(limit).decode('utf-8', errors='replace')
    except FileNotFoundError:
        return ''


def terminate_tree(record):
    """Terminate only the saved process identity and its current descendants."""
    root = same_process(record)
    if root is None:
        return []
    targets = []
    for proc in root.children(recursive=True):
        try:
            targets.append(identity(proc.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    targets.append(record)
    stopped = []
    for item in reversed(targets):
        proc = same_process(item)
        if proc:
            try:
                proc.terminate()
                stopped.append(proc)
            except psutil.NoSuchProcess:
                pass
    _, alive = psutil.wait_procs(stopped, timeout=3)
    for proc in alive:
        item = next(r for r in targets if r['pid'] == proc.pid)
        verified = same_process(item)
        if verified:
            verified.kill()
    psutil.wait_procs(alive, timeout=3)
    return [proc.pid for proc in stopped]


def supervise(directory):
    directory = Path(directory).resolve()
    path = directory/'job.json'
    record = read(path)
    record.update(supervisor=identity(os.getpid()), status='starting', updated_at=now())
    write(path, record)
    child = None
    try:
        if (directory/'cancel.request').exists():
            record.update(status='cancelled', exit_code=None)
            return
        command = read(directory/'argv.json')
        with (directory/'stdout.log').open('wb') as stdout, (directory/'stderr.log').open('wb') as stderr:
            options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session':True}
            child = subprocess.Popen(command, cwd=record['cwd'], stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, **options)
            record.update(worker=identity(child.pid), status='running', updated_at=now())
            write(path, record)
            while child.poll() is None:
                try:
                    proc = psutil.Process(child.pid)
                    rss = proc.memory_info().rss
                    for descendant in proc.children(recursive=True):
                        try:
                            rss += descendant.memory_info().rss
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    record['peak_worker_rss_bytes'] = max(record.get('peak_worker_rss_bytes', 0), rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                if (directory/'cancel.request').exists():
                    terminate_tree(record['worker'])
                    child.wait()
                    record['status'] = 'cancelled'
                    break
                time.sleep(.2)
            record.update(exit_code=child.wait())
            if record['status'] != 'cancelled':
                record['status'] = 'succeeded' if child.returncode == 0 else 'failed'
    except BaseException as exc:
        if child is not None:
            terminate_tree(record.get('worker'))
            child.wait()
        record.update(status='failed', error=str(exc)[:2000], exit_code=None)
    finally:
        record.update(finished_at=now(), updated_at=now())
        write(path, record)


def status(directory):
    directory = Path(directory).resolve()
    record = read(directory/'job.json')
    state = record['status']
    launch = directory/'launch.json'
    launcher = read(launch) if launch.exists() else None
    if state in ('succeeded','failed','cancelled') and (
            same_process(record.get('supervisor')) is not None or same_process(launcher) is not None):
        state = 'finalizing'
    if state in ('starting', 'running', 'launching') and same_process(record.get('supervisor')) is None:
        if same_process(launcher) is not None:
            state = 'starting'
        else:
            state = 'orphaned' if same_process(record.get('worker')) else 'interrupted'
    result = {key: record.get(key) for key in
              ('job_id','exit_code','supervisor','worker','started_at','finished_at','peak_worker_rss_bytes')}
    result.update(status=state, job_dir=str(directory), stdout=str(directory/'stdout.log'),
                  stderr=str(directory/'stderr.log'), metadata=str(directory/'job.json'))
    if state in ('failed','interrupted','orphaned'):
        result['error'] = record.get('error')
        result['stderr_tail'] = tail(directory/'stderr.log')
    return result


def start(task_dir, job_dir, argv_file, cwd=None):
    task = Path(task_dir).resolve()
    directory = inside(job_dir, task/'work')
    argv_file = inside(argv_file, task/'work')
    command = read(argv_file)
    if not isinstance(command, list) or not command or any(not isinstance(x,str) or not x or '\0' in x for x in command):
        raise ValueError('argv-file must contain a nonempty argument array of strings')
    launch_dir = Path(cwd or task.parent).resolve()
    if not launch_dir.is_dir():
        raise ValueError('Launch directory is unavailable')
    directory.mkdir(parents=True, exist_ok=False)
    write(directory/'argv.json', command)
    record = {'job_id':uuid.uuid4().hex, 'task_dir':str(task), 'cwd':str(launch_dir),
              'command_sha256':hashlib.sha256(json.dumps(command,ensure_ascii=False).encode('utf-8')).hexdigest(),
              'status':'launching', 'started_at':now(), 'exit_code':None}
    write(directory/'job.json', record)
    with (directory/'supervisor.log').open('wb') as log:
        options = {'creationflags':subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session':True}
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_supervise', str(directory)],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=record['cwd'], **options)
    try:
        write(directory/'launch.json', identity(proc.pid))
    except psutil.NoSuchProcess:
        pass  # A short command may already have completed.
    # Reap the launcher when this module is used from a long-lived caller too.
    # The CLI may exit immediately; the independent supervisor owns the PDF job.
    threading.Thread(target=proc.wait, daemon=True).start()
    return status(directory)


def cancel(directory):
    directory = Path(directory).resolve()
    record = read(directory/'job.json')
    if record['status'] in ('succeeded','failed','cancelled'):
        return status(directory)
    write(directory/'cancel.request', {'at':now()})
    if same_process(record.get('supervisor')) is None:
        launch = directory/'launch.json'
        if not launch.exists() or same_process(read(launch)) is None:
            stopped = terminate_tree(record.get('worker'))
            record.update(status='cancelled', finished_at=now(), exit_code=None, stopped_pids=stopped)
            write(directory/'job.json', record)
    return status(directory)


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    launch = sub.add_parser('start')
    launch.add_argument('--task-dir', required=True)
    launch.add_argument('--job-dir', required=True)
    launch.add_argument('--argv-file', required=True)
    launch.add_argument('--cwd')
    for name in ('status','cancel'):
        sub.add_parser(name).add_argument('--job-dir', required=True)
    internal = sub.add_parser('_supervise')
    internal.add_argument('job_dir')
    args = parser.parse_args(argv)
    if args.command == '_supervise':
        supervise(args.job_dir)
        return 0
    result = start(args.task_dir,args.job_dir,args.argv_file,args.cwd) if args.command == 'start' else (
        status(args.job_dir) if args.command == 'status' else cancel(args.job_dir))
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
