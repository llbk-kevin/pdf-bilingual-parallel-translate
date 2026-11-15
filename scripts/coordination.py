"""Read host settings and select ready PDF tasks without role quotas."""
import argparse
import json
import os
from pathlib import Path
import tomllib


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


def ready_tasks(tasks, available_slots):
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
    return ready[:available_slots]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    home=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))
    parser.add_argument('--config',type=Path,default=home/'config.toml')
    args=parser.parse_args()
    print(json.dumps(host_settings(args.config),ensure_ascii=False))


if __name__=='__main__':
    main()
