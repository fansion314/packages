#!/usr/bin/env python3
"""Mirror immutable pacman bytes to CNB Releases; prune only after acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from repository import ROOT, canonical, download, write_json
from sign import checksum

API = 'https://api.cnb.cool'
OWNER = 'Managed by fansion314/packages arch/mirror.py (schema 1).'
STATE = 'mirror-state.json'


def quote(value):
    return urllib.parse.quote(value, safe='')


def location(repository, tag, filename):
    return f'https://cnb.cool/{repository}/-/releases/download/{quote(tag)}/{quote(filename)}'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        return None


class Client:
    def __init__(self, repository, token=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', repository):
            raise ValueError('Invalid CNB repository')
        self.repository = repository
        self.token = token or os.environ.get('CNB_MIRROR_TOKEN')
        if not self.token:
            raise ValueError('CNB_MIRROR_TOKEN is required')
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, data=None, missing=False):
        # Never follow a redirect with the bearer token or include API response
        # bodies / pre-signed upload URLs in exceptions and Actions logs.
        url = API+path if path.startswith('/') else path
        if not url.startswith(API+'/'+self.repository+'/-/releases'):
            raise ValueError('CNB API request outside the configured Release scope')
        request = urllib.request.Request(url, method=method,
            data=canonical(data) if data is not None else None,
            headers={'Authorization': 'Bearer '+self.token, 'Accept': 'application/vnd.cnb.api+json',
                     'Content-Type': 'application/json', 'User-Agent': 'fansionia-pacman-mirror'})
        try:
            with self.opener.open(request, timeout=90) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise RuntimeError(f'CNB Release API {method} failed: HTTP {error.code}') from None
        except (OSError, ValueError):
            raise RuntimeError(f'CNB Release API {method} failed') from None

    def release(self, tag, create=False):
        path = f'/{self.repository}/-/releases'
        result = self.request('GET', path+'/tags/'+quote(tag), missing=True)
        if result is None and create:
            result = self.request('POST', path, {'tag_name': tag, 'target_commitish': 'main',
                'name': tag, 'body': OWNER, 'draft': False, 'make_latest': 'false'})
        if result is not None and result.get('body') != OWNER:
            raise ValueError('CNB release is not owned by the mirror: '+tag)
        return result

    def upload(self, item, source):
        release = self.release(item['tag'], create=True)
        matches = [a for a in (release.get('assets') or []) if a['name'] == item['filename']]
        if len(matches) > 1:
            raise ValueError('Duplicate CNB attachment')
        if matches:
            asset = matches[0]
            if asset['size'] != item['size']:
                raise ValueError('Refusing to overwrite a different CNB attachment')
            if (asset.get('hash_algo') or '').lower().replace('-', '') == 'sha256' and \
                    asset['hash_value'].lower() != item['sha256']:
                raise ValueError('Refusing to overwrite a different CNB digest')
            # Full anonymous SHA-256 verification below also handles servers
            # that report a different hash algorithm, or no hash metadata.
            return False
        prefix = f'/{self.repository}/-/releases/{quote(str(release["id"]))}'
        result = self.request('POST', prefix+'/asset-upload-url', {
            'asset_name': item['filename'], 'size': item['size'], 'overwrite': False, 'ttl': 0})
        upload = urllib.parse.urlsplit(result['upload_url'])
        if upload.scheme != 'https' or not upload.hostname or upload.username:
            raise ValueError('Invalid CNB upload location')
        try:
            with Path(source).open('rb') as body:
                request = urllib.request.Request(result['upload_url'], data=body, method='PUT',
                    headers={'Content-Length': str(item['size']), 'Content-Type': 'application/octet-stream'})
                with self.opener.open(request, timeout=600) as response:
                    response.read()
        except (OSError, ValueError):
            raise RuntimeError('CNB attachment upload failed; retry the publication') from None
        verify = urllib.parse.urlsplit(result['verify_url'])
        if verify.scheme != 'https' or verify.netloc != 'api.cnb.cool' or \
                not verify.path.startswith(prefix+'/asset-upload-confirmation/'):
            raise ValueError('Invalid CNB upload confirmation location')
        # Set permanent retention explicitly at both steps. Store only the
        # stable public download URL, never this temporary credential.
        query = dict(urllib.parse.parse_qsl(verify.query))
        query['ttl'] = '0'
        self.request('POST', verify.path+'?'+urllib.parse.urlencode(query))
        return True

    def delete(self, item):
        release = self.release(item['tag'])
        if release is None:
            return
        prefix = f'/{self.repository}/-/releases/{quote(str(release["id"]))}'
        for asset in (release.get('assets') or []):
            if asset['name'] == item['filename']:
                self.request('DELETE', prefix+'/assets/'+quote(str(asset['id'])))
        # A user may have added other attachments: leave those untouched.
        release = self.release(item['tag'])
        if release is not None and not release.get('assets'):
            self.request('DELETE', prefix)


def read_state(site, settings):
    path = Path(site)/STATE
    if path.exists():
        state = json.loads(path.read_text())
        if state['schema'] != 1 or state['repository'] != settings['mirror']['repository']:
            raise ValueError('CNB mirror state identity changed')
        return state
    return {'schema': 1, 'repository': settings['mirror']['repository'], 'successful': [],
            'pending': '', 'cleanup_pending': False, 'snapshots': {}, 'objects': {}, 'keys': {}}


def snapshot_plan(site, settings, snapshot):
    if not re.fullmatch(r'[0-9a-f]{32}', snapshot):
        raise ValueError('Invalid mirror snapshot identity')
    base = Path(site)/'snapshots'/snapshot
    manifest = json.loads((base/'manifest.json').read_text())
    result = {}
    for package in manifest['packages']:
        # Source identity is hashed so repositories/tags cannot collide even
        # when their human-readable names contain the same separators.
        identity = hashlib.sha256(canonical([package['repository'], package['tag']])).hexdigest()[:32]
        tag = 'pacman-package-'+identity
        for suffix, prefix in [('', ''), ('.sig', 'signature_')]:
            name = package['filename']+suffix
            result['/'+settings['architecture']+'/'+name] = {
                'tag': tag, 'filename': name, 'sha256': package[prefix+'sha256'],
                'source': package[prefix+'url']}
    for filename, digest in manifest['files'].items():
        name = Path(filename).name
        if filename != settings['architecture']+'/'+name:
            raise ValueError('Unexpected database path')
        result['/'+filename] = {'tag': 'pacman-snapshot-'+snapshot, 'filename': name,
            'sha256': digest, 'local': str(base/filename)}
    # Keep the exact source manifest with the snapshot, but do not expose it as
    # a flat pacman route. It is also included in garbage-collection references.
    result['/manifest.json'] = {'tag': 'pacman-snapshot-'+snapshot, 'filename': 'manifest.json',
        'sha256': checksum(base/'manifest.json'), 'local': str(base/'manifest.json')}
    return result


def key_plan(site):
    keys = {p.name: checksum(p) for p in (Path(site)/'keys').iterdir() if p.is_file()}
    tag = 'pacman-keys-'+hashlib.sha256(canonical(keys)).hexdigest()[:32]
    return {'/keys/'+name: {'tag': tag, 'filename': name, 'sha256': digest,
                          'local': str(Path(site)/'keys'/name)} for name, digest in keys.items()}


def stage(site, settings, active, candidate):
    state = read_state(site, settings)
    if state['pending'] and state['pending'] != candidate:
        raise ValueError('Finish the pending mirror publication before staging another snapshot')
    if not state['successful'] and active:
        # Bootstrap by mirroring the currently accepted primary database too.
        state['successful'] = [active]
    if active and active not in [*state['successful'], state['pending']]:
        raise ValueError('Live snapshot is missing from protected mirror state')
    state['pending'] = candidate
    retained = list(dict.fromkeys([*state['successful'], candidate]))
    if len(state['successful']) > 2 or len(retained) > 3:
        raise ValueError('Mirror snapshot retention exceeded')
    state['snapshots'] = {s: {'verified': False, 'routes': snapshot_plan(site, settings, s)} for s in retained}
    state['keys'] = key_plan(site)
    write_json(Path(site)/STATE, state)
    return state


def references(state):
    result = {}
    for routes in [state['keys'], *(s['routes'] for s in state['snapshots'].values())]:
        for item in routes.values():
            url = location(state['repository'], item['tag'], item['filename'])
            if url in result and result[url]['sha256'] != item['sha256']:
                raise ValueError('Conflicting immutable mirror reference')
            result[url] = item
    return result


def verify_remote(url, expected):
    request = urllib.request.Request(url, headers={'User-Agent': 'fansionia-pacman-mirror'})
    # Deliberately anonymous and uncached. Check all bytes, including on retries.
    for attempt in range(4):
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(request, timeout=90) as response:
                while block := response.read(1024*1024):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError('CNB anonymous download SHA-256 mismatch')
            return
        except OSError:
            if attempt == 3:
                raise RuntimeError('CNB anonymous download failed') from None
            time.sleep(2**attempt)


def sync(site, settings, client=None):
    site = Path(site)
    state = read_state(site, settings)
    if not state['pending']:
        raise ValueError('Stage a mirror candidate before syncing')
    client = client or Client(state['repository'])
    uploaded = reused = 0
    for url, item in references(state).items():
        if 'source' in item:
            source = download(item['source'], ROOT.parent/'.cache/pacman-downloads'/item['sha256'], item['sha256'])
        else:
            source = Path(item['local'])
        if checksum(source) != item['sha256']:
            raise ValueError('Mirror source checksum mismatch')
        record = {k: item[k] for k in ['tag', 'filename', 'sha256']}
        record['size'] = source.stat().st_size
        before = state['objects'].get(url)
        if before is not None and before != record:
            raise ValueError('Refusing to replace an immutable mirrored object')
        # A conservative repository budget leaves room for other shared
        # organization objects. The platform's free quota remains the hard
        # limit; this workflow never enables billing or changes its budget.
        projected = sum(o['size'] for o in state['objects'].values())+(0 if before else record['size'])
        if projected > settings['mirror']['max_bytes']:
            raise ValueError('Mirror storage budget exceeded; protected files will not be deleted')
        state['objects'][url] = record
        write_json(site/STATE, state)  # journal before any external write
        if client.upload(record, source):
            uploaded += 1
        else:
            reused += 1
        verify_remote(url, item['sha256'])
        print('Verified CNB attachment:', item['filename'])
    for snapshot in state['snapshots'].values():
        snapshot['verified'] = True
    # Local paths belong to the snapshot job, not to later artifact consumers.
    for mapping in [state['keys'], *(s['routes'] for s in state['snapshots'].values())]:
        for item in mapping.values():
            item.pop('local', None)
    write_json(site/STATE, state)
    print(f'CNB sync complete: uploaded {uploaded} new attachments; reused {reused} existing attachments')


def routes(site, settings, selected):
    state = read_state(site, settings)
    if selected not in state['snapshots'] or any(not s['verified'] for s in state['snapshots'].values()):
        raise ValueError('Mirror is not fully verified for the selected snapshot')
    assets = {}
    retained = list(dict.fromkeys([*state['successful'], *([state['pending']] if state['pending'] else [])]))
    if set(retained) != set(state['snapshots']):
        raise ValueError('Mirror retained snapshot references changed')
    for snapshot in retained:
        record = state['snapshots'][snapshot]
        manifest = json.loads((Path(site)/'snapshots'/snapshot/'manifest.json').read_text())
        expected = {}
        for package in manifest['packages']:
            for suffix, prefix in [('', ''), ('.sig', 'signature_')]:
                expected['/'+settings['architecture']+'/'+package['filename']+suffix] = package[prefix+'sha256']
        if snapshot == selected:
            expected.update({'/'+p: digest for p, digest in manifest['files'].items()})
        for path, digest in expected.items():
            item = record['routes'][path]
            if item['sha256'] != digest:
                raise ValueError('Mirror verification receipt does not match snapshot')
            url = location(state['repository'], item['tag'], item['filename'])
            if state['objects'][url]['sha256'] != digest:
                raise ValueError('Mirror object ledger does not match snapshot')
            path = '/mirror'+path
            if path in assets and assets[path] != url:
                raise ValueError('Conflicting immutable mirror mapping')
            assets[path] = url
    for path, item in state['keys'].items():
        if item['sha256'] != checksum(Path(site)/path.lstrip('/')):
            raise ValueError('Mirror public key verification receipt changed')
        assets['/mirror'+path] = location(state['repository'], item['tag'], item['filename'])
    return assets, retained


def finish(site, settings, candidate, public=None):
    from state import public_status
    public = public if public is not None else public_status()
    state = read_state(site, settings)
    if state['pending'] != candidate or public.get('active') != candidate or public.get('phase') != 'active' or \
            public.get('mirror', {}).get('active') != candidate:
        raise ValueError('Both public origins must serve the accepted candidate before retention changes')
    if not state['snapshots'][candidate]['verified']:
        raise ValueError('Unverified mirror candidate')
    successful = [s for s in state['successful'] if s != candidate]+[candidate]
    state['successful'] = successful[-2:]
    state['pending'] = ''
    state['cleanup_pending'] = True
    state['snapshots'] = {s: state['snapshots'][s] for s in state['successful']}
    write_json(Path(site)/STATE, state)


def prune(site, settings, client=None, public=None):
    from state import public_status
    state = read_state(site, settings)
    public = public if public is not None else public_status()
    if state['pending'] or not state['successful'] or public.get('phase') != 'active' or \
            public.get('active') != state['successful'][-1] or \
            public.get('mirror', {}).get('active') != state['successful'][-1] or \
            public.get('mirror', {}).get('snapshots') != state['successful']:
        raise ValueError('Refusing cleanup before the retained public mirror mappings are deployed')
    client = client or Client(state['repository'])
    protected = references(state)
    for url, item in list(state['objects'].items()):
        if url in protected:
            continue
        client.delete(item)
        del state['objects'][url]
        write_json(Path(site)/STATE, state)
        print('Removed unreferenced CNB attachment:', item['filename'])
    state['cleanup_pending'] = False
    write_json(Path(site)/STATE, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['stage', 'sync', 'finish', 'prune'])
    parser.add_argument('--site', default='.work/pacman-site')
    parser.add_argument('--active', default='')
    parser.add_argument('--candidate', default='')
    args = parser.parse_args()
    settings = json.loads((ROOT/'sources.json').read_text())
    if args.command == 'stage':
        stage(args.site, settings, args.active, args.candidate)
    elif args.command == 'sync':
        sync(args.site, settings)
    elif args.command == 'finish':
        finish(args.site, settings, args.candidate)
    else:
        prune(args.site, settings)
