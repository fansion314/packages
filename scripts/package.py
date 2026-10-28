#!/usr/bin/env python3
"""Prepare pinned upstream sources and release-local Arch recipes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
IDS = ('bitwarden', 'obsidian', 'motrix', 'deepseek-harness', 'mygo-cloudmusic')
REPOSITORY = 'fansion314/packages'


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def manifest(project):
    if project not in IDS:
        raise ValueError('Unknown package')
    info = json.loads((ROOT/'packages'/project/'manifest.json').read_text())
    if info['id'] != project or not re.fullmatch(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?', info['version']):
        raise ValueError('Invalid package identity/version')
    if type(info['pkgrel']) is not int or info['pkgrel'] < 1:
        raise ValueError('Invalid pkgrel')
    if 'upstream' in info and not re.fullmatch('[a-f0-9]{40}', info['upstream']['commit']):
        raise ValueError('Upstream must be pinned to a full commit')
    return info


def tag(info):
    return f"{info['id']}-v{info['version']}-{info['pkgrel']}"


def parse_tag(value):
    for project in IDS:
        info = manifest(project)
        if value == tag(info):
            return project
    raise ValueError('Tag does not match a package manifest')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def recipes(project, destination, checksum=None, packaging_ref=None, metadata=False):
    info = manifest(project)
    if checksum is not None and not re.fullmatch('[a-f0-9]{64}', checksum):
        raise ValueError('Invalid binary checksum')
    destination = Path(destination)
    values = {'VERSION': info['version'], 'PKGVER': info['version'].replace('-', ''),
              'PKGREL': str(info['pkgrel']), 'TAG': tag(info), 'REPOSITORY': REPOSITORY,
              'PACKAGING_REF': packaging_ref or 'tag='+tag(info),
              'UPSTREAM_COMMIT': info.get('upstream', {}).get('commit', ''),
              'SHA256': checksum or 'SKIP'}
    for source in (ROOT/'packages'/project/'recipes').iterdir():
        target = destination/source.name
        shutil.copytree(source, target, dirs_exist_ok=True)
        text = (source/'PKGBUILD').read_text()
        for name, value in values.items():
            text = text.replace('@'+name+'@', value)
        if re.search(r'@[A-Z_]+@', text):
            raise ValueError('Unexpanded recipe template')
        (target/'PKGBUILD').write_text(text)
        # .SRCINFO is produced by makepkg on the native Arch runner.
        (target/'.SRCINFO').unlink(missing_ok=True)
        if metadata:
            (target/'.SRCINFO').write_text(run('makepkg', '--printsrcinfo', cwd=target)+'\n')
    return destination


def apply(project, source):
    info = manifest(project)
    source = Path(source).resolve()
    if run('git', 'rev-parse', 'HEAD', cwd=source) != info['upstream']['commit']:
        raise ValueError('Unexpected upstream source commit')
    if run('git', 'status', '--porcelain', '--untracked-files=all', cwd=source):
        raise ValueError('Apply patches only to a clean upstream checkout')
    package = ROOT/'packages'/project
    for name in (package/'patches/series').read_text().splitlines():
        if not name or name.startswith('#'):
            continue
        if Path(name).name != name:
            raise ValueError('Unsafe patch path')
        patch = package/'patches'/name
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
    for item in (package/'overlay').rglob('*'):
        if not item.is_file():
            continue
        target = source/item.relative_to(package/'overlay')
        if target.exists():
            raise ValueError(f'Overlay would replace upstream source: {target}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
    recipes(project, source/'aur')
    if json.loads((source/info.get('version_file', 'package.json')).read_text())['version'] != info['version']:
        raise ValueError('Unexpected upstream application version')


def prepare(project, destination):
    info = manifest(project)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Destination already exists')
    if 'upstream' in info:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', str(destination)], check=True)
        subprocess.run(['git', '-C', str(destination), 'fetch', '--depth=1',
                        'https://github.com/'+info['upstream']['repository']+'.git', info['upstream']['commit']], check=True)
        subprocess.run(['git', '-C', str(destination), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
        apply(project, destination)
    else:
        destination.mkdir(parents=True)
        recipes(project, destination)
        package = ROOT/'packages'/project
        if project == 'bitwarden':
            shutil.copytree(package/'.github', destination/'.github')
            for name in ['PKGBUILD']:
                shutil.copy2(destination/'bitwarden-electron-bin'/name, destination/name)
        else:
            shutil.copytree(package/'ci', destination/'ci')


def finalize(project, archive, destination):
    info = manifest(project)
    archive = Path(archive).resolve()
    expected = f"{info['package']}-{info['version'].replace('-', '')}-{info['pkgrel']}-x86_64.pkg.tar.zst"
    if archive.name != expected:
        raise ValueError(f'Unexpected package: {archive.name}, expected {expected}')
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, destination/archive.name)
    recipes(project, destination/'aur', digest(archive), metadata=True)
    bundle = destination/f"{project}-{info['version']}-{info['pkgrel']}-aur.tar.gz"
    with tarfile.open(bundle, 'w:gz') as output:
        output.add(destination/'aur', arcname='aur')
    tracked = run('git', 'ls-files', 'packages/'+project, 'scripts/package.py', cwd=ROOT).splitlines()
    build = {'package': info, 'packaging_commit': run('git', 'rev-parse', 'HEAD', cwd=ROOT),
             'inputs': {name: digest(ROOT/name) for name in tracked},
             'system_electron': None if info.get('runtime') == 'native-go' else run('pacman', '-Q', 'electron'),
             'native_go': run('go', 'version') if info.get('runtime') == 'native-go' else None,
             'toolchain': {name: run(*cmd) for name, cmd in {
                 'node': ['node', '--version'], 'pnpm': ['pnpm', '--version'],
                 'python': ['python', '--version'], 'makepkg': ['makepkg', '--version']}.items()}}
    (destination/'build-info.json').write_text(json.dumps(build, indent=2)+'\n')
    assets = [destination/archive.name, bundle, destination/'build-info.json']
    (destination/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in assets))
    runtime_note = ('Native Go/GTK application; no Electron or WebView runtime. Includes the persistent interface scale setting. Updates use pacman/paru. ' if info.get('runtime') == 'native-go' else 'Uses system Electron; the Electron runtime is not bundled. ')
    (destination/'notes.md').write_text(
        f"{project} {info['version']} packaging revision {info['pkgrel']} for Arch Linux x86_64.\n\n"
        + runtime_note + 'Install the pacman package directly, '
        'or use the source / -bin recipes from the fansionia PKGBUILD repository.\n\n'
        'Build inputs and toolchain versions are recorded in build-info.json. '
        'Published checks include metadata, binary repackaging and the package-specific smoke tests.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['prepare', 'apply', 'recipes']:
        p = sub.add_parser(name)
        p.add_argument('project', choices=IDS)
        p.add_argument('destination')
        if name == 'recipes':
            p.add_argument('--checksum'); p.add_argument('--packaging-ref'); p.add_argument('--metadata', action='store_true')
    p = sub.add_parser('finalize'); p.add_argument('project', choices=IDS); p.add_argument('archive'); p.add_argument('destination')
    p = sub.add_parser('resolve'); p.add_argument('tag')
    args = parser.parse_args()
    if args.command == 'resolve':
        print(parse_tag(args.tag))
    elif args.command == 'recipes':
        recipes(args.project, args.destination, args.checksum, args.packaging_ref, args.metadata)
    elif args.command == 'finalize':
        finalize(args.project, args.archive, args.destination)
    else:
        globals()[args.command](args.project, args.destination)


if __name__ == '__main__':
    main()
