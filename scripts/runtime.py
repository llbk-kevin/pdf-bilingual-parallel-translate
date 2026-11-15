#!/usr/bin/env python3
"""Run a frozen PDF task with its recorded import paths."""
import importlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import sys

def main():
    config = json.loads(Path(__file__).with_name('runtime.json').read_text(encoding='utf-8'))
    sys.path[:] = config['paths']
    for module in ('pypdf', 'pypdfium2', 'pymupdf', 'PIL.Image', 'fontTools'):
        importlib.import_module(module)
    actual = {name: importlib.metadata.version(name) for name in config['packages']}
    if actual != config['packages']:
        raise RuntimeError('Frozen runtime dependencies changed: ' + json.dumps(actual))
    if sys.argv[1:] == ['--probe']:
        print(json.dumps(actual))
    else:
        runner = str(Path(sys.argv[1]).resolve())
        sys.argv = sys.argv[1:]
        sys.path.insert(0, str(Path(runner).parent))
        runpy.run_path(runner, run_name='__main__')


if __name__ == '__main__':
    main()
