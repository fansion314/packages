#!/usr/bin/env python3
"""Publish verified assets without replacing an existing public release."""
import json
import os
from pathlib import Path
import subprocess
import sys
from package import manifest, tag, parse_tag, digest


def gh(*args, **kwargs):
    return subprocess.run(['gh', *args], check=True, text=True, capture_output=True, **kwargs).stdout


def publish(project, commit):
    info = manifest(project)
    release_tag = tag(info)
    if parse_tag(release_tag) != project or os.environ['GITHUB_REF_NAME'] != release_tag:
        raise ValueError('Publish requires the exact package tag')
    resolved = json.loads(gh('api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/commits/{release_tag}'))['sha']
    if resolved != commit:
        raise ValueError('Tag moved since the build')
    directory = Path('dist')/project
    expected = {}
    for line in (directory/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split()
        if Path(name).name != name or digest(directory/name) != checksum:
            raise ValueError('Release checksum mismatch')
        expected[name] = checksum
    expected['SHA256SUMS'] = digest(directory/'SHA256SUMS')
    assets = [directory/name for name in expected]
    query = subprocess.run(['gh', 'api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/releases/tags/{release_tag}'], capture_output=True, text=True)
    if query.returncode:
        if '404' not in query.stderr:
            raise RuntimeError(query.stderr)
        flags = ['--prerelease'] if '-' in info['version'] else []
        gh('release', 'create', release_tag, '--verify-tag', '--draft', '--latest=false',
           '--title', f"{project} {info['version']}-{info['pkgrel']}", '--notes-file', str(directory/'notes.md'), *flags)
        release = json.loads(gh('api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/releases/tags/{release_tag}'))
    else:
        release = json.loads(query.stdout)
    if release['draft']:
        if release['target_commitish'] not in [commit, 'main']:
            raise ValueError('Draft belongs to a different build')
        gh('release', 'upload', release_tag, *map(str, assets), '--clobber')
    # Verify draft/public bytes through GitHub digests before publication or idempotent success.
    release = json.loads(gh('api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/releases/tags/{release_tag}'))
    actual = {a['name']: a.get('digest') for a in release['assets']}
    if actual != {name: 'sha256:'+value for name, value in expected.items()}:
        raise ValueError('Published asset set or bytes differ; increment pkgrel')
    if release['draft']:
        gh('release', 'edit', release_tag, '--draft=false', '--latest=false')
    print(gh('release', 'view', release_tag, '--json', 'url', '--jq', '.url'))


if __name__ == '__main__':
    publish(sys.argv[1], sys.argv[2])
