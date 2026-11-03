#!/usr/bin/env python3
"""Publish only verified Clash Momo Windows assets and a signed CNB update feed."""
import argparse
import base64
import binascii
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from cnb_release import Client, location

REPOSITORY = 'fansionia/packages'
SOURCE = 'fansion314/momo'
REMOTE = 'https://cnb.cool/'+REPOSITORY
BRANCH = 'windows-updates'
FEED = 'clash-momo/windows-x64/latest.json'
STATE = 'clash-momo/windows-x64/state.json'
MANIFEST = 'clash-momo-windows-x64-update.json'
OWNER = 'Managed by fansion314/packages windows/mirror.py (schema 1).'
RECEIPT = 'windows-candidate.json'
VERSION_PATTERN = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-([1-9][0-9]*)'
TAG = re.compile('clash-momo-v'+VERSION_PATTERN)
CORE_TAG = re.compile('mihomomo-v'+VERSION_PATTERN)
MAX_SAFE_INTEGER = 2**53-1
SHA256 = re.compile(r'[0-9a-f]{64}')
SHA1 = re.compile(r'[0-9a-f]{40}')
MAX_MANIFEST = 1024*1024


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def git(directory, *args):
    # The signed envelope is an immutable byte artifact, including its line endings.
    return subprocess.check_output(['git', '-c', 'core.autocrlf=false', '-C', str(directory), *args],
                                   text=True, stderr=subprocess.DEVNULL, timeout=120).strip()


def version_key(tag):
    return release_key(tag, TAG)


def release_key(tag, pattern):
    match = pattern.fullmatch(tag) if isinstance(tag, str) else None
    if not match:
        raise ValueError('Invalid Windows release tag')
    key = tuple(map(int, match.groups()))
    if any(number > MAX_SAFE_INTEGER for number in key):
        raise ValueError('Windows release numbers exceed safe integer range')
    return key


def valid_tag(tag):
    try:
        version_key(tag)
        return True
    except ValueError:
        return False


def checked_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate update JSON field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def decode(value):
    if not isinstance(value, str):
        raise ValueError('Invalid update manifest encoding')
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Invalid update manifest encoding') from None
    if base64.b64encode(result).decode() != value:
        raise ValueError('Non-canonical update manifest encoding')
    return result


def validated_manifest(raw, keys=None):
    if len(raw) > MAX_MANIFEST:
        raise ValueError('Update manifest exceeds size limit')
    envelope = checked_json(raw)
    if not isinstance(envelope, dict) or set(envelope) != {'schema', 'keyId', 'payload', 'signature'} \
            or type(envelope['schema']) is not int or envelope['schema'] != 1 \
            or not isinstance(envelope['keyId'], str):
        raise ValueError('Invalid update manifest envelope')
    keys = keys if keys is not None else json.loads((ROOT/'windows/keys.json').read_text())
    if envelope['keyId'] not in keys:
        raise ValueError('Unknown update signing key')
    payload, signature = decode(envelope['payload']), decode(envelope['signature'])
    if len(signature) != 64:
        raise ValueError('Invalid update manifest signature')
    verification = subprocess.run(['node', '-e', '''
const fs = require('node:fs'), crypto = require('node:crypto');
try {
  const v = JSON.parse(fs.readFileSync(0, 'utf8'));
  const key = crypto.createPublicKey({key: Buffer.from(v.key, 'base64'), format: 'der', type: 'spki'});
  if (key.asymmetricKeyType !== 'ed25519' || !crypto.verify(null, Buffer.from(v.payload, 'base64'), key, Buffer.from(v.signature, 'base64'))) process.exit(1);
} catch { process.exit(1); }
'''], input=json.dumps({'key': keys[envelope['keyId']], 'payload': envelope['payload'],
                       'signature': envelope['signature']}), text=True, capture_output=True, timeout=15)
    if verification.returncode:
        raise ValueError('Invalid update manifest signature')
    info = checked_json(payload)
    expected = {'schema', 'product', 'platform', 'arch', 'tag', 'version', 'revision', 'publishedAt',
                'changelog', 'sourceCommit', 'core', 'assets'}
    if not isinstance(info, dict) or set(info) != expected or type(info['schema']) is not int or info['schema'] != 1 \
            or (info['product'], info['platform'], info['arch']) != ('clash-momo', 'win32', 'x64'):
        raise ValueError('Unexpected update product or platform')
    key = version_key(info['tag'])
    if info['version'] != '.'.join(map(str, key[:3])) or type(info['revision']) is not int \
            or info['revision'] != key[3] or not matches(SHA1, info['sourceCommit']):
        raise ValueError('Inconsistent update release identity')
    if not isinstance(info['publishedAt'], str) or not isinstance(info['changelog'], str):
        raise ValueError('Invalid update release description')
    try:
        if datetime.fromisoformat(info['publishedAt'].replace('Z', '+00:00')).utcoffset() is None:
            raise ValueError('Missing timezone')
    except ValueError:
        raise ValueError('Invalid update publication timestamp') from None
    core = info['core']
    if not isinstance(core, dict) or set(core) != {'tag', 'sha256', 'sourceCommit'} \
            or not matches(CORE_TAG, core['tag']) \
            or not matches(SHA256, core['sha256']) or not matches(SHA1, core['sourceCommit']):
        raise ValueError('Invalid paired core identity')
    release_key(core['tag'], CORE_TAG)
    if not isinstance(info['assets'], dict) or set(info['assets']) != {'installer', 'portable'}:
        raise ValueError('Invalid Windows asset set')
    prefix = f'clash-momo-{info["version"]}-{info["revision"]}-windows-x64'
    for kind, suffix in [('installer', '-setup.exe'), ('portable', '-portable.zip')]:
        asset = info['assets'][kind]
        if not isinstance(asset, dict) or set(asset) != {'name', 'size', 'sha256'} \
                or asset['name'] != prefix+suffix or type(asset['size']) is not int \
                or not 0 < asset['size'] <= 2*1024**3 or not matches(SHA256, asset['sha256']):
            raise ValueError('Invalid signed Windows asset')
    return info


