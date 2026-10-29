#!/usr/bin/env python3
"""Read signed pacman upstreams using reviewed, repository-local public keys."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import string
import tarfile
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
USER_AGENT = 'pacman/7.1.0 (Linux x86_64) fansionia-sync'


def fetch(url, limit=16 * 1024 * 1024):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Upstream metadata exceeds size limit')
    return data


def sources(settings):
    result = settings.get('upstreams', [])
    seen = set()
    for source in result:
        name = source['id']
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', name) or name in seen:
            raise ValueError('Invalid or duplicate upstream ID')
        seen.add(name)
        if not re.fullmatch(r'[A-F0-9]{40}', source['fingerprint']):
            raise ValueError('Upstream requires a full primary-key fingerprint')
        if source.get('key') != 'upstream-keys/'+name+'.asc':
            raise ValueError('Upstream key must be a reviewed local file')
        server(source, settings['architecture'])
    return result


def server(source, architecture):
    url = source['server'].replace('$repo', source['id']).replace('$arch', architecture).rstrip('/')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or \
            parsed.query or parsed.fragment or '$' in url:
        raise ValueError('Upstream server must be an HTTPS repository directory')
    return url


def keyring(source, home):
    """Import in an isolated home; never use a user's keyring or a keyserver."""
    path = ROOT/source['key']
    command = ['gpg', '--homedir', str(home), '--batch', '--no-tty']
    listing = subprocess.check_output([*command, '--with-colons', '--show-keys', str(path)],
                                      stderr=subprocess.PIPE, text=True)
    primaries = []
    primary = False
    for line in listing.splitlines():
        if line.startswith(('pub:', 'sub:')):
            primary = line.startswith('pub:')
        elif line.startswith('fpr:') and primary:
            primaries.append(line.split(':')[9])
            primary = False
    if primaries != [source['fingerprint']]:
        raise ValueError('Upstream public key fingerprint mismatch: '+source['id'])
    subprocess.run([*command, '--import', str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    exported = subprocess.check_output([*command, '--export-options', 'export-minimal',
                                        '--export', source['fingerprint']], stderr=subprocess.PIPE)
    destination = Path(home)/'verification.gpg'
    destination.write_bytes(exported)
    return destination


def verify(source, path, signature=None):
    with tempfile.TemporaryDirectory(prefix='fansionia-upstream-gpg-') as temporary:
        public = keyring(source, temporary)
        status = subprocess.check_output(['gpgv', '--homedir', temporary, '--status-fd', '1',
            '--keyring', str(public), str(signature or str(path)+'.sig'), str(path)], text=True)
        valid = [line.split() for line in status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
        # VALIDSIG's last field identifies the primary key, including subkey signatures.
        if not any(parts[2] == source['fingerprint'] or parts[-1] == source['fingerprint'] for parts in valid):
            raise ValueError('Unexpected upstream signing key')


def fields(data):
    result = {}
    for block in data.decode('utf-8').strip().split('\n\n'):
        lines = block.splitlines()
        if not lines or not re.fullmatch(r'%[A-Z0-9_]+%', lines[0]):
            raise ValueError('Malformed upstream database field')
        name = lines[0].strip('%')
        if name in result:
            raise ValueError('Duplicate upstream database field')
        result[name] = lines[1:]
    return result


def parse_database(data, source, architecture):
    packages = []
    names = set()
    expanded = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        for member in archive:
            expanded += member.size
            if expanded > 64 * 1024 * 1024 or len(packages) > 10000:
                raise ValueError('Upstream database exceeds expansion limit')
            if not member.name.endswith('/desc'):
                continue
            if not member.isfile() or member.size > 1024 * 1024:
                raise ValueError('Invalid upstream desc entry')
            record = fields(archive.extractfile(member).read())
            def one(key):
                values = record.get(key, [])
                if len(values) != 1 or not values[0]:
                    raise ValueError('Missing or ambiguous upstream field: '+key)
                return values[0]
            name, filename, version = one('NAME'), one('FILENAME'), one('VERSION')
            if not re.fullmatch(r'[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\-]*', name) or name in names:
                raise ValueError('Invalid or duplicate upstream package name')
            names.add(name)
            allowed = string.ascii_letters + string.digits + "@_+:.~-"
            if not filename[0].isalnum() or any(c not in allowed for c in filename) or not \
                    re.search(r"\.pkg\.tar\.(zst|xz|gz)$", filename):
                raise ValueError('Invalid upstream package filename')
            if not re.fullmatch(r'[A-Za-z0-9_.+:~\-]+', version):
                raise ValueError('Invalid upstream version')
            arch = one('ARCH')
            if arch not in (architecture, 'any'):
                raise ValueError('Unexpected upstream package architecture')
            digest = one('SHA256SUM')
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('Missing upstream SHA-256')
            url = server(source, architecture)+'/'+urllib.parse.quote(filename, safe='')
            packages.append({'upstream': source['id'], 'project': source['id'],
                'repository': 'upstream/'+source['id'], 'tag': 'upstream-'+source['id']+'-'+hashlib.sha256(
                    (name+'\n'+version+'\n'+digest).encode()).hexdigest()[:32],
                'name': name, 'filename': filename, 'version': version, 'architecture': arch,
                'url': url, 'sha256': digest, 'signature_url': url+'.sig',
                **({'embedded_signature': one('PGPSIG')} if 'PGPSIG' in record else {})})
    if not packages:
        raise ValueError('Upstream database is empty')
    return packages


def discover(settings, occupied):
    packages = []
    names = set(occupied)
    for source in sources(settings):
        url = server(source, settings['architecture'])+'/'+source['id']+'.db'
        data, signature = fetch(url), fetch(url+'.sig', 1024 * 1024)
        with tempfile.TemporaryDirectory(prefix='fansionia-upstream-db-') as temporary:
            path = Path(temporary)/'upstream.db'
            path.write_bytes(data)
            Path(str(path)+'.sig').write_bytes(signature)
            verify(source, path)
        for package in parse_database(data, source, settings['architecture']):
            if package['name'] in names:
                print('Skipping colliding upstream package:', source['id'], package['name'])
                continue
            signature = fetch(package['signature_url'], 1024 * 1024)
            embedded = package.pop('embedded_signature', None)
            if embedded is not None and base64.b64decode(embedded, validate=True) != signature:
                raise ValueError('Detached signature differs from signed upstream database')
            package['signature_sha256'] = hashlib.sha256(signature).hexdigest()
            packages.append(package)
            names.add(package['name'])
    return packages


def export_keyring(settings, destination, check=False):
    public = b''
    trusted = ''
    for source in sources(settings):
        with tempfile.TemporaryDirectory(prefix='fansionia-keyring-') as temporary:
            public += keyring(source, temporary).read_bytes()
        trusted += source['fingerprint']+':4:\n'
    destination = Path(destination)
    for filename, content in [('fansionia-upstream.gpg', public),
                              ('fansionia-upstream-trusted', trusted.encode()),
                              ('fansionia-upstream-revoked', b'')]:
        path = destination/filename
        if check:
            if path.read_bytes() != content:
                raise ValueError('Regenerate upstream keyring: '+filename)
        else:
            path.write_bytes(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['keyring', 'probe'])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    settings = json.loads((ROOT/'sources.json').read_text())
    if args.command == 'keyring':
        export_keyring(settings, ROOT/'support/fansionia-keyring', args.check)
    else:
        print(json.dumps(discover(settings, []), indent=2))
