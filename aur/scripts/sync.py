#!/usr/bin/env python3
"""Mirror approved PKGBUILD directories; verify and pin published binary assets."""
import argparse
import base64
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def metadata(text):
    result = defaultdict(list)
    for line in text.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.strip().split('=', 1)
            result[key.strip()].append(value.strip())
    return result


def version(meta):
    return (meta.get('epoch', ['0'])[0] + ':' + meta['pkgver'][0] + '-' + meta['pkgrel'][0])


def safe_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Unsafe package path: {value}')
    return path


def source_name(value):
    alias, separator, url = value.partition('::')
    if not separator:
        url = value
        alias = unquote(urlsplit(url).path.rsplit('/', 1)[-1])
    safe_path(alias)
    return alias, url


class GitHub:
    def __init__(self):
        self.cache = {}

    def api(self, endpoint):
        if endpoint not in self.cache:
            self.cache[endpoint] = json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))
        return self.cache[endpoint]

    def releases(self, repository):
        result = []
        page = 1
        while True:
            values = self.api(f'repos/{repository}/releases?per_page=100&page={page}')
            result.extend(values)
            if len(values) < 100:
                return result
            page += 1

    def asset(self, repository, url):
        prefix = f'https://github.com/{repository}/releases/download/'
        if not url.startswith(prefix):
            raise ValueError(f'Binary source must be this project\'s GitHub Release: {url}')
        tag, separator, name = url[len(prefix):].partition('/')
        if not separator:
            raise ValueError('Invalid release asset URL')
        release = self.api(f'repos/{repository}/releases/tags/{tag}')
        if release['draft']:
            raise ValueError('Draft binary release')
        matches = [asset for asset in release['assets'] if asset['browser_download_url'] == url]
        if len(matches) != 1:
            raise ValueError(f'Release asset is not available: {url}')
        return matches[0]

    def download(self, url, expected):
        if not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError(f'Missing SHA-256 for {url}')
        cache = ROOT/'.cache/downloads'
        cache.mkdir(parents=True, exist_ok=True)
        dest = cache/(expected + '-' + urlsplit(url).path.rsplit('/', 1)[-1])
        if not dest.exists():
            temp = dest.with_suffix(dest.suffix + '.partial')
            subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--connect-timeout', '20',
                            '--max-time', '600', '--silent', '--show-error', '--output', str(temp), url], check=True)
            temp.replace(dest)
        with dest.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'Checksum mismatch: {url}')
        return dest


def digest_of_asset(asset):
    value = asset.get('digest') or ''
    if not re.fullmatch('sha256:[a-f0-9]{64}', value):
        raise ValueError(f'GitHub SHA-256 digest missing for {asset["name"]}')
    return value.removeprefix('sha256:')


def release_key(settings, tag):
    match = re.fullmatch(settings['tag_pattern'], tag)
    if not match:
        raise ValueError('Unexpected release tag')
    major, minor, patch, stage, number, revision = match.groups()
    return (int(major), int(minor), int(patch),
            {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage], int(number or 0), int(revision))


def recipe_files(project, github):
    repository = project['repository']
    if 'release_bundle' in project:
        settings = project['release_bundle']
        releases = [r for r in github.releases(repository) if not r['draft'] and re.fullmatch(settings['tag_pattern'], r['tag_name'])]
        # These published recipe bundles intentionally include the beta channel.
        for release in sorted(releases, key=lambda r: release_key(settings, r['tag_name']), reverse=True):
            assets = [a for a in release['assets'] if a['name'].endswith(settings['asset_suffix'])]
            if not assets:
                continue
            if len(assets) != 1:
                raise ValueError('Ambiguous recipe bundle')
            asset = assets[0]
            file = github.download(asset['browser_download_url'], digest_of_asset(asset))
            files = {}
            with tarfile.open(file) as archive:
                for member in archive:
                    path = str(safe_path(member.name))
                    if member.isdir():
                        continue
                    if not member.isfile() or member.size > 8 * 1024 * 1024 or path in files:
                        raise ValueError(f'Unexpected recipe bundle entry: {path}')
                    files[path] = archive.extractfile(member).read()
            return release['tag_name'], files
        raise ValueError(f'No published recipe bundle for {repository}')

    commit = github.api(f'repos/{repository}/commits/HEAD')['sha']
    tree = github.api(f'repos/{repository}/git/trees/{commit}?recursive=1')
    if tree.get('truncated'):
        raise ValueError('Truncated Git tree')
    files = {}
    for entry in tree['tree']:
        path = entry['path']
        selected = any((path.startswith(directory + '/') if directory else path in ['PKGBUILD', '.SRCINFO'])
                       for directory in project['packages'].values())
        if not selected or entry['type'] == 'tree':
            continue
        safe_path(path)
        if entry['mode'] not in ['100644', '100755'] or entry.get('size', 0) > 8 * 1024 * 1024:
            raise ValueError(f'Unsupported recipe file: {path}')
        blob = github.api(f'repos/{repository}/git/blobs/{entry["sha"]}')
        files[path] = base64.b64decode(blob['content'])
    return commit, files


