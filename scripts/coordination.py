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
    reserve = max(2*1024**3, int(memory.total*.10)) if reserve_bytes is None else reserve_bytes
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


def ready_tasks(tasks, available_slots, memory=None, reserve_bytes=None, check_memory=True):
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
    budget = memory_status(reserve_bytes, memory)['dispatch_budget_bytes'] if check_memory else None
    selected = []
    for task in ready:
        estimate = task.get('estimated_memory_bytes', 256*1024**2)
        if type(estimate) is not int or estimate < 1:
            raise ValueError('Task memory estimate must be a positive byte count')
        resource_class = task.get('resource_class', 'heavy')
        if resource_class not in ('light', 'heavy'):
            raise ValueError('Task resource_class must be light or heavy')
        if len(selected) < available_slots and (resource_class == 'light' or budget is None or estimate <= budget):
            selected.append(task)
            if resource_class == 'heavy' and budget is not None:
                budget -= estimate
    return selected


def check_model_result(model, effort, *, actual_model=None, actual_effort=None, evidence=None,
                       agent_id=None, evidence_agent_id=None, error=None):
    """Classify host/tool evidence; never infer availability from a static catalog."""
    result = {'requested_model': model, 'requested_effort': effort,
              'actual_model': actual_model, 'actual_effort': actual_effort, 'evidence': evidence,
              'agent_id': agent_id, 'evidence_agent_id': evidence_agent_id}
    if error:
        result.update(status='failed', error=error, action='Ask the user before selecting another model')
    elif ((actual_model is not None and actual_model != model)
          or (actual_effort is not None and actual_effort != effort)):
        result.update(status='mismatch', action='Stop this assignment and resolve the model mismatch')
    elif (actual_model == model and actual_effort == effort and evidence
          and agent_id and evidence_agent_id == agent_id):
        result.update(status='verified')
    else:
        result.update(status='unverified', action='Record missing host evidence; do not claim verification')
    return result


def plan_summary(plan):
    tasks = plan.get('tasks', [])
    launches = plan.get('launches', [])
    work_agents = {item['agent_id'] for item in launches if item.get('agent_id')}
    probe_agents = {item['agent_id'] for item in plan.get('model_checks', [])
                    if isinstance(item, dict) and item.get('agent_id')}
    running = {task['agent_id'] for task in tasks
               if task.get('status') == 'running' and task.get('agent_id')}
    return {'created_agents': len(work_agents | probe_agents), 'work_agents': len(work_agents),
            'probe_agents': len(probe_agents), 'running_agents': len(running),
            'queued_tasks': sum(task.get('status') == 'queued' for task in tasks),
            'blocked_tasks': sum(task.get('status') == 'blocked' for task in tasks),
            'resume_count': sum(task.get('resume_count', 0) for task in tasks)}