def gh(*args):
    # GitHub JSON is UTF-8 even when Windows' active ANSI code page is cp1252.
    return json.loads(subprocess.check_output(['gh', *args], timeout=120))


def git_shell(program='bash'):
    if os.name != 'nt':
        return shutil.which(program) or program
    roots = [Path(value)/'Git' for key in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)')
             if (value := os.environ.get(key))]
    if executable := shutil.which('git'):
        roots.extend([Path(executable).parent.parent, Path(executable).parent])
    for root in roots:
        for relative in ('bin', 'usr/bin'):
            candidate = root/relative/(program+'.exe')
            if candidate.is_file():
                return str(candidate.resolve())
    raise RuntimeError('Git for Windows shell is required; refusing the Windows WSL shell stub')


def source_release(tag=''):
    if tag:
        version_key(tag)
        release = gh('api', f'repos/{SOURCE}/releases/tags/{tag}')
    else:
        pages = gh('api', f'repos/{SOURCE}/releases?per_page=100', '--paginate', '--slurp')
        candidates = [r for page in pages for r in page if valid_tag(r['tag_name'])
                      and not r['draft'] and not r['prerelease']]
        if not candidates:
            raise ValueError('No public stable Clash Momo release')
        release = max(candidates, key=lambda r: version_key(r['tag_name']))
    if release['draft'] or release['prerelease'] or not valid_tag(release['tag_name']):
        raise ValueError('Update source must be a public stable Clash Momo release')
    return release


def download(url, target, expected=None, size=None, limit=2*1024**3):
    request = urllib.request.Request(url, headers={'User-Agent': 'fansionia-windows-mirror'})
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    checksum, length = hashlib.sha256(), 0
    deadline = time.monotonic()+600
    try:
        with urllib.request.urlopen(request, timeout=90) as response, target.open('wb') as stream:
            while block := response.read(1024*1024):
                if time.monotonic() > deadline:
                    raise RuntimeError('Windows asset download exceeded time limit')
                length += len(block)
                if length > limit:
                    raise ValueError('Windows download exceeds size limit')
                stream.write(block)
                checksum.update(block)
    except OSError:
        raise RuntimeError('Anonymous Windows asset download failed') from None
    if (expected is not None and checksum.hexdigest() != expected) or (size is not None and length != size):
        raise ValueError('Windows asset download digest or size mismatch')


def indexed_assets(release):
    result = {}
    for asset in release['assets']:
        if asset['name'] in result:
            raise ValueError('Duplicate GitHub Release attachment')
        result[asset['name']] = asset
    return result


def source_file(assets, name, directory, expected=None, limit=2*1024**3):
    asset = assets.get(name)
    if not asset or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''):
        raise ValueError('Missing Windows Release attachment or GitHub digest: '+name)
    if asset.get('browser_download_url') != f'https://github.com/{SOURCE}/releases/download/{asset["_tag"]}/{name}':
        raise ValueError('Unexpected GitHub asset URL')
    sha = asset['digest'][7:]
    if expected and (expected['sha256'] != sha or expected['size'] != asset['size']):
        raise ValueError('GitHub asset differs from signed update manifest')
    target = directory/name
    download(asset['browser_download_url'], target, sha, asset['size'], limit)
    return target


