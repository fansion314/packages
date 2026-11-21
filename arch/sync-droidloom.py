#!/usr/bin/env python3
"""Review the Droidloom release inputs and publish Fansionia signatures."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from repository import (ReleaseIncomplete, download, github, package_metadata,
                        release_packages, select_release, version_key)
from sign import api, checksum, release, sign_directory
from upstream import fetch, parse_database, server

ROOT = Path(__file__).resolve().parent
RUNTIME = 'droidloom-runtime'
IMAGE = 'droidloom-image'
BASE = 'droidloom-base'


def upstream_packages(project, architecture):
    source = project['upstream']
    database = server(source, architecture)+'/'+source['id']+'.db'
    packages = {p['name']: p for p in parse_database(fetch(database), source, architecture)}
    if not set(project['packages']) <= packages.keys():
        raise ReleaseIncomplete('Droidloom database is missing a package in the required set')
    upstream = api(f'repos/{source["repository"]}/releases/tags/{source["tag"]}')
    if upstream['draft'] or upstream['tag_name'] != source['tag']:
        raise ReleaseIncomplete('Droidloom upstream release is unavailable')
    assets = {a['name']: a for a in upstream['assets']}
    selected = {}
    for name in project['packages']:
        package = packages[name]
        version = package['version']
        filename = f'{name}-{version}-{architecture}.pkg.tar.zst'
        if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-[0-9]+', version) or \
                package['architecture'] != architecture or package['filename'] != filename:
            raise ValueError('Unexpected Droidloom package identity: '+name)
        asset = assets.get(filename)
        if asset is None:
            raise ReleaseIncomplete('Droidloom release is missing '+filename)
        url = f'https://github.com/{source["repository"]}/releases/download/{source["tag"]}/{filename}'
        if asset['browser_download_url'] != url or asset.get('digest') != 'sha256:'+package['sha256']:
            raise ValueError('Droidloom database and GitHub Release disagree: '+filename)
        selected[name] = dict(package, url=url)
    if selected[RUNTIME]['version'] != selected[IMAGE]['version']:
        raise ReleaseIncomplete('Droidloom runtime and image versions do not match')
    return selected


def check_published(project, published, packages):
    match = {p['name']: p for p in release_packages(project, published, [p['name'] for p in packages])}
    for package in packages:
        existing = match[package['name']]
        if any(existing[key] != package[key] for key in ('version', 'filename', 'sha256')):
            raise ValueError('Droidloom changed a published package without a version bump: '+package['filename'])


def prepare(project, directory, packages, existing):
    if existing and not existing['draft']:
        check_published(project, existing, packages)
        return
    directory.mkdir(parents=True, exist_ok=True)
    for package in packages:
        archive = download(package['url'], directory/package['filename'], package['sha256'])
        fields = package_metadata(package, archive)
        dependency = package.get('required_dependency')
        if dependency and [value for value in fields.get('depend', [])
                           if re.split(r'[<>=]', value, maxsplit=1)[0] == dependency.split('=', 1)[0]] != [dependency]:
            raise ValueError(f'{archive.name} does not require {dependency}')


def publish(project, tag, packages, directory, current, notes):
    if current and not current['draft']:
        return False
    repository = project['repository']
    gh = ['gh', 'release']
    note_file = directory.parent/(tag+'.md')
    note_file.write_text(notes)
    if current is None:
        subprocess.run([*gh, 'create', tag, '-R', repository, '--draft', '--latest=false',
                        '--target', os.environ['GITHUB_SHA'], '--title', tag,
                        '--notes-file', str(note_file)], check=True)
        for _ in range(15):
            current = release(repository, tag)
            if current is not None:
                break
            time.sleep(2)
    if not current or not current['draft'] or current.get('body', '').strip() != notes.strip():
        raise ValueError('Unexpected Droidloom release draft for '+tag)
    sign_directory(directory, repository, tag)
    sums = directory/'SHA256SUMS'
    sums.write_text(''.join(f'{checksum(p)}  {p.name}\n' for p in sorted(directory.iterdir())))
    assets = {a['name']: a for a in current['assets']}
    for path in sorted(directory.iterdir()):
        if path.name in assets:
            if assets[path.name].get('digest') != 'sha256:'+checksum(path):
                raise ValueError('Droidloom release asset differs: '+path.name)
        else:
            subprocess.run([*gh, 'upload', tag, '-R', repository, str(path)], check=True)
    # GitHub gives draft assets temporary URLs until the tag is published.
    uploaded = release(repository, tag)
    uploaded_digests = {a['name']: a.get('digest') for a in uploaded['assets']}
    for path in directory.iterdir():
        if uploaded_digests.get(path.name) != 'sha256:'+checksum(path):
            raise ValueError('Droidloom release upload digest mismatch: '+path.name)
    subprocess.run([*gh, 'edit', tag, '-R', repository, '--draft=false', '--latest=false'], check=True)
    published = api(f'repos/{repository}/releases/tags/{tag}')
    check_published(project, published, packages)
    print('Published', tag, flush=True)
    return True


def sync(settings, directory):
    project = next(p for p in settings['projects'] if p['id'] == 'droidloom')
    packages = upstream_packages(project, settings['architecture'])
    main_version = packages[RUNTIME]['version']
    base_version = packages[BASE]['version']
    main_tag = 'droidloom-v'+main_version
    base_tag = 'droidloom-base-v'+base_version
    packages[RUNTIME]['required_dependency'] = IMAGE+'='+main_version
    packages[IMAGE]['required_dependency'] = BASE+'='+base_version

    releases = [r for page in github(f'repos/{project["repository"]}/releases?per_page=100') for r in page]
    try:
        previous = select_release(project, releases)
    except ReleaseIncomplete:
        previous = []
    for old in previous:
        if version_key(packages[old['name']]['version']) < version_key(old['version']):
            raise ValueError('Droidloom upstream downgraded '+old['name'])
    existing = {r['tag_name']: r for r in releases}
    main_release = existing.get(main_tag)
    base_release = existing.get(base_tag)
    note = (
        'Original x86_64 package archives from the [Droidloom upstream release]'
        '(https://github.com/denialwm/droidloom/releases/tag/packages). '
        'Fansionia Packages verified the upstream repository and release SHA-256 '
        'values and signed these exact bytes. The signatures identify Fansionia as the distributor.\n'
    )
    main_note = f'Droidloom base version: {base_version}\n\n'+note
    if main_release and f'Droidloom base version: {base_version}' not in (main_release.get('body') or '').splitlines():
        raise ValueError('Droidloom changed the base dependency for an existing release')
    grouped = [(base_tag, [packages[BASE]], base_release, note),
               (main_tag, [packages[RUNTIME], packages[IMAGE]], main_release, main_note)]
    # Verify the full update before publishing either of the immutable releases.
    for tag, members, current, _ in grouped:
        prepare(project, directory/tag, members, current)
    changed = False
    # Publish the base first. Discovery follows the base named by the public
    # runtime/image release so it never selects a partially published update.
    for tag, members, current, notes in grouped:
        changed = publish(project, tag, members, directory/tag, current, notes) or changed
    return changed


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='fansionia-droidloom-') as temporary:
        changed = sync(json.loads((ROOT/'sources.json').read_text()), Path(temporary))
    print('changed='+str(changed).lower())
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('changed='+str(changed).lower()+'\n')
