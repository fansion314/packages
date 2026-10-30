#!/usr/bin/env python3
"""Publish a verified Homebrew distribution snapshot and its immutable CNB assets."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from cnb_release import Client, location

spec = importlib.util.spec_from_file_location('homebrew_sync', Path(__file__).with_name('sync.py'))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

REPOSITORY = 'fansionia/packages'
REMOTE = 'https://cnb.cool/'+REPOSITORY
OWNER = 'Managed by fansion314/packages homebrew/scripts/mirror.py (schema 1).'
RECEIPT = 'homebrew-candidate.json'
PROVENANCE = 'homebrew/mirror.json'


def git(directory, *args, env=None):
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(directory), *args],
                                   text=True, env=env).strip()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def verify_remote(url, expected):
    # No authorization and no local cache: validate the public object's bytes.
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'fansionia-homebrew-mirror'})
            with urllib.request.urlopen(request, timeout=90) as response:
                actual = hashlib.sha256()
                while chunk := response.read(1024*1024):
                    actual.update(chunk)
            if actual.hexdigest() != expected:
                raise ValueError('CNB anonymous download SHA-256 mismatch')
            return
        except OSError:
            if attempt == 3:
                raise RuntimeError('CNB anonymous download failed') from None
            time.sleep(2**attempt)


def validate_info(project, info):
    if info['repository'] != sync.PROJECTS[project][0]:
        raise ValueError('Unexpected Homebrew upstream repository')
    if not re.fullmatch(sync.PROJECTS[project][1], info['tag']):
        raise ValueError('Unexpected Homebrew upstream tag')
    if not re.fullmatch(r'[a-f0-9]{64}', info['sha256']):
        raise ValueError('Invalid Homebrew SHA-256')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', info['asset']):
        raise ValueError('Invalid Homebrew archive filename')
    expected = f"https://github.com/{info['repository']}/releases/download/{info['tag']}/{info['asset']}"
    if info['url'] != expected:
        raise ValueError('Unexpected Homebrew upstream URL')
    if info.get('github_digest') not in (None, 'sha256:'+info['sha256']):
        raise ValueError('Inconsistent GitHub asset digest')
    key = [*map(int, info['version'].split('.')), info['release'], info['revision']]
    if info['key'] != key:
        raise ValueError('Inconsistent Homebrew version key')
    return info


def compare(previous, current):
    if current['key'] < previous['key']:
        raise ValueError('Refusing to downgrade CNB Homebrew release')
    if current['key'] == previous['key']:
        for field in ('sha256', 'upstream_url', 'url', 'asset', 'source_sha'):
            if previous.get(field) != current.get(field):
                raise ValueError('Refusing to replace immutable CNB Homebrew release')


def source_files(info, directory):
    subprocess.run(['gh', 'release', 'download', info['tag'], '--repo', info['repository'],
                    '--pattern', info['asset'], '--pattern', info['asset']+'.sha256',
                    '--dir', str(directory)], check=True)
    archive = directory/info['asset']
    checksum = directory/(info['asset']+'.sha256')
    fields = checksum.read_text().split()
    if fields != [info['sha256'], info['asset']] or digest(archive) != info['sha256']:
        raise ValueError('Original Homebrew archive/checksum mismatch')
    return archive, checksum


def readme():
    return '''# Fansionia package mirror

This repository distributes Homebrew recipes and immutable package attachments.
Development and publishing workflows: https://github.com/fansion314/packages.

## Homebrew

Apple Silicon and macOS 15 or later:

```sh
brew tap fansionia/tap https://cnb.cool/fansionia/packages
brew install fansionia/tap/dnr fansionia/tap/pi-dnr
brew install --cask fansionia/tap/etcher-dnr
brew install --cask fansionia/tap/clash-momo
```

Recipes and their shared runtime dependencies download verified macOS archives
from this repository's public CNB Release attachments.

To switch an existing `fansionia/tap` to this mirror:

```sh
brew tap --custom-remote fansionia/tap https://cnb.cool/fansionia/packages
brew update-reset "$(brew --repository fansionia/tap)"
```

The second command resets only this tap checkout, removing manual changes within
it. Installed applications and their data are retained. To switch back, use
`https://github.com/fansion314/packages.git` in the first command and repeat the
second command. Daily updates use `brew update` and `brew upgrade`.

## Signed pacman mirror

Release attachments also contain unmodified Arch packages, signatures and
database snapshots. Use `Server = https://packages.fansionia.world/mirror/$arch`
in the `[fansionia]` section of pacman.conf, with
`SigLevel = Required TrustedOnly`. Follow the authoritative repository for
signing-key verification and setup.
'''


def authenticated_push(output, dry_run=False):
    token = os.environ.get('CNB_MIRROR_TOKEN')
    if not token:
        raise ValueError('CNB_MIRROR_TOKEN is required')
    # Supply credentials only through an ephemeral askpass process environment.
    with tempfile.TemporaryDirectory(prefix='fansionia-cnb-auth-') as tmp:
        askpass = Path(tmp)/'askpass'
        askpass.write_text('#!/bin/sh\ncase "$1" in\n  *Username*) printf "%s\\n" cnb ;;\n  *Password*) printf "%s\\n" "$CNB_MIRROR_TOKEN" ;;\n  *) exit 1 ;;\nesac\n')
        askpass.chmod(0o700)
        env = {**os.environ, 'GIT_ASKPASS': str(askpass), 'GIT_TERMINAL_PROMPT': '0'}
        result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(output),
                                 '-c', 'credential.helper=', 'push', *(['--dry-run'] if dry_run else []),
                                 'origin', 'HEAD:refs/heads/main'], env=env, capture_output=True, text=True)
        if result.returncode:
            # Do not echo remote diagnostics, which may contain credential material.
            diagnostic = (result.stderr or '').lower()
            if any(word in diagnostic for word in ('403', '401', 'forbidden', 'denied', 'authentication failed')):
                raise RuntimeError('CNB Git write access denied; CNB_MIRROR_TOKEN needs repo-code:rw '
                                   'for fansionia/packages (Release write access alone is insufficient)')
            operation = 'write preflight' if dry_run else 'publication'
            raise RuntimeError(f'CNB Git {operation} failed; verify connectivity and regenerate the candidate '
                               'if remote main advanced')


def prepare(output, source=ROOT, remote=REMOTE, client=None):
    output, source = Path(output).resolve(), Path(source).resolve()
    if output.exists():
        raise ValueError('Candidate directory already exists; use a fresh output directory')
    records = {project: validate_info(project, json.loads((source/'homebrew/releases'/f'{project}.json').read_text()))
               for project in sync.PROJECTS}
    source_sha = git(source, 'rev-parse', 'HEAD')
    if not re.fullmatch('[0-9a-f]{40}', source_sha):
        raise ValueError('Invalid maintenance commit')
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '--single-branch', '--branch', 'main',
                    '--', remote, str(output)], check=True)
    base = git(output, 'rev-parse', 'HEAD')
    previous_marker = output/PROVENANCE
    if previous_marker.exists():
        previous = json.loads(previous_marker.read_text())
        if previous.get('owner') != OWNER or previous.get('repository') != REPOSITORY:
            raise ValueError('CNB Homebrew snapshot is not owned by this publisher')
    elif (output/'README.md').read_text().splitlines()[0] != '# Fansionia pacman mirror':
        raise ValueError('Refusing to adopt an unknown CNB repository')
    # Validate all records before uploading any new files.
    for project, info in records.items():
        record = {**info, 'upstream_url': info['url'], 'url': sync.cnb_url(project, info)}
        path = output/'homebrew/releases'/f'{project}.json'
        if path.exists():
            compare(json.loads(path.read_text()), record)
    if client is None:
        # Authenticate receive-pack before downloading or uploading any archives.
        authenticated_push(output, dry_run=True)
        client = Client(REPOSITORY, owner=OWNER, user_agent='fansionia-homebrew-mirror')
    paths = []
    for project, info in records.items():
        with tempfile.TemporaryDirectory(prefix='fansionia-homebrew-assets-') as tmp:
            archive, checksum = source_files(info, Path(tmp))
            for path in (archive, checksum):
                item = {'tag': sync.cnb_tag(project, info), 'title': f"Homebrew · {project} {info['version']}",
                        'filename': path.name, 'sha256': digest(path), 'size': path.stat().st_size}
                client.upload(item, path)
                verify_remote(location(REPOSITORY, item['tag'], item['filename']), item['sha256'])
        relative, text = sync.render(project, info, source='cnb')
        (output/relative).parent.mkdir(parents=True, exist_ok=True)
        (output/relative).write_text(text)
        paths.append(relative)
        relative = f'homebrew/releases/{project}.json'
        write_json(output/relative, {**info, 'upstream_url': info['url'], 'url': sync.cnb_url(project, info)})
        paths.append(relative)
    (output/'README.md').write_text(readme())
    write_json(output/PROVENANCE, {'schema': 1, 'owner': OWNER, 'repository': REPOSITORY, 'source_sha': source_sha})
    paths.extend(['README.md', PROVENANCE])
    write_json(output/'.git'/RECEIPT, {'base': base, 'remote': remote, 'source_sha': source_sha,
                                     'files': {p: digest(output/p) for p in paths}})
    print(f'Prepared verified CNB Homebrew candidate from {source_sha}')


def publish(output):
    output = Path(output).resolve()
    receipt = json.loads((output/'.git'/RECEIPT).read_text())
    if receipt['remote'] != REMOTE or git(output, 'remote', 'get-url', 'origin') != REMOTE:
        raise ValueError('Unexpected CNB publication remote')
    if git(output, 'rev-parse', 'HEAD') != receipt['base']:
        raise ValueError('Candidate base changed after validation')
    for path, expected in receipt['files'].items():
        if digest(output/path) != expected:
            raise ValueError('Candidate files changed after preparation')
    # Never include unrelated user files, test output, credentials or generated caches.
    staged = git(output, 'diff', '--cached', '--name-only').splitlines()
    if any(path not in receipt['files'] for path in staged):
        raise ValueError('Unrelated files staged in candidate')
    git(output, 'add', '--', *receipt['files'])
    if subprocess.run(['git', '-C', str(output), 'diff', '--cached', '--quiet'], check=False).returncode == 0:
        print('CNB Homebrew snapshot already current')
        return
    git(output, '-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', 'chore(homebrew): update verified CNB distribution')
    authenticated_push(output)
    print('Published verified CNB Homebrew snapshot:', git(output, 'rev-parse', 'HEAD'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'publish'])
    parser.add_argument('--output-root', type=Path, default=ROOT/'.work/homebrew-cnb')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.output_root)
        else:
            publish(args.output_root)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f'CNB Homebrew mirror: external command failed (exit {error.returncode})\n')
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'CNB Homebrew mirror: {error}\n')