def askpass_environment(directory):
    askpass = Path(directory)/'askpass.sh'
    askpass.write_text('#!/bin/sh\ncase "$1" in\n *Username*) printf "%s\\n" cnb ;;\n *Password*) printf "%s\\n" "$CNB_MIRROR_TOKEN" ;;\n *) exit 1 ;;\nesac\n', newline='\n')
    askpass.chmod(0o700)
    if os.name == 'nt':
        # GIT_ASKPASS is one executable path, not a shell command. Git for Windows
        # resolves this script's /bin/sh shebang through its bundled shell.
        git_shell('sh')
    return {**os.environ, 'GIT_ASKPASS': askpass.as_posix(), 'GIT_TERMINAL_PROMPT': '0'}


def authenticated_push(output, dry_run=False):
    token = os.environ.get('CNB_MIRROR_TOKEN')
    if not token:
        raise ValueError('CNB_MIRROR_TOKEN is required')
    with tempfile.TemporaryDirectory(prefix='fansionia-windows-auth-') as temporary:
        env = askpass_environment(temporary)
        result = subprocess.run(['git', '-C', str(output), '-c', 'credential.helper=', 'push',
                                 *(['--dry-run'] if dry_run else []), 'origin', 'HEAD:refs/heads/'+BRANCH],
                                env=env, capture_output=True, text=True, timeout=120)
        if result.returncode:
            if any(s in result.stderr.lower() for s in ('401', '403', 'forbidden', 'denied', 'authentication')):
                raise RuntimeError('CNB Git access denied; token needs repo-code:rw and windows-updates branch write access')
            raise RuntimeError('CNB Windows publication failed; verify connectivity or regenerate after remote branch advanced')


