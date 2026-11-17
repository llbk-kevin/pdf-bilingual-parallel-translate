"""Coordinate PDF tasks, memory admission and owned tool sessions."""
import argparse
import json
import os
from pathlib import Path
import tomllib
import hashlib
import datetime
import psutil

from task_runtime import write


def memory_status(reserve_bytes=None, snapshot=None):
    memory = snapshot or psutil.virtual_memory()
    reserve = max(2*1024**3, int(memory.total*.20)) if reserve_bytes is None else reserve_bytes
    if type(reserve) is not int or reserve < 0:
        raise ValueError('Memory reserve must be a nonnegative byte count')
    return {'total_bytes':memory.total, 'available_bytes':memory.available,
            'reserve_bytes':reserve, 'dispatch_budget_bytes':max(0,memory.available-reserve),
            'can_dispatch':memory.available > reserve}


def register_session(task_dir, agent, process=None):
    """Only a tool kernel verified in the direct caller's parent chain can register."""
    proc = process or psutil.Process(os.getppid())
    # Some launchers insert a Python shim; do not search unrelated process trees.
    for _ in range(4):
        command = proc.cmdline()
        if any(Path(arg).name == 'kernel.js' for arg in command) and '--session-id' in command:
            break
        parent = proc.parent()
        if parent is None or proc.name().lower() not in ('python.exe','python','python3'):
            raise ValueError('unverified_tool_caller: invoke registration directly from the tool kernel')
        proc = parent
    else:
        raise ValueError('unverified_tool_caller')
    session = command[command.index('--session-id')+1]
    record = {'agent':agent, 'task_dir':str(Path(task_dir).resolve()), 'pid':proc.pid,
              'started':proc.create_time(), 'session_id':session, 'rss_bytes':proc.memory_info().rss,
              'status':'running', 'registered_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    key = hashlib.sha256((agent+str(record['pid'])+str(record['started'])).encode()).hexdigest()[:24]
    path = Path(task_dir).resolve()/'work'/'tool-sessions'/(key+'.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        old = json.loads(path.read_text(encoding='utf-8'))
        if old['status'] != 'running':
            raise ValueError('Session is already handed off; register only the current live kernel')
        return {'record':str(path), **old}
    write(path,record)
    return {'record':str(path), **record}


def mark_session(path, status, checkpoint):
    if status not in ('cleanup_required','cleanup_unavailable'):
        raise ValueError('Invalid cleanup status')
    path = Path(path).resolve()
    record = json.loads(path.read_text(encoding='utf-8'))
    checkpoint = Path(checkpoint).resolve()
    if not checkpoint.is_relative_to(Path(record['task_dir']).resolve()) or not checkpoint.is_file():
        raise ValueError('Save the checkpoint inside the task before session handoff')
    record.update(status=status, checkpoint=str(checkpoint))
    write(path,record)
    return record


def session_status(task_dir):
    records = []
    tracked = set()
    for path in sorted((Path(task_dir)/'work'/'tool-sessions').glob('*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        try:
            proc = psutil.Process(record['pid'])
            live = abs(proc.create_time()-record['started']) < .01
            if live:
                record['rss_bytes'] = proc.memory_info().rss
                tracked.add(record['pid'])
        except psutil.NoSuchProcess:
            live = False
        except psutil.AccessDenied:
            live = None
        if live is False and record['status'] in ('running','cleanup_required'):
            record['status'] = 'reset_observed' if record['status']=='cleanup_required' else 'exited'
            record['released_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            write(path,record)
        records.append({'record':str(path), **record, 'alive':live})
    unknown = []
    for proc in psutil.process_iter(['pid','name']):
        if proc.pid in tracked or (proc.info['name'] or '').lower() not in ('node.exe','node'):
            continue
        try:
            if any(Path(arg).name == 'kernel.js' for arg in proc.cmdline()):
                unknown.append({'pid':proc.pid,'started':proc.create_time(),'rss_bytes':proc.memory_info().rss})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {'sessions':records, 'unknown_kernels':unknown,
            'note':'Unknown kernels are diagnostics only; never terminate them by name or memory size.'}


def host_settings(path):
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    agents = data.get('agents', {})
    capacity = agents.get('max_concurrent_threads_per_session')
    if capacity is not None and (type(capacity) is not int or capacity < 1):
        raise ValueError('Host subagent capacity must be a positive integer')
    return {'config':str(path), 'enabled':agents.get('enabled',True),
            'configured_capacity':capacity, 'capacity_choice_needed':capacity is None,
            'effective_capacity_source':'Use the actual subagent tools for current availability'}


def ready_tasks(tasks, available_slots, memory=None, reserve_bytes=None):
    if type(available_slots) is not int or available_slots < 0:
        raise ValueError('available_slots must be a nonnegative integer')
    invalid = [task['id'] for task in tasks if task['status'] not in ('queued','running','completed','blocked')]
    if invalid:
        raise ValueError('Invalid coordination status for tasks: '+', '.join(invalid))
    ids = [task['id'] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate coordination task IDs')
    completed = {task['id'] for task in tasks if task['status']=='completed'}
    ready = [task for task in tasks if task['status']=='queued'
             and all(parent in completed for parent in task['depends_on'])]
    ready.sort(key=lambda task:task['phase'] != 'review')
    budget = memory_status(reserve_bytes, memory)['dispatch_budget_bytes']
    selected = []
    for task in ready:
        estimate = task.get('estimated_memory_bytes', 256*1024**2)
        if type(estimate) is not int or estimate < 1:
            raise ValueError('Task memory estimate must be a positive byte count')
        if len(selected) < available_slots and estimate <= budget:
            selected.append(task)
            budget -= estimate
    return selected


def main():
    import sys
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    home=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))
    parser.add_argument('--config',type=Path,default=home/'config.toml')
    sub = parser.add_subparsers(dest='command')
    for name in ('memory','session-register','sessions'):
        child = sub.add_parser(name)
        child.add_argument('--task-dir',required=True)
        if name=='session-register':
            child.add_argument('--agent',required=True)
        if name=='memory':
            child.add_argument('--reserve-bytes',type=int)
    mark = sub.add_parser('session-mark')
    mark.add_argument('--record',required=True)
    mark.add_argument('--status',choices=('cleanup_required','cleanup_unavailable'),required=True)
    mark.add_argument('--checkpoint',required=True)
    args = parser.parse_args()
    if args.command=='memory':
        config = Path(args.task_dir)/'work'/'resource-settings.json'
        settings = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        reserve = args.reserve_bytes if args.reserve_bytes is not None else settings.get('memory_reserve_bytes')
        result = memory_status(reserve)
    elif args.command=='session-register':
        result = register_session(args.task_dir,args.agent)
    elif args.command=='session-mark':
        result = mark_session(args.record,args.status,args.checkpoint)
    elif args.command=='sessions':
        result = session_status(args.task_dir)
    else:
        result = host_settings(args.config)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