def validate_plan(plan):
    """Validate the current planning/dispatch ledger without changing it or calling a host."""
    errors = []
    if not isinstance(plan, dict):
        return {'ok': False, 'errors': ['Plan must be an object']}
    documents, tasks = plan.get('documents'), plan.get('tasks')
    if not isinstance(documents, list) or not documents or not isinstance(tasks, list) or not tasks:
        return {'ok': False, 'errors': ['Nonempty documents and tasks lists are required']}
    if any(not isinstance(item, dict) for item in documents + tasks):
        return {'ok': False, 'errors': ['Documents and tasks must contain objects']}

    def pages(item, label):
        value = item.get('pages')
        if (not isinstance(value, list) or not value
                or any(type(page) is not int or page < 1 for page in value)
                or len(value) != len(set(value))):
            errors.append(label + ': pages must be unique positive physical page numbers')
            return set()
        return set(value)

    docs, by_id, page_sets, names = {}, {}, {}, set()
    for doc in documents:
        identifier = doc.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in docs:
            errors.append('Document IDs must be nonempty and unique')
            continue
        docs[identifier] = doc
        page_sets[identifier] = pages(doc, identifier)
    task_pages = {}
    for task in tasks:
        identifier = task.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in by_id:
            errors.append('Task IDs must be nonempty and unique')
            continue
        by_id[identifier] = task
        name = task.get('name')
        if not isinstance(name, str) or not name.strip() or name in names:
            errors.append(identifier + ': display name must be nonempty and unique')
        names.add(str(name))
        task_pages[identifier] = pages(task, identifier)
        if task.get('document') not in docs:
            errors.append(identifier + ': unknown document')
        elif not task_pages[identifier] <= page_sets[task['document']]:
            errors.append(identifier + ': editing/review pages are outside document selection')
        if task.get('phase') not in ('translate', 'review', 'repair'):
            errors.append(identifier + ': phase must be translate, review or repair')
        if task.get('status') not in ('queued', 'running', 'completed', 'blocked'):
            errors.append(identifier + ': invalid status')
        for field in ('model', 'reasoning_effort', 'responsibilities', 'handoff'):
            if not isinstance(task.get(field), str) or not task[field].strip():
                errors.append(identifier + ': missing ' + field)
        if task.get('fork_turns') not in ('none', 'all'):
            errors.append(identifier + ': fork_turns is required')
        if task.get('phase') in ('translate', 'review') and task.get('fork_turns') != 'none':
            errors.append(identifier + ': first translation/review assignment requires fresh context')
        if type(task.get('owns_edits')) is not bool:
            errors.append(identifier + ': owns_edits must be explicit')
        if task.get('phase') == 'review' and task.get('owns_edits'):
            errors.append(identifier + ': reviewers submit observations, not translation edits')
        if type(task.get('resume_count', 0)) is not int or task.get('resume_count', 0) < 0:
            errors.append(identifier + ': resume_count must be a nonnegative integer')
        if task.get('resource_class', 'heavy') not in ('light', 'heavy'):
            errors.append(identifier + ': invalid resource_class')
        if not isinstance(task.get('depends_on'), list) or any(not isinstance(x, str) for x in task.get('depends_on', [])):
            errors.append(identifier + ': depends_on must be a list of task IDs')

    ancestors = {}
    def dependencies(identifier, visiting):
        if identifier in ancestors:
            return ancestors[identifier]
        if identifier in visiting:
            errors.append(identifier + ': dependency cycle')
            return set()
        found = set()
        for dependency in by_id[identifier].get('depends_on', []) if isinstance(by_id[identifier].get('depends_on'), list) else []:
            if not isinstance(dependency, str) or dependency not in by_id:
                errors.append(identifier + ': unknown dependency ' + str(dependency))
                continue
            found.add(dependency)
            found.update(dependencies(dependency, visiting | {identifier}))
        ancestors[identifier] = found
        return found
    for identifier in by_id:
        dependencies(identifier, set())
    for doc_id, doc in docs.items():
        members = [task for task in by_id.values() if task.get('document') == doc_id]
        writer = by_id.get(doc.get('state_writer'))
        if not writer or writer.get('document') != doc_id or writer.get('phase') == 'review':
            errors.append(doc_id + ': state_writer must identify this document\'s translation/repair owner')
        translators = [task for task in members if task.get('phase') == 'translate' and task.get('owns_edits')]
        reviewers = [task for task in members if task.get('phase') == 'review']
        for group, label in ((translators, 'translation'), (reviewers, 'independent review')):
            covered = set().union(*(task_pages[task['id']] for task in group)) if group else set()
            if covered != page_sets[doc_id]:
                errors.append(doc_id + ': incomplete ' + label + ' coverage')
        active = [task for task in members if task.get('owns_edits') and task.get('status') != 'completed']
        for i, task in enumerate(active):
            for other in active[i+1:]:
                if task_pages[task['id']] & task_pages[other['id']]:
                    errors.append(doc_id + ': overlapping editing ownership: ' + task['id'] + ', ' + other['id'])
        editor_agents = {task['agent_id'] for task in members if task.get('phase') != 'review' and task.get('agent_id')}
        for task in reviewers:
            if task.get('agent_id') and task['agent_id'] in editor_agents:
                errors.append(task['id'] + ': reviewer agent also translated/repaired this document')
            for translator in translators:
                if task_pages[task['id']] & task_pages[translator['id']] and translator['id'] not in ancestors[task['id']]:
                    errors.append(task['id'] + ': missing dependency on ' + translator['id'])
            if task.get('status') in ('queued', 'running'):
                for repair in members:
                    if (repair.get('phase') == 'repair' and repair.get('status') != 'completed'
                            and task_pages[task['id']] & task_pages[repair['id']]
                            and repair['id'] not in ancestors[task['id']]):
                        errors.append(task['id'] + ': missing dependency on pending repair ' + repair['id'])

    launches = plan.get('launches', [])
    if not isinstance(launches, list) or any(not isinstance(item, dict) for item in launches):
        errors.append('launches must be a list of objects')
        launches = []
    launch_ids, models = {}, []
    for launch in launches:
        task = by_id.get(launch.get('task'))
        if task is None:
            errors.append('Launch references an unknown task')
            continue
        agent = launch.get('agent_id')
        if not isinstance(agent, str) or not agent:
            errors.append(task['id'] + ': launch requires actual agent_id')
        elif agent in launch_ids:
            errors.append(agent + ': duplicate launch; record continuation as resume_count')
        else:
            launch_ids[agent] = task
        for field, expected in (('requested_model', task.get('model')), ('requested_effort', task.get('reasoning_effort'))):
            if launch.get(field) != expected:
                errors.append(task['id'] + ': launch ' + field + ' differs from confirmed task')
        check = check_model_result(task.get('model'), task.get('reasoning_effort'),
                                   actual_model=launch.get('actual_model'), actual_effort=launch.get('actual_effort'),
                                   evidence=launch.get('evidence'), agent_id=launch.get('agent_id'),
                                   evidence_agent_id=launch.get('evidence_agent_id'), error=launch.get('error'))
        models.append({'task': task['id'], **check})
        if check['status'] in ('failed', 'mismatch'):
            errors.append(task['id'] + ': model ' + check['status'] + '; no automatic substitution')
    # Historical launch identities also enforce independent review after reassignment.
    for doc_id in docs:
        editor_agents, reviewer_agents = set(), set()
        for task in by_id.values():
            if task.get('document') != doc_id:
                continue
            identities = {task['agent_id']} if task.get('agent_id') else set()
            identities.update(item['agent_id'] for item in launches
                              if item.get('task') == task['id'] and item.get('agent_id'))
            (reviewer_agents if task.get('phase') == 'review' else editor_agents).update(identities)
        for agent in editor_agents & reviewer_agents:
            errors.append(agent + ': historical translation identity cannot independently review its document')
    model_checks = plan.get('model_checks', [])
    if not isinstance(model_checks, list) or any(not isinstance(item, dict) for item in model_checks):
        errors.append('model_checks must be a list of evidence objects')
        model_checks = []
    summary_plan = {'tasks': [task for task in tasks if type(task.get('resume_count', 0)) is int],
                    'launches': launches, 'model_checks': model_checks}
    return {'ok': not errors, 'errors': list(dict.fromkeys(errors)), 'models': models,
            'summary': plan_summary(summary_plan),
            'note': 'Structure only: user confirmation and a real model/tool probe are separate evidence'}


def main():
    import sys
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    home=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))
    parser.add_argument('--config',type=Path,default=home/'config.toml')
    sub = parser.add_subparsers(dest='command')
    validate = sub.add_parser('validate-plan')
    validate.add_argument('--plan', required=True, type=Path)
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
    if args.command=='validate-plan':
        result = validate_plan(json.loads(args.plan.read_text(encoding='utf-8')))
    elif args.command=='memory':
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
    if args.command == 'validate-plan' and not result['ok']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