def pin_binary(files, repository, github):
    srcinfo = files['.SRCINFO'].decode()
    meta = metadata(srcinfo)
    overrides, assets = {}, []
    for key in ['source', 'source_x86_64']:
        if key not in meta:
            continue
        digest_key = key.replace('source', 'sha256sums', 1)
        checksums = meta[digest_key]
        if len(meta[key]) != len(checksums):
            raise ValueError('Every binary source needs a SHA-256 field')
        pinned = []
        downloaded = {}
        for source, expected in zip(meta[key], checksums):
            filename, url = source_name(source)
            if '://' not in url:
                if filename not in files:
                    raise ValueError(f'Missing local binary recipe source {filename}')
                actual = hashlib.sha256(files[filename]).hexdigest()
            else:
                asset = github.asset(repository, url)
                actual = digest_of_asset(asset)
                file = github.download(url, actual)
                downloaded[filename] = file
                assets.append({'url': url, 'sha256': actual, 'size': asset['size']})
            if expected != 'SKIP' and expected != actual:
                raise ValueError(f'Upstream recipe checksum disagrees with released bytes: {source}')
            pinned.append(actual)
        for filename, file in downloaded.items():
            if filename.endswith('.sha256'):
                fields = file.read_text().split()
                if len(fields) != 2 or fields[1] != filename[:-7] or fields[1] not in downloaded:
                    raise ValueError('Invalid release checksum companion')
                with downloaded[fields[1]].open('rb') as stream:
                    if fields[0] != hashlib.file_digest(stream, 'sha256').hexdigest():
                        raise ValueError('Release companion checksum mismatch')
        if pinned != checksums:
            overrides[digest_key] = pinned
    if overrides:
        files['PKGBUILD'] += b'\n# Pinned by fansion314/packages after verifying the published release bytes.\n'
        for key, values in overrides.items():
            files['PKGBUILD'] += (key + '=(' + ' '.join("'" + value + "'" for value in values) + ')\n').encode()
        indexes = defaultdict(int)
        lines = []
        for line in srcinfo.splitlines():
            key = line.strip().partition(' = ')[0]
            if key in overrides:
                line = '\t' + key + ' = ' + overrides[key][indexes[key]]
                indexes[key] += 1
            lines.append(line)
        files['.SRCINFO'] = ('\n'.join(lines) + '\n').encode()
    return assets


def check_local_sources(files):
    meta = metadata(files['.SRCINFO'].decode())
    for key in ['source', 'source_x86_64']:
        for index, source in enumerate(meta.get(key, [])):
            name, url = source_name(source)
            if '://' in url:
                continue
            if name not in files:
                raise ValueError(f'Missing recipe companion: {name}')
            sums = meta.get(key.replace('source', 'sha256sums', 1), [])
            if index < len(sums) and sums[index] != 'SKIP' and hashlib.sha256(files[name]).hexdigest() != sums[index]:
                raise ValueError(f'Local source checksum mismatch: {name}')


def sync(project, github):
    reference, upstream = recipe_files(project, github)
    proposals, records = {}, {}
    state_path = ROOT/'state'/f'{project["id"]}.json'
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    for name, directory in project['packages'].items():
        prefix = directory + '/' if directory else ''
        files = {path[len(prefix):]: data for path, data in upstream.items()
                 if path.startswith(prefix) and (directory or path in ['PKGBUILD', '.SRCINFO'])}
        if not {'PKGBUILD', '.SRCINFO'} <= files.keys():
            raise ValueError(f'Missing PKGBUILD/.SRCINFO for {name}')
        meta = metadata(files['.SRCINFO'].decode())
        if meta['pkgbase'] != [name] or meta['pkgname'] != [name] or meta['arch'] != ['x86_64']:
            raise ValueError(f'Unexpected package identity or architecture: {name}')
        check_local_sources(files)
        assets = pin_binary(files, project['repository'], github) if name.endswith('-bin') else []
        file_digests = {path: hashlib.sha256(data).hexdigest() for path, data in sorted(files.items())}
        previous = old.get('packages', {}).get(name)
        if previous and previous['version'] == version(meta) and previous['assets'] != assets:
            raise ValueError(f'{name}: same-version binary assets changed; upstream must increment pkgrel')
        records[name] = {'version': version(meta), 'files': file_digests, 'assets': assets}
        proposals[name] = files
    # An unrelated upstream commit should not produce another synchronization commit.
    if old.get('packages') == records:
        print(project['id'] + ': unchanged')
        return []
    changed = []
    for name, files in proposals.items():
        if old.get('packages', {}).get(name) == records[name]:
            continue
        target = ROOT/'packages'/name
        target.mkdir(parents=True, exist_ok=True)
        for path in target.rglob('*'):
            if path.is_file() and str(path.relative_to(target)) not in files:
                path.unlink()
        for path, content in files.items():
            dest = target/str(safe_path(path))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        changed.append(name)
    for retired in set(old.get('packages', {})) - set(proposals):
        safe_path(retired)
        target = ROOT/'packages'/retired
        if target.is_dir():
            shutil.rmtree(target)
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps({'repository': project['repository'], 'reference': reference, 'packages': records}, indent=2) + '\n')
    print(project['id'] + ': ' + ', '.join(changed))
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('projects', nargs='*')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'sources.json').read_text())
    projects = manifest['projects']
    if set(args.projects) - {p['id'] for p in projects}:
        parser.error('Unknown project')
    github = GitHub()
    changed = []
    for project in projects:
        if not args.projects or project['id'] in args.projects:
            changed.extend(sync(project, github))
    cache = ROOT/'.cache'
    cache.mkdir(exist_ok=True)
    (cache/'changed.json').write_text(json.dumps(changed) + '\n')


if __name__ == '__main__':
    main()
