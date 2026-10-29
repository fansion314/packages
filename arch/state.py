#!/usr/bin/env python3
"""Persist generated Pages snapshots without touching the maintenance branch."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

REPOSITORY = 'https://github.com/fansion314/packages.git'
STATUS = 'https://packages.fansionia.world/status.json'


def public_status():
    try:
        with urllib.request.urlopen(STATUS, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise RuntimeError(
            f'Public repository status returned HTTP {error.code}; '
            f'CF-Ray={error.headers.get("cf-ray", "")}; '
            f'CF-Mitigated={error.headers.get("cf-mitigated", "")}; '
            f'body={error.read(500).decode("utf-8", errors="replace")!r}'
        ) from error


def active_snapshot():
    return public_status().get('active', '')


def mirror_state():
    """Read persisted recovery state through the uncached GitHub API."""
    result = subprocess.run(['gh', 'api', '-H', 'Cache-Control: no-cache',
        'repos/fansion314/packages/contents/mirror-state.json?ref=pacman-pages'],
        text=True, capture_output=True)
    if result.returncode:
        if 'HTTP 404' in result.stderr:
            return {}
        raise RuntimeError('Cannot read persisted CNB mirror recovery state')
    import base64
    return json.loads(base64.b64decode(json.loads(result.stdout)['content']))


def checkout(directory):
    directory = Path(directory)
    if directory.exists():
        raise ValueError('Use a fresh generated-state directory')
    exists = subprocess.check_output(['git', 'ls-remote', REPOSITORY, 'refs/heads/pacman-pages'], text=True).strip()
    if exists:
        subprocess.run(['git', 'clone', '--depth=1', '--branch', 'pacman-pages', REPOSITORY, str(directory)], check=True)
    else:
        directory.mkdir(parents=True)
        subprocess.run(['git', 'init', '--initial-branch=pacman-pages', str(directory)], check=True)
        subprocess.run(['git', '-C', str(directory), 'remote', 'add', 'origin', REPOSITORY], check=True)
    active = active_snapshot()
    if active and not (directory/'snapshots'/active/'manifest.json').is_file():
        raise ValueError('Live snapshot is missing from the persisted generated state')
    print('Active snapshot:', active or '(first deployment)')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('active='+active+'\n')


def commit(directory):
    directory = Path(directory)
    paths = ['snapshots', 'snapshots.json', 'keys', '.nojekyll', 'index.html']
    if (directory/'mirror-state.json').exists():
        paths.append('mirror-state.json')
    subprocess.run(['git', '-C', str(directory), 'add', '--', *paths], check=True)
    changes = subprocess.run(['git', '-C', str(directory), 'diff', '--cached', '--quiet'])
    if changes.returncode == 0:
        return
    if changes.returncode != 1:
        raise RuntimeError('Could not inspect generated changes')
    subprocess.run(['git', '-C', str(directory), '-c', 'user.name=github-actions[bot]', '-c',
                    'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                    'commit', '-m', 'chore: stage verified pacman snapshot'], check=True)
    subprocess.run(['git', '-C', str(directory), '-c', 'credential.helper=!gh auth git-credential',
                    'push', 'origin', 'HEAD:pacman-pages'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['checkout', 'commit'])
    parser.add_argument('directory')
    args = parser.parse_args()
    if args.command == 'checkout':
        checkout(args.directory)
    else:
        commit(args.directory)
