#!/usr/bin/env python3
"""Append only missing verified support release assets, then publish."""
from pathlib import Path
import os
import subprocess
import sys
import time
from sign import checksum, release

tag = sys.argv[1]
repository = os.environ['GITHUB_REPOSITORY']
directory = Path('dist/support')
current = release(repository, tag)
if current is None:
    subprocess.run(['gh', 'release', 'create', tag, '--verify-tag', '--draft', '--latest=false',
                    '--title', tag, '--notes', 'Signed repository support package; built and installed in native Arch CI.'], check=True)
    for attempt in range(30):
        current = release(repository, tag)
        if current:
            break
        time.sleep(2)
    if not current:
        raise RuntimeError('New draft is not visible; retry publication')
assets = {a['name']: a for a in current['assets']}
for path in sorted(directory.iterdir()):
    existing = assets.get(path.name)
    if existing:
        if existing.get('digest') != 'sha256:'+checksum(path):
            raise ValueError('Support release bytes changed; increment pkgrel')
    else:
        if not current['draft']:
            raise ValueError('Public support release is incomplete; do not silently change it')
        subprocess.run(['gh', 'release', 'upload', tag, str(path)], check=True)
current = release(repository, tag)
for path in directory.iterdir():
    asset = next(a for a in current['assets'] if a['name'] == path.name)
    if asset.get('digest') != 'sha256:'+checksum(path):
        raise ValueError('Support release upload digest mismatch')
if current['draft']:
    subprocess.run(['gh', 'release', 'edit', tag, '--draft=false', '--latest=false'], check=True)
