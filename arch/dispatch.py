#!/usr/bin/env python3
"""Notify distribution, restoring only GitHub's automatic inactivity disable."""
import argparse
import json
import subprocess

TARGET = 'fansion314/packages'


def dispatch(project, platform):
    workflow = json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{TARGET}/actions/workflows/downstream.yml'], text=True))
    state = workflow['state']
    if state == 'disabled_inactivity':
        subprocess.run(['gh', 'workflow', 'enable', 'downstream.yml', '-R', TARGET], check=True)
    elif state != 'active':
        raise RuntimeError('Distribution workflow was intentionally disabled or is unavailable; leaving it unchanged')
    subprocess.run(['gh', 'workflow', 'run', 'downstream.yml', '-R', TARGET, '--ref', 'main',
                    '-f', 'project='+project, '-f', 'platform='+platform], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', choices=['dnr', 'pi', 'etcher', 'motrix',
                                          'deepseek-harness', 'bitwarden', 'obsidian',
                                          'python-pptx', 'fansionia-keyring', 'clash-momo', 'mihomomo'])
    parser.add_argument('platform', choices=['arch', 'macos'])
    args = parser.parse_args(argv)
    dispatch(args.project, args.platform)


if __name__ == '__main__':
    main()
