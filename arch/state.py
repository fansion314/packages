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


def active_snapshot():
    try:
        with urllib.request.urlopen(STATUS, timeout=30) as response:
            state = json.load(response)
            return state['active']
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return ''
        raise


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
