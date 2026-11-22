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
ACCEPTANCE = 'homebrew/accepted.json'


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


def managed_files(records):
    result = {'README.md': readme()}
    for project, info in records.items():
        relative, text = sync.render(project, info, source='cnb')
        result[relative] = text
        result[f'homebrew/releases/{project}.json'] = json.dumps(
            {**info, 'upstream_url': info['url'], 'url': sync.cnb_url(project, info)},
            indent=2, sort_keys=True)+'\n'
    return result


def content_identity(files):
    policy = hashlib.sha256()
    for filename in ['mirror.py', 'sync.py', 'test-install.sh', 'test-switch.sh', 'test-clash-momo.sh']:
        policy.update((Path(__file__).parent/filename).read_bytes())
    return hashlib.sha256(json.dumps({'files': files, 'policy': policy.hexdigest()},
                                     sort_keys=True).encode()).hexdigest()


def public_object(url, expected_size):
    request = urllib.request.Request(url, method='HEAD', headers={
        'User-Agent': 'fansionia-homebrew-mirror', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=30) as response:
        size = response.headers.get('Content-Length')
        if size is None or int(size) != expected_size:
            raise ValueError('CNB anonymous attachment size changed')


def prepare(output, source=ROOT, remote=REMOTE, client=None, full=False):
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
    previous = json.loads(previous_marker.read_text()) if previous_marker.exists() else {}
    if previous:
        if previous.get('owner') != OWNER or previous.get('repository') != REPOSITORY:
            raise ValueError('CNB Homebrew snapshot is not owned by this publisher')
    elif (output/'README.md').read_text().splitlines()[0] != '# Fansionia pacman mirror':
        raise ValueError('Refusing to adopt an unknown CNB repository')
    files = managed_files(records)
    identity = content_identity(files)
    accepted_path = output/ACCEPTANCE
    accepted = json.loads(accepted_path.read_text()) if accepted_path.exists() else {}
    current = all((output/path).is_file() and (output/path).read_text() == text for path, text in files.items())
    needed = full or not current or previous.get('identity') != identity or accepted.get('identity') != identity
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(f'needed={str(needed).lower()}\nidentity={identity}\n')
    if not needed:
        print('CNB Homebrew content already publicly accepted; skipping downloads and installation')
        return {'needed': False, 'identity': identity, 'projects': []}
    changed = {}
    for project, info in records.items():
        relative, text = sync.render(project, info, source='cnb')
        changed[project] = hashlib.sha256(text.encode()).hexdigest()
        record = json.loads(files[f'homebrew/releases/{project}.json'])
        path = output/'homebrew/releases'/f'{project}.json'
        if path.exists():
            compare(json.loads(path.read_text()), record)
    accepted_projects = accepted.get('projects', {}) if accepted.get('policy') == policy_identity() else {}
    projects = sync.validation_projects(changed, accepted_projects, full)
    if not projects:
        projects = ['mihomomo']
    if client is None:
        authenticated_push(output, dry_run=True)
        client = Client(REPOSITORY, owner=OWNER, user_agent='fansionia-homebrew-mirror')
    objects = dict(previous.get('objects', {}))
    transferred = reused = 0
    for project, info in records.items():
        tag = sync.cnb_tag(project, info)
        names = [info['asset'], info['asset']+'.sha256']
        reusable = []
        for name in names:
            url = location(REPOSITORY, tag, name)
            receipt = objects.get(url)
            valid = bool(receipt and receipt.get('verified') and receipt.get('asset_id') is not None)
            if valid and name == info['asset'] and receipt['sha256'] != info['sha256']:
                raise ValueError('Refusing to replace immutable CNB archive receipt')
            if valid and not full:
                asset = client.asset(receipt)
                valid = bool(asset and str(asset['id']) == str(receipt['asset_id']))
                if valid:
                    public_object(url, receipt['size'])
            reusable.append(valid and not full)
        if all(reusable):
            reused += 2
            continue
        with tempfile.TemporaryDirectory(prefix='fansionia-homebrew-assets-') as tmp:
            archive, checksum = source_files(info, Path(tmp))
            for path, reuse in zip((archive, checksum), reusable):
                if reuse:
                    reused += 1
                    continue
                item = {'tag': tag, 'title': f"Homebrew · {project} {info['version']}",
                        'filename': path.name, 'sha256': digest(path), 'size': path.stat().st_size}
                client.upload(item, path)
                url = location(REPOSITORY, tag, path.name)
                verify_remote(url, item['sha256'])
                asset = client.asset(item, refresh=True)
                if asset is None:
                    raise ValueError('CNB attachment disappeared after verification')
                objects[url] = {**item, 'verified': True, 'asset_id': asset['id']}
                transferred += item['size']
    for relative, text in files.items():
        (output/relative).parent.mkdir(parents=True, exist_ok=True)
        (output/relative).write_text(text)
    write_json(output/PROVENANCE, {'schema': 1, 'owner': OWNER, 'repository': REPOSITORY,
        'source_sha': source_sha if not current or previous.get('identity') != identity else previous['source_sha'],
        'identity': identity, 'objects': objects})
    paths = [*files, PROVENANCE]
    receipt = {'base': base, 'remote': remote, 'source_sha': source_sha, 'identity': identity,
               'projects': projects, 'project_inputs': changed,
               'files': {path: digest(output/path) for path in paths}}
    write_json(output/'.git'/RECEIPT, receipt)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('projects='+json.dumps(projects)+'\n')
    summary = f'Homebrew CNB downloaded verification bytes {transferred}; reused {reused} attachments'
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary+'\n')
    return {'needed': True, 'identity': identity, 'projects': projects}


