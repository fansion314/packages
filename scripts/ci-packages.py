#!/usr/bin/env python3
"""Choose application builds affected by a maintenance diff (static checks always run)."""
import json
from pathlib import PurePosixPath
import subprocess
import sys

from package import IDS

SHARED_BUILD_INPUTS = {
    'scripts/package.py', 'scripts/build.sh', 'scripts/arch-dependencies.sh',
    'scripts/verify-native.py', '.github/workflows/build-package.yml',
}


def affected(paths):
    selected = set()
    for path in paths:
        if path in SHARED_BUILD_INPUTS:
            return list(IDS)
        parts = PurePosixPath(path).parts
        if len(parts) >= 2 and parts[0] == 'packages' and parts[1] in IDS:
            selected.add(parts[1])
    return [project for project in IDS if project in selected]


def main(base, head):
    if not base or set(base) == {'0'}:
        projects = list(IDS)  # Manual runs and new branches exercise every app.
    else:
        paths = subprocess.check_output(
            ['git', 'diff', '--name-only', '-z', base, head], text=True).split('\0')
        projects = affected(paths)
    print('matrix='+json.dumps({'package': projects}))
    print('has_packages='+str(bool(projects)).lower())


if __name__ == '__main__':
    main(*sys.argv[1:])
