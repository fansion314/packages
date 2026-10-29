#!/usr/bin/env python3
"""Build immutable pacman snapshots from signed, unmodified GitHub assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from sign import Signer, checksum

ROOT = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def github(path):
    return json.loads(subprocess.check_output(['gh', 'api', '--paginate', '--slurp',
                                              '-H', 'Cache-Control: no-cache', path]))


def version_key(tag):
    # Package tags have fixed, validated prefixes; numeric ordering includes the
    # prerelease channel and packaging revision instead of publication dates.
    version = tag.split('-v', 1)[-1].removeprefix('v')
    match = re.fullmatch(r'(\d+)(?:\.(\d+)\.(\d+))?(?:-(alpha|beta|rc)\.(\d+))?(?:-(?:dnr\.)?(\d+))?', version)
    if not match:
        raise ValueError('Cannot order release tag: '+tag)
    major, minor, patch, channel, pre, packaging = match.groups()
    return (int(major), int(minor or 0), int(patch or 0),
            {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[channel], int(pre or 0), int(packaging or 1))


def select_release(project, releases):
    matches = [r for r in releases if not r['draft'] and re.fullmatch(project['tag_pattern'], r['tag_name'])]
    if not matches:
        raise ValueError('No public release for '+project['id'])
    release = max(matches, key=lambda r: version_key(r['tag_name']))
    assets = {a['name']: a for a in release['assets']}
    result = []
    for name in project['packages']:
        # Arch pkgver cannot contain '-'. Requiring a numeric version start
        # prevents dnr from also matching dnr-cef and dnr-webview archives.
        pattern = re.compile(re.escape(name)+r'-([0-9][A-Za-z0-9.+_~]*)-(\d+)-(x86_64|any)\.pkg\.tar\.zst')
        packages = [(asset, pattern.fullmatch(asset['name'])) for asset in assets.values()]
        packages = [(asset, match) for asset, match in packages if match]
        if len(packages) != 1:
            raise ValueError(f'Expected exactly one {name} package in {release["tag_name"]}')
        asset, match = packages[0]
        signature = assets.get(asset['name']+'.sig')
        if not signature:
            raise ValueError('Release is not completely signed: '+asset['name'])
        record = {'project': project['id'], 'repository': project['repository'], 'tag': release['tag_name'],
                  'name': name, 'version': match[1]+'-'+match[2], 'architecture': match[3],
                  'filename': asset['name']}
        for prefix, item in [('', asset), ('signature_', signature)]:
            digest = item.get('digest') or ''
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise ValueError('Missing GitHub asset digest')
            url = ('https://github.com/'+project['repository']+'/releases/download/'
                   +urllib.parse.quote(release['tag_name'], safe='')+'/'+urllib.parse.quote(item['name'], safe=''))
            if urllib.parse.unquote(item['browser_download_url']) != urllib.parse.unquote(url):
                raise ValueError('Unexpected GitHub asset download URL')
            record[prefix+'url'] = url
            record[prefix+'sha256'] = digest.removeprefix('sha256:')
        result.append(record)
    return result


def discover(settings):
    releases = {}
    packages = []
    for project in settings['projects']:
        repository = project['repository']
        if repository not in releases:
            releases[repository] = [r for page in github(f'repos/{repository}/releases?per_page=100') for r in page]
        packages.extend(select_release(project, releases[repository]))
    filenames = [p['filename'] for p in packages]
    names = [p['name'] for p in packages]
    if len(filenames) != len(set(filenames)) or len(names) != len(set(names)):
        raise ValueError('Duplicate package name or filename')
    return sorted(packages, key=lambda p: p['name'])


def download(url, destination, expected):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and checksum(destination) == expected:
        return destination
    temporary = destination.with_name(destination.name+'.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'fansionia-packages-ci'})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as output:
        shutil.copyfileobj(response, output)
    if checksum(temporary) != expected:
        temporary.unlink()
        raise ValueError('Downloaded asset checksum mismatch: '+url)
    temporary.replace(destination)
    return destination


def verify_package(package, archive, public_key):
    metadata = subprocess.check_output(['bsdtar', '-xOf', str(archive), '.PKGINFO'], text=True)
    fields = {}
    for line in metadata.splitlines():
        if ' = ' in line:
            key, value = line.split(' = ', 1)
            fields.setdefault(key, []).append(value)
    for field, expected in [('pkgname', package['name']), ('pkgver', package['version']),
                            ('arch', package['architecture'])]:
        if fields.get(field) != [expected]:
            raise ValueError('Package metadata mismatch: '+field)
    status = subprocess.check_output(['gpgv', '--status-fd', '1', '--keyring', str(public_key),
                                      str(archive)+'.sig', str(archive)], text=True)
    signer = json.loads((ROOT/'keys/signers.json').read_text())[package['repository']]
    if not any(line.startswith('[GNUPG:] VALIDSIG '+signer+' ') for line in status.splitlines()):
        raise ValueError('Package was signed by a different source repository subkey')
    return fields


def previous_manifest(site, active):
    if not active:
        return None
    path = site/'snapshots'/active/'manifest.json'
    if not path.is_file():
        raise ValueError('Active snapshot was not retained in publication state')
    return json.loads(path.read_text())


def ensure_monotonic(packages, previous, compare=None):
    compare = compare or (lambda a, b: int(subprocess.check_output(['vercmp', a, b], text=True)))
    old = {p['name']: p for p in previous['packages']} if previous else {}
    for package in packages:
        before = old.get(package['name'])
        if not before:
            continue
        order = compare(package['version'], before['version'])
        if order < 0:
            raise ValueError('Refusing package downgrade: '+package['name'])
        if order == 0 and any(package[k] != before[k] for k in ['sha256', 'url', 'filename']):
            raise ValueError('Refusing same-version package replacement: '+package['name'])


def snapshot_inputs(packages):
    source = Path(__file__).read_bytes()+ROOT.joinpath('worker.mjs').read_bytes()
    for filename in ['mirror.py', 'sources.json']:
        if (ROOT/filename).exists():
            source += (ROOT/filename).read_bytes()
    generator = hashlib.sha256(source).hexdigest()
    inputs = {'schema': 1, 'packages': packages, 'generator': generator,
              'keyring': checksum(ROOT/'keys/fansionia.gpg')}
    return inputs, hashlib.sha256(canonical(inputs)).hexdigest()[:32]


def build(site, settings, active, resume=''):
    site = Path(site)
    site.mkdir(parents=True, exist_ok=True)
    if resume:
        manifest_path = site/'snapshots'/resume/'manifest.json'
        if not re.fullmatch(r'[0-9a-f]{32}', resume) or not manifest_path.is_file():
            raise ValueError('Pending snapshot is missing from persisted state')
        existing = json.loads(manifest_path.read_text())
        packages = existing['packages']
    else:
        packages = discover(settings)
    previous = previous_manifest(site, active)
    ensure_monotonic(packages, previous)
    # Changes in inputs, generator or public signing material require a new
    # snapshot. Repeated release notifications reuse the existing signed bytes.
    if resume:
        inputs = {k: v for k, v in existing.items() if k != 'files'}
        snapshot = resume
    else:
        inputs, snapshot = snapshot_inputs(packages)
    manifest_path = site/'snapshots'/snapshot/'manifest.json'
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        if any(existing[k] != inputs[k] for k in inputs):
            raise ValueError('Snapshot identity collision')
    else:
        target = manifest_path.parent
        target.mkdir(parents=True)
        database_dir = target/settings['architecture']
        database_dir.mkdir()
        with tempfile.TemporaryDirectory(prefix='fansionia-inputs-') as temporary:
            temporary = Path(temporary)
            archives = []
            for package in packages:
                archive = temporary/package['filename']
                for prefix, destination in [('', archive), ('signature_', Path(str(archive)+'.sig'))]:
                    cache = ROOT.parent/'.cache/pacman-downloads'/package[prefix+'sha256']
                    download(package[prefix+'url'], cache, package[prefix+'sha256'])
                    shutil.copy2(cache, destination)
                verify_package(package, archive, ROOT/'keys/fansionia.gpg')
                archives.append(str(archive))
            database = database_dir/(settings['repository']+'.db.tar.gz')
            subprocess.run(['repo-add', '--include-sigs', str(database), *archives], check=True)
        files = database_dir/(settings['repository']+'.files.tar.gz')
        with Signer() as signer:
            signer.sign(database)
            signer.sign(files)
        # GitHub Pages artifacts cannot contain symlinks produced by repo-add.
        for suffix in ['db', 'files']:
            archive = database_dir/(settings['repository']+'.'+suffix+'.tar.gz')
            for extension in ['', '.sig']:
                alias = database_dir/(settings['repository']+'.'+suffix+extension)
                alias.unlink(missing_ok=True)
                shutil.copy2(str(archive)+extension, alias)
        inputs['files'] = {str(p.relative_to(target)): checksum(p) for p in database_dir.iterdir() if p.is_file()}
        write_json(manifest_path, inputs)
    index_path = site/'snapshots.json'
    snapshots = json.loads(index_path.read_text()) if index_path.exists() else []
    if snapshot not in snapshots:
        snapshots.append(snapshot)
    keep = settings['keep_snapshots']
    retained = snapshots[-keep:]
    if active and active not in retained:
        # A failed candidate must never evict the still-active database.
        retained = [active]+[s for s in retained if s != active][-keep+1:]
    for item in (site/'snapshots').iterdir():
        if item.name not in retained:
            shutil.rmtree(item)
    write_json(index_path, retained)
    shutil.copytree(ROOT/'keys', site/'keys', dirs_exist_ok=True)
    (site/'.nojekyll').touch()
    (site/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Fansionia packages</title>'
                                 '<a href="https://packages.fansionia.world/">Repository setup</a>\n')
    print(json.dumps({'candidate': snapshot, 'active': active, 'changed': snapshot != active}))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write(f'candidate={snapshot}\nchanged={str(snapshot != active).lower()}\n')


def worker(site, settings, active, candidate, phase, destination):
    site = Path(site)
    snapshots = json.loads((site/'snapshots.json').read_text())
    selected = active if phase == 'prepare' and active else candidate
    if selected not in snapshots or candidate not in snapshots:
        raise ValueError('Worker would refer to an unpublished snapshot')
    assets = {}
    for snapshot in snapshots:
        manifest = json.loads((site/'snapshots'/snapshot/'manifest.json').read_text())
        for package in manifest['packages']:
            for suffix, field in [('', 'url'), ('.sig', 'signature_url')]:
                path = '/'+settings['architecture']+'/'+package['filename']+suffix
                url = package[field]
                if path in assets and assets[path] != url:
                    raise ValueError('Conflicting immutable package mapping')
                assets[path] = url
    manifest = json.loads((site/'snapshots'/selected/'manifest.json').read_text())
    for filename in manifest['files']:
        assets['/'+filename] = settings['pages_url']+'/snapshots/'+selected+'/'+filename
    for key in (site/'keys').iterdir():
        if key.is_file():
            assets['/keys/'+key.name] = settings['pages_url']+'/keys/'+key.name
    mirror_snapshots = []
    if settings.get('mirror'):
        from mirror import routes
        mirror_assets, mirror_snapshots = routes(site, settings, selected)
        assets.update(mirror_assets)
    fingerprint = (ROOT/'keys/fingerprint.txt').read_text().strip()
    instructions = (f'Fansionia Arch Linux / CachyOS repository\n\nSigning key: {fingerprint}\n'
                    f'Public key: {settings["public_url"]}/keys/fansionia.asc\n'
                    'Verify the fingerprint against https://github.com/fansion314/packages before trusting it.\n\n'
                    'sudo pacman-key --add fansionia.asc\n'
                    f'sudo pacman-key --lsign-key {fingerprint}\n\n'
                    f'[{settings["repository"]}]\nSigLevel = Required TrustedOnly\n'
                    f'Server = {settings["public_url"]}/$arch\n\n'
                    f'CNB mirror: Server = {settings["public_url"]}/mirror/$arch\n'
                    f'Mirror signing key: {settings["public_url"]}/mirror/keys/fansionia.asc\n\n'
                    'sudo pacman -Syu fansionia-keyring\n'
                    'sudo pacman -S dnr pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron\n')
    config = {'schema': 1, 'active': selected, 'candidate': candidate, 'phase': phase,
              'snapshots': snapshots, 'assets': assets, 'instructions': instructions}
    if settings.get('mirror'):
        config['mirror'] = {'repository': settings['mirror']['repository'], 'active': selected,
                            'snapshots': mirror_snapshots}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text((ROOT/'worker.mjs').read_text()+'\nconst config = '+canonical(config).decode()
                           +';\nexport default createWorker(config);\n')
    write_json(destination.with_suffix('.json'), config)


def verify_pages(site, settings, candidate):
    manifest = json.loads((Path(site)/'snapshots'/candidate/'manifest.json').read_text())
    with tempfile.TemporaryDirectory() as temporary:
        for filename, digest in manifest['files'].items():
            download(settings['pages_url']+'/snapshots/'+candidate+'/'+filename,
                     Path(temporary)/filename, digest)
        for suffix in ['db', 'files']:
            path = Path(temporary)/settings['architecture']/(settings['repository']+'.'+suffix)
            subprocess.run(['gpgv', '--keyring', str(ROOT/'keys/fansionia.gpg'), str(path)+'.sig', str(path)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['probe', 'build', 'worker', 'verify-pages'])
    parser.add_argument('--site', default='.work/pacman-site')
    parser.add_argument('--active', default='')
    parser.add_argument('--candidate', default='')
    parser.add_argument('--phase', choices=['prepare', 'active'], default='prepare')
    parser.add_argument('--output', default='arch/generated/index.mjs')
    args = parser.parse_args()
    settings = json.loads((ROOT/'sources.json').read_text())
    if args.command == 'probe':
        from state import public_status, mirror_state
        status = public_status()
        active = status.get('active', '')
        state = mirror_state() if settings.get('mirror') else {}
        resume = state.get('pending') or (active if state.get('cleanup_pending') else '')
        _, candidate = snapshot_inputs(discover(settings)) if not resume else ({}, resume)
        changed = candidate != active or bool(resume) or os.environ.get('FORCE_PUBLISH') == 'true'
        print('Candidate snapshot:', candidate, 'active:', active or '(none)')
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write(f'changed={str(changed).lower()}\nresume={resume}\n')
    elif args.command == 'build':
        build(args.site, settings, args.active, args.candidate)
    elif args.command == 'worker':
        worker(args.site, settings, args.active, args.candidate, args.phase, args.output)
    else:
        verify_pages(args.site, settings, args.candidate)
