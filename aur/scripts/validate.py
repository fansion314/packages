#!/usr/bin/env python3
"""Validate recipe metadata, and package selected binaries without installing them."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from sync import ROOT, metadata, source_name, version


def command(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def validate_recipe(path):
    subprocess.run(['bash', '-n', 'PKGBUILD'], cwd=path, check=True)
    work = ROOT/'.cache/metadata'/path.name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(path, work)
    generated = metadata(command('makepkg', '--printsrcinfo', cwd=work))
    recorded = metadata((path/'.SRCINFO').read_text())
    if generated != recorded:
        raise ValueError(f'{path.name}: PKGBUILD and .SRCINFO disagree')
    previous = subprocess.run(['git', 'show', f'HEAD:aur/packages/{path.name}/.SRCINFO'], cwd=ROOT,
                              capture_output=True, text=True)
    if previous.returncode == 0:
        comparison = command('vercmp', version(recorded), version(metadata(previous.stdout))).strip()
        if int(comparison) < 0:
            raise ValueError(f'{path.name}: refusing version downgrade')
    for key in ['source', 'source_x86_64']:
        for entry in recorded.get(key, []):
            filename, url = source_name(entry)
            if '://' not in url and not (path/filename).is_file():
                raise ValueError(f'{path.name}: missing local source {filename}')
    print(f'METADATA_OK {path.name} {version(recorded)}', flush=True)


def package_binary(path):
    # Never build into the versioned recipe directory, nor reuse an old pkg/ tree.
    work = ROOT/'.cache/build'/path.name
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(path, work)
    meta = metadata((path/'.SRCINFO').read_text())
    for key in ['source', 'source_x86_64']:
        sums = meta.get(key.replace('source', 'sha256sums', 1), [])
        for entry, digest in zip(meta.get(key, []), sums):
            filename, url = source_name(entry)
            cached = ROOT/'.cache/downloads'/(digest + '-' + url.rsplit('/', 1)[-1])
            if cached.is_file():
                shutil.copyfile(cached, work/filename)
    subprocess.run(['makepkg', '--force', '--nodeps', '--noconfirm'], cwd=work, check=True)
    packages = [Path(name) for name in command('makepkg', '--packagelist', cwd=work).splitlines() if Path(name).is_file()]
    if len(packages) != 1:
        raise ValueError(f'{path.name}: expected exactly one binary package, got {packages}')
    package = packages[0]
    info = metadata(command('bsdtar', '-xOf', str(package), '.PKGINFO'))
    if info['pkgname'] != [path.name] or info['arch'] != ['x86_64']:
        raise ValueError(f'{path.name}: wrong output identity')
    expected = meta['pkgver'][0] + '-' + meta['pkgrel'][0]
    if meta.get('epoch', ['0'])[0] != '0':
        expected = meta['epoch'][0] + ':' + expected
    if info['pkgver'] != [expected]:
        raise ValueError(f'{path.name}: wrong output version')
    entries = command('bsdtar', '-tf', str(package)).splitlines()
    if not any(entry.startswith(('usr/', 'opt/')) for entry in entries):
        raise ValueError(f'{path.name}: empty application payload')
    print(f'PACKAGE_OK {package.name}', flush=True)
    return package


def smoke(packages):
    if not {'dnr-bin', 'dnc-bin'} <= packages.keys():
        return
    stage = ROOT/'.cache/tool-smoke'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    for name in ['dnr-bin', 'dnc-bin']:
        subprocess.run(['bsdtar', '-xf', str(packages[name]), '-C', str(stage)], check=True)
    dnr, dnc = stage/'usr/bin/dnr', stage/'usr/bin/dnc'
    subprocess.run([str(dnr), '--version'], check=True)
    subprocess.run([str(dnc), '--version'], check=True)
    app = stage/'app'
    app.mkdir()
    (app/'main.ts').write_text('const value: string = "AUR_RUNTIME_OK"; console.log(value);\n')
    subprocess.run([str(dnc), str(app), '--entry', 'main.ts', '-o', str(stage/'test.dnp')], check=True)
    assert command(str(dnr), str(stage/'test.dnp')).strip() == 'AUR_RUNTIME_OK'
    if 'pi-dnr-bin' in packages:
        subprocess.run(['bsdtar', '-xf', str(packages['pi-dnr-bin']), '-C', str(stage)], check=True)
        subprocess.run([str(dnr), str(stage/'usr/lib/pi/pi.dnp'), '--version'],
                       env={**os.environ, 'PI_OFFLINE': '1', 'PI_TELEMETRY': '0', 'PI_CODING_AGENT_DIR': str(stage/'pi-config')}, check=True)
    print('DNR_DNC_PI_SMOKE_OK', flush=True)


def main():
    projects = json.loads((ROOT/'sources.json').read_text())['projects']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-bins', action='store_true')
    parser.add_argument('--changed-only', action='store_true')
    parser.add_argument('--project', choices=[p['id'] for p in projects])
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() == 0:
        parser.error('Run as an unprivileged user in Arch Linux x86_64')
    configured = {name for p in projects for name in p['packages']}
    actual = {p.name for p in (ROOT/'packages').iterdir() if (p/'PKGBUILD').exists()}
    if configured != actual:
        raise ValueError('Package inventory differs from sources.json')
    selected = {name for p in projects if not args.project or p['id'] == args.project for name in p['packages']}
    changed_file = ROOT/'.cache/changed.json'
    changed = set(json.loads(changed_file.read_text())) if args.changed_only else configured
    packages = {}
    for name in sorted(selected):
        path = ROOT/'packages'/name
        validate_recipe(path)
        if args.build_bins and name.endswith('-bin') and name in changed:
            packages[name] = package_binary(path)
    smoke(packages)


if __name__ == '__main__':
    main()
