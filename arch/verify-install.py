#!/usr/bin/env python3
"""Select and verify the packages covered by pacman publication acceptance."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from repository import ROOT, canonical, previous_manifest, trust_policy, worker, write_json

DROIDLOOM = {'droidloom-base', 'droidloom-image', 'droidloom-runtime'}
KEYRING = 'fansionia-keyring'


def selected_packages(current, previous, full=False):
    packages = current['packages']
    if (full or not previous or current['policy'] != previous['policy'] or
            previous['packages'].get(KEYRING) != packages.get(KEYRING)):
        return sorted(packages)
    selected = {name for name, record in packages.items() if previous['packages'].get(name) != record}
    if selected & DROIDLOOM:
        selected.update(packages.keys() & DROIDLOOM)
    return sorted(selected | {KEYRING})


def prepare(site, settings, snapshot, full):
    manifest = previous_manifest(site, snapshot)
    destination = site/'verification/worker.mjs'
    worker(site, settings, '', snapshot, 'active', destination)
    config = json.loads(destination.with_suffix('.json').read_text())
    state = json.loads((site/'mirror-state.json').read_text())
    assets = config['assets']
    packages = {}
    for record in manifest['packages']:
        path = '/'+settings['architecture']+'/'+record['filename']
        packages[record['name']] = [
            record, assets[path], assets[path+'.sig'], assets['/mirror'+path], assets['/mirror'+path+'.sig']]
    policy = hashlib.sha256(canonical([
        trust_policy(), (ROOT/'test-install.sh').read_text(), Path(__file__).read_text(),
    ])).hexdigest()
    acceptance = {'snapshot': snapshot, 'policy': policy, 'packages': packages}
    previous = state.get('accepted_install')
    if previous and (not state['successful'] or previous['snapshot'] != state['successful'][-1]):
        previous = None
    selected = selected_packages(acceptance, previous, full)
    write_json(site/'acceptance.json', acceptance)
    (site/'install-targets.txt').write_text(''.join(name+'\n' for name in selected))
    print(f'Install acceptance for {snapshot}: {", ".join(selected)}')
    return config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_routes(site, settings, server, origin):
    config = json.loads((site/'verification/worker.json').read_text())
    manifest = previous_manifest(site, config['active'])
    prefix = '/mirror' if origin == 'mirror' else ''
    base = '/'+settings['architecture']+'/'
    expected = [prefix+'/'+name for name in manifest['files']]
    for record in manifest['packages']:
        path = prefix+base+record['filename']
        expected.extend([path, path+'.sig'])
    expected.append(prefix+'/keys/fansionia.asc')
    request = urllib.request.Request(server+prefix+'/status.json', headers={'Cache-Control': 'no-cache'})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = json.load(response)
            if all(status.get(key) == config.get(key) for key in ('active', 'phase', 'mirror')):
                break
        except OSError:
            if attempt == 4:
                raise
        time.sleep(2)
    else:
        raise ValueError('Install endpoint is not serving the requested active snapshot')

    def check(path):
        target = config['assets'][path]
        request = urllib.request.Request(server+urllib.parse.quote(path, safe='/'), method='HEAD',
                                         headers={'Cache-Control': 'no-cache'})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=15):
                pass
        except urllib.error.HTTPError as error:
            with error:
                if error.code == 302 and error.headers.get('Location') == target:
                    return
        raise ValueError('Unexpected install redirect for '+path)

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(check, expected))
    print(f'Verified {len(expected)} {origin} redirects in {time.monotonic()-started:.1f}s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'routes'])
    parser.add_argument('--site', type=Path, default=Path('.work/pacman-site'))
    parser.add_argument('--snapshot')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--server')
    parser.add_argument('--origin', choices=['primary', 'mirror'])
    args = parser.parse_args()
    settings = json.loads((ROOT/'sources.json').read_text())
    if args.command == 'prepare':
        prepare(args.site, settings, args.snapshot, args.full)
    else:
        verify_routes(args.site, settings, args.server, args.origin)


if __name__ == '__main__':
    main()
