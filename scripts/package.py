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
import tomllib

ROOT = Path(__file__).resolve().parents[1]
IDS = ('bitwarden', 'obsidian', 'motrix', 'deepseek-harness', 'mygo-music', 'hghub', 'longbridge')
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
    if info.get('runtime') == 'official-binary':
        if not re.fullmatch('[a-f0-9]{64}', info['source']['sha256']):
            raise ValueError('Official binary must have a pinned SHA-256')
        if not info['source']['url'].startswith('https://'):
            raise ValueError('Official binary source requires HTTPS')
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
              'SOURCE_URL': info.get('source', {}).get('url', ''),
              'SOURCE_SHA256': info.get('source', {}).get('sha256', ''),
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


def application_version(source, info):
    path = Path(source)/info.get('version_file', 'package.json')
    if path.suffix == '.ts':
        # Node 24+ strips the configuration's TypeScript annotations. Evaluate
        # the build configuration just as upstream does, rather than extracting
        # a version-like string from executable source or the website manifest.
        output = subprocess.check_output([
            'node', '--input-type=module', '--eval',
            "import {pathToFileURL} from 'node:url'; "
            "const {default: exported} = await import(pathToFileURL(process.argv[1]).href); "
            "const config = await (typeof exported === 'function' "
            "? exported({command: 'build'}) : exported); "
            "process.stdout.write(JSON.stringify(config?.version ?? null));",
            str(path.resolve()),
        ], text=True)
        version = json.loads(output)
    else:
        version = json.loads(path.read_text()).get('version')
    if not isinstance(version, str):
        raise ValueError('Invalid upstream application version')
    if info.get('runtime') == 'tauri-webkitgtk':
        tauri = json.loads((Path(source)/'src-tauri/tauri.conf.json').read_text())
        cargo = tomllib.loads((Path(source)/'src-tauri/Cargo.toml').read_text())
        if tauri.get('version') != version or cargo.get('package', {}).get('version') != version:
            raise ValueError('Tauri and Cargo application versions must match package.json')
    return version


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
    if application_version(source, info) != info['version']:
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
        elif (package/'ci').is_dir():
            shutil.copytree(package/'ci', destination/'ci')


def runtime_metadata(info):
    runtime = info.get('runtime', 'system-electron')
    metadata = {'system_electron': None, 'native_go': None}
    if runtime == 'official-binary':
        metadata['official_binary'] = info['source']
    elif runtime == 'native-go':
        metadata['native_go'] = run('go', 'version')
    elif runtime == 'tauri-webkitgtk':
        metadata['webkitgtk'] = run('pkg-config', '--modversion', 'webkit2gtk-4.1')
        metadata['rust'] = run('rustc', '--version')
        metadata['cargo'] = run('cargo', '--version')
    elif runtime == 'system-electron':
        metadata['system_electron'] = run('pacman', '-Q', 'electron')
    else:
        raise ValueError('Unknown application runtime: '+runtime)
    return metadata


def runtime_note(info):
    runtime = info.get('runtime', 'system-electron')
    if runtime == 'official-binary':
        return ('Repackages the official stable Linux x86_64 binary without rebuilding or modifying it. '
                'Uses system GTK3 and WebKitGTK 4.1; no Electron runtime. '
                'Preserves the upstream com.longbridge.app.desktop application identity. '
                'Launch with longbridge-desktop. Updates use pacman/paru; '
                'disable automatic updates in Settings > General > Software Update. ')
    if runtime == 'native-go':
        return ('Native Go/GTK application; no Electron or WebView runtime. '
                'Includes the persistent interface scale setting. Updates use pacman/paru. ')
    if runtime == 'tauri-webkitgtk':
        return ('Community Linux build with Linux compatibility fixes and persistent interface scale controls. '
                'Uses Tauri 2 and system WebKitGTK 4.1; no Electron runtime. '
                'Preserves the upstream com.hghub.huangguo application identity. Updates use pacman/paru. '
                'Distributed under PolyForm Noncommercial 1.0.0; the full license and Required Notice '
                'are installed under /usr/share/licenses/hghub/LICENSE. ')
    return 'Uses system Electron; the Electron runtime is not bundled. '


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
             **runtime_metadata(info),
             'toolchain': {name: run(*cmd) for name, cmd in {
                 'node': ['node', '--version'], 'pnpm': ['pnpm', '--version'],
                 'python': ['python', '--version'], 'makepkg': ['makepkg', '--version']}.items()}}
    (destination/'build-info.json').write_text(json.dumps(build, indent=2)+'\n')
    assets = [destination/archive.name, bundle, destination/'build-info.json']
    (destination/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in assets))
    migration_note = (
        '\nMyGo Music includes no provider plugins. Install mygo-music manually; '
        'it does not replace MyGo CloudMusic or migrate its accounts, library, '
        'cache or settings. The upstream dev.egoist.music identity uses a separate '
        'data directory, and the old application data remains untouched.\n'
        if project == 'mygo-music' else '')
    project_notes = ROOT/'packages'/project/'release-notes.md'
    if project_notes.is_file():
        migration_note += '\n' + project_notes.read_text().strip() + '\n'
    (destination/'notes.md').write_text(
        f"{project} {info['version']} packaging revision {info['pkgrel']} for Arch Linux x86_64.\n\n"
        + runtime_note(info) + 'Install the pacman package directly, '
        'or use the source / -bin recipes from the fansionia PKGBUILD repository.\n\n'
        'Build inputs and toolchain versions are recorded in build-info.json. '
        'Published checks include metadata, binary repackaging and the package-specific smoke tests.\n'
        + migration_note)


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