def candidate_repository(output, remote):
    if output.exists():
        raise ValueError('Candidate already exists; use a fresh output directory')
    output.mkdir(parents=True)
    git(output, 'init', '--initial-branch='+BRANCH)
    git(output, 'remote', 'add', 'origin', remote)
    existing = subprocess.run(['git', 'ls-remote', '--exit-code', remote, 'refs/heads/'+BRANCH],
                              text=True, capture_output=True, timeout=120)
    if existing.returncode == 0:
        git(output, 'fetch', '--depth=1', 'origin', 'refs/heads/'+BRANCH)
        git(output, 'checkout', '-B', BRANCH, 'FETCH_HEAD')
        if not (output/STATE).exists():
            raise ValueError('Refusing to adopt an unknown Windows update branch')
    elif existing.returncode == 2:
        git(output, '-c', 'user.name=github-actions[bot]',
            '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '--allow-empty', '-m', 'chore(windows): initialize isolated update feed')
    else:
        raise RuntimeError('Cannot inspect public CNB Windows update branch')


def prepare(output, tag='', remote=REMOTE, client=None):
    output = Path(output).resolve()
    release = source_release(tag)
    assets = indexed_assets(release)
    for asset in assets.values():
        asset['_tag'] = release['tag_name']
    candidate_repository(output, remote)
    # Prove branch write permission before fetching installers or uploading any attachment.
    if client is None:
        authenticated_push(output, dry_run=True)
    downloads = output/'.git/windows-downloads'
    downloads.mkdir()
    manifest = source_file(assets, MANIFEST, downloads, limit=MAX_MANIFEST)
    raw = manifest.read_bytes()
    info = validated_manifest(raw)
    if info['tag'] != release['tag_name']:
        raise ValueError('Signed update tag differs from selected release')
    previous = None
    if (output/STATE).exists():
        previous = json.loads((output/STATE).read_text())
        if previous.get('owner') != OWNER or previous.get('repository') != REPOSITORY or previous.get('schema') != 1:
            raise ValueError('Windows update branch ownership differs')
        old_raw = (output/FEED).read_bytes()
        old = validated_manifest(old_raw)
        if version_key(info['tag']) < version_key(old['tag']):
            raise ValueError('Refusing to downgrade Windows update feed')
        if info['tag'] == old['tag']:
            if raw != old_raw:
                raise ValueError('Refusing to replace immutable Windows update manifest')
            return {'changed': False, 'tag': info['tag'], 'source_sha': info['sourceCommit']}
    files = [manifest]
    for signed in info['assets'].values():
        archive = source_file(assets, signed['name'], downloads, signed)
        checksum = source_file(assets, signed['name']+'.sha256', downloads, limit=1024)
        if checksum.read_text().split() not in ([signed['sha256'], signed['name']], [signed['sha256'], '*'+signed['name']]):
            raise ValueError('Windows checksum differs from signed manifest')
        files.extend([archive, checksum])
    name = f'clash-momo-{info["version"]}-{info["revision"]}-windows-x64-manifest.json'
    identity = source_file(assets, name, downloads, limit=MAX_MANIFEST)
    checksum = source_file(assets, name+'.sha256', downloads, limit=1024)
    if checksum.read_text().split() != [digest(identity), name]:
        raise ValueError('Windows core manifest checksum mismatch')
    packaged = checked_json(identity.read_bytes())
    core = packaged.get('core', {}) if isinstance(packaged, dict) else {}
    if not isinstance(packaged, dict) or not isinstance(core, dict) \
            or packaged.get('tag') != info['tag'] or packaged.get('source_commit') != info['sourceCommit'] \
            or packaged.get('architecture') != 'x64' or core.get('tag') != info['core']['tag'] \
            or core.get('core_sha256') != info['core']['sha256'] \
            or core.get('source_commit') != info['core']['sourceCommit']:
        raise ValueError('Packaged client/core identity differs from signed update')
    files.extend([identity, checksum])
    client = client or Client(REPOSITORY, owner=OWNER, user_agent='fansionia-windows-mirror')
    objects, uploaded, reused = {}, 0, 0
    for file in files:
        item = {'tag': 'windows-'+info['tag'], 'title': 'Windows - '+info['tag'],
                'filename': file.name, 'sha256': digest(file), 'size': file.stat().st_size}
        changed = client.upload(item, file)
        uploaded += bool(changed)
        reused += not changed
        url = location(REPOSITORY, item['tag'], item['filename'])
        # Retain anonymously downloaded mirror bytes for the native Windows smoke test.
        download(url, file, item['sha256'], item['size'])
        objects[file.name] = {**item, 'url': url}
    (output/FEED).parent.mkdir(parents=True, exist_ok=True)
    (output/FEED).write_bytes(raw)
    write_json(output/STATE, {'schema': 1, 'owner': OWNER, 'repository': REPOSITORY,
                             'tag': info['tag'], 'objects': objects})
    receipt = {'schema': 1, 'remote': remote, 'branch': BRANCH, 'base': git(output, 'rev-parse', 'HEAD'),
               'tag': info['tag'], 'source_sha': info['sourceCommit'],
               'files': {p: digest(output/p) for p in (FEED, STATE)},
               'download_files': {file.name: digest(file) for file in files}}
    write_json(output/'.git'/RECEIPT, receipt)
    print(f'Prepared Windows mirror: uploaded={uploaded}, reused={reused}; native validation required before feed publication')
    return {'changed': True, 'tag': info['tag'], 'source_sha': info['sourceCommit']}


def publish(output):
    output = Path(output).resolve()
    receipt = json.loads((output/'.git'/RECEIPT).read_text())
    if receipt['remote'] != REMOTE or receipt['branch'] != BRANCH \
            or git(output, 'remote', 'get-url', 'origin') != REMOTE \
            or git(output, 'rev-parse', 'HEAD') != receipt['base']:
        raise ValueError('Windows candidate publication identity changed')
    for name, sha in receipt['files'].items():
        if name not in (FEED, STATE) or digest(output/name) != sha:
            raise ValueError('Windows candidate feed changed after validation')
    for name, sha in receipt['download_files'].items():
        if Path(name).name != name or digest(output/'.git/windows-downloads'/name) != sha:
            raise ValueError('Windows candidate package changed after validation')
    if set(git(output, 'diff', '--cached', '--name-only').splitlines()) - set(receipt['files']):
        raise ValueError('Unrelated files staged in Windows candidate')
    git(output, 'add', '--', *receipt['files'])
    git(output, '-c', 'user.name=github-actions[bot]',
        '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
        'commit', '-m', 'chore(windows): publish verified '+receipt['tag'])
    authenticated_push(output)
    print('Published signed Windows update feed:', receipt['tag'])


def verify_public(output, metadata_only=False):
    output = Path(output).resolve()
    state = json.loads((output/STATE).read_text())
    with tempfile.TemporaryDirectory(prefix='fansionia-windows-public-') as temporary:
        target = Path(temporary)/'latest.json'
        url = REMOTE+'/-/git/raw/'+BRANCH+'/'+FEED
        download(url, target, digest(output/FEED), limit=MAX_MANIFEST)
        validated_manifest(target.read_bytes())
        if not metadata_only:
            for item in state['objects'].values():
                download(item['url'], Path(temporary)/item['filename'], item['sha256'], item['size'])
    print('Public CNB Windows feed verified' if metadata_only else 'Public CNB Windows feed and every mirrored attachment verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'publish', 'verify-public'])
    parser.add_argument('--output-root', type=Path, default=ROOT/'.work/windows-candidate')
    parser.add_argument('--release-tag', default='')
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.output_root, args.release_tag)
            if args.github_output:
                with args.github_output.open('a') as stream:
                    for key, value in result.items():
                        stream.write(f'{key}={str(value).lower() if isinstance(value, bool) else value}\n')
        elif args.command == 'publish':
            publish(args.output_root)
        else:
            verify_public(args.output_root, args.metadata_only)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        message = str(error) if not isinstance(error, subprocess.SubprocessError) else 'external command failed'
        parser.exit(1, 'CNB Windows mirror: '+message+'\n')


if __name__ == '__main__':
    main()
