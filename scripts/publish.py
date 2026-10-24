#!/usr/bin/env python3
"""Publish verified assets without replacing an existing public release."""
import json
import os
from pathlib import Path
import subprocess
import sys
from package import IDS, tag, digest


def gh(*args, **kwargs):
    result = subprocess.run(['gh', *args], text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def publish(project, commit):
    directory = Path('dist')/project
    build = json.loads((directory/'build-info.json').read_text())
    info = build['package']
    release_tag = tag(info)
    if project not in IDS or info['id'] != project or build['packaging_commit'] != commit:
        raise ValueError('Artifact does not belong to the requested source commit')
    if os.environ.get('RELEASE_TAG', os.environ['GITHUB_REF_NAME']) != release_tag:
        raise ValueError('Publish requires the exact package tag')
    resolved = json.loads(gh('api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/commits/{release_tag}'))['sha']
    if resolved != commit:
        raise ValueError('Tag moved since the build')
    expected = {}
    for line in (directory/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split()
        if Path(name).name != name or digest(directory/name) != checksum:
            raise ValueError('Release checksum mismatch')
        expected[name] = checksum
    expected['SHA256SUMS'] = digest(directory/'SHA256SUMS')
    assets = [directory/name for name in expected]
    def find_release():
        # GitHub's by-tag endpoint does not return drafts. The authenticated
        # release list includes drafts and must be paginated in this monorepo.
        pages = json.loads(gh('api', '--paginate', '--slurp',
                              f'repos/{os.environ["GITHUB_REPOSITORY"]}/releases?per_page=100'))
        matches = [release for page in pages for release in page if release['tag_name'] == release_tag]
        if len(matches) > 1:
            raise ValueError('Ambiguous release tag')
        return matches[0] if matches else None

    release = find_release()
    if release is None:
        flags = ['--prerelease'] if '-' in info['version'] else []
        gh('release', 'create', release_tag, '--verify-tag', '--draft', '--latest=false', '--target', commit,
           '--title', f"{project} {info['version']}-{info['pkgrel']}", '--notes-file', str(directory/'notes.md'), *flags)
        release = find_release()
        if release is None:
            raise ValueError('Created draft was not found')
    if release['draft']:
        if release['target_commitish'] not in [commit, 'main']:
            raise ValueError('Draft belongs to a different build')
        gh('release', 'upload', release_tag, *map(str, assets), '--clobber')
    # Verify draft/public bytes through GitHub digests before publication or idempotent success.
    release = find_release()
    actual = {a['name']: a.get('digest') for a in release['assets']}
    if actual != {name: 'sha256:'+value for name, value in expected.items()}:
        raise ValueError('Published asset set or bytes differ; increment pkgrel')
    if release['draft']:
        gh('release', 'edit', release_tag, '--draft=false', '--latest=false')
    print(gh('release', 'view', release_tag, '--json', 'url', '--jq', '.url'))


if __name__ == '__main__':
    publish(sys.argv[1], sys.argv[2])