def policy_identity():
    return content_identity({})


def accept(output, expected):
    output = Path(output).resolve()
    if git(output, 'remote', 'get-url', 'origin') != REMOTE:
        raise ValueError('Unexpected CNB acceptance remote')
    if git(output, 'diff', '--cached', '--name-only'):
        raise ValueError('Unexpected staged files before recording acceptance')
    provenance = json.loads((output/PROVENANCE).read_text())
    records = {project: json.loads((output/'homebrew/releases'/f'{project}.json').read_text())
               for project in sync.PROJECTS}
    # Convert mirror records back to the exact upstream records used by rendering.
    records = {p: {k: v for k, v in dict(info, url=info['upstream_url']).items() if k != 'upstream_url'}
               for p, info in records.items()}
    files = managed_files(records)
    if provenance.get('identity') != expected or content_identity(files) != expected or any(
            (output/path).read_text() != text for path, text in files.items()):
        raise ValueError('Public Homebrew content changed after installation tests')
    projects = {p: hashlib.sha256(sync.render(p, info, source='cnb')[1].encode()).hexdigest()
                for p, info in records.items()}
    write_json(output/ACCEPTANCE, {'schema': 1, 'identity': expected, 'policy': policy_identity(), 'projects': projects})
    git(output, 'add', '--', ACCEPTANCE)
    if subprocess.run(['git', '-C', str(output), 'diff', '--cached', '--quiet'], check=False).returncode:
        git(output, '-c', 'user.name=github-actions[bot]', '-c',
            'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '-m', 'chore(homebrew): record public installation acceptance')
        authenticated_push(output)


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
    parser.add_argument('command', choices=['prepare', 'publish', 'accept'])
    parser.add_argument('--output-root', type=Path, default=ROOT/'.work/homebrew-cnb')
    parser.add_argument('--identity', default='')
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.output_root, full=args.full)
        elif args.command == 'accept':
            accept(args.output_root, args.identity)
        else:
            publish(args.output_root)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f'CNB Homebrew mirror: external command failed (exit {error.returncode})\n')
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'CNB Homebrew mirror: {error}\n')
