"""Real repo-add/GnuPG integration, only on disposable native Arch CI."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARCH))
spec = importlib.util.spec_from_file_location('native_repository', ARCH/'repository.py')
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)
import upstream


@unittest.skipUnless(os.environ.get('CI_ARCH_REPOSITORY') == '1' and shutil.which('repo-add'),
                     'requires disposable native Arch CI with repo-add')
class NativeRepositoryTests(unittest.TestCase):
    def test_signed_snapshot_roundtrip_and_idempotent_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root/'gpg'
            home.mkdir(mode=0o700)
            environment = dict(os.environ, GNUPGHOME=str(home))
            def gpg(*args, **kwargs):
                return subprocess.check_output(['gpg', '--batch', '--pinentry-mode', 'loopback',
                                                '--passphrase', '', *args], env=environment, **kwargs)
            try:
                gpg('--quick-generate-key', 'Ephemeral repository integration test', 'ed25519', 'cert', '5y')
                def fingerprints():
                    return [line.split(':')[9] for line in gpg('--with-colons', '--list-secret-keys').decode().splitlines()
                            if line.startswith('fpr:')]
                primary = fingerprints()[0]
                gpg('--quick-add-key', primary, 'ed25519', 'sign', '2y')
                signer = fingerprints()[-1]
                arch = root/'arch'
                keys = arch/'keys'
                keys.mkdir(parents=True)
                (keys/'fansionia.gpg').write_bytes(gpg('--export', primary))
                (keys/'fansionia.asc').write_bytes(gpg('--armor', '--export', primary))
                (keys/'fingerprint.txt').write_text(primary+'\n')
                repository.write_json(keys/'signers.json', {'test/fixture': signer})
                shutil.copy2(ARCH/'worker.mjs', arch/'worker.mjs')
                payload = root/'payload'
                payload.mkdir()
                (payload/'.PKGINFO').write_text('pkgname = fixture\npkgbase = fixture\npkgver = 1.0.0-1\n'
                    'pkgdesc = integration fixture\narch = any\nsize = 1\nbuilddate = 1700000000\nlicense = MIT\n')
                (payload/'fixture.txt').write_text('payload\n')
                archive = root/'fixture-1.0.0-1-any.pkg.tar.zst'
                subprocess.run(['bsdtar', '--zstd', '-cf', str(archive), '.PKGINFO', 'fixture.txt'], cwd=payload, check=True)
                gpg('--local-user', signer+'!', '--detach-sign', str(archive))
                package = {'name':'fixture', 'project':'fixture', 'repository':'test/fixture', 'tag':'v1.0.0',
                           'version':'1.0.0-1', 'architecture':'any', 'filename':archive.name,
                           'url':'https://github.com/test/fixture/releases/download/v1.0.0/'+archive.name,
                           'signature_url':'https://github.com/test/fixture/releases/download/v1.0.0/'+archive.name+'.sig',
                           'sha256':repository.checksum(archive), 'signature_sha256':repository.checksum(str(archive)+'.sig')}
                def download(url, destination, expected):
                    source = Path(str(archive)+'.sig') if url.endswith('.sig') else archive
                    self.assertEqual(repository.checksum(source), expected)
                    Path(destination).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                settings = {'architecture':'x86_64', 'repository':'fansionia', 'keep_snapshots':32,
                            'pages_url':'https://pages.example', 'public_url':'https://packages.example'}
                upstream_keys = arch/'upstream-keys'
                upstream_keys.mkdir()
                (upstream_keys/'fixture.asc').write_bytes(gpg('--armor', '--export', primary))
                source = {'id': 'fixture', 'server': 'https://upstream.example/$arch',
                          'key': 'upstream-keys/fixture.asc', 'fingerprint': primary}
                settings['upstreams'] = [source]
                # A real upstream archive with an epoch and its original signature.
                external = root/'external-1:2.0-1-any.pkg.tar.zst'
                metadata = (payload/'.PKGINFO').read_text()
                (payload/'.PKGINFO').write_text(metadata.replace('fixture', 'external').replace('1.0.0-1', '1:2.0-1'))
                subprocess.run(['bsdtar', '--zstd', '-cf', str(external), '.PKGINFO', 'fixture.txt'], cwd=payload, check=True)
                gpg('--local-user', signer+'!', '--detach-sign', str(external))
                external_record = dict(package, name='external', upstream='fixture', project='fixture',
                    repository='upstream/fixture', tag='upstream-fixture-test', version='1:2.0-1',
                    filename=external.name, url='https://upstream.example/'+external.name,
                    signature_url='https://upstream.example/'+external.name+'.sig',
                    sha256=repository.checksum(external), signature_sha256=repository.checksum(str(external)+'.sig'))
                original_download = download
                def download(url, destination, expected):
                    if url.startswith('https://upstream.example/'):
                        source_path = Path(str(external)+('.sig' if url.endswith('.sig') else ''))
                        self.assertEqual(repository.checksum(source_path), expected)
                        Path(destination).parent.mkdir(parents=True, exist_ok=True)
                        return shutil.copy2(source_path, destination)
                    return original_download(url, destination, expected)
                variables = {'ARCH_SIGNING_PRIVATE_KEY':gpg('--armor', '--export-secret-subkeys', signer+'!').decode(),
                             'ARCH_SIGNING_KEY_ID':signer, 'ARCH_SIGNING_PASSPHRASE':''}
                site = root/'site'
                with patch.object(repository, 'ROOT', arch), patch.object(upstream, 'ROOT', arch), \
                     patch.object(repository, 'discover', return_value=[package, external_record]), \
                     patch.object(repository, 'download', side_effect=download), patch.dict(os.environ, variables), \
                     contextlib.redirect_stdout(io.StringIO()):
                    repository.build(site, settings, '')
                    snapshot = json.loads((site/'snapshots.json').read_text())[0]
                    files = site/'snapshots'/snapshot/'x86_64'
                    signature = (files/'fansionia.db.sig').read_bytes()
                    self.assertFalse(any(path.is_symlink() for path in files.iterdir()))
                    subprocess.run(['gpgv', '--keyring', str(keys/'fansionia.gpg'),
                                    str(files/'fansionia.db.sig'), str(files/'fansionia.db')], check=True)
                    listing = subprocess.check_output(['bsdtar', '-tf', str(files/'fansionia.db')], text=True)
                    self.assertIn('fixture-1.0.0-1/desc', listing)
                    desc = subprocess.check_output(['bsdtar', '-xOf', str(files/'fansionia.db'), 'fixture-1.0.0-1/desc'], text=True)
                    self.assertIn('%PGPSIG%', desc)
                    self.assertIn(archive.name, desc)
                    external_desc = subprocess.check_output(['bsdtar', '-xOf', str(files/'fansionia.db'),
                                                             'external-1:2.0-1/desc'], text=True)
                    self.assertIn('%PGPSIG%', external_desc)
                    self.assertIn(external.name, external_desc)
                    upstream.verify(source, files/'fansionia.db', files/'fansionia.db.sig')
                    parsed = upstream.parse_database((files/'fansionia.db').read_bytes(), source, 'x86_64')
                    self.assertEqual({p['name'] for p in parsed}, {'fixture', 'external'})
                    # Tampered bytes and unreviewed keys must fail even when a
                    # detached signature is present and correctly formatted.
                    external.write_bytes(external.read_bytes()+b'tampered')
                    with self.assertRaises(subprocess.CalledProcessError):
                        upstream.verify(source, external)
                    with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
                        upstream.verify(dict(source, fingerprint='F'*40), files/'fansionia.db')
                    repository.build(site, settings, snapshot)
                    self.assertEqual(signature, (files/'fansionia.db.sig').read_bytes())
                    self.assertEqual(json.loads((site/'snapshots.json').read_text()), [snapshot])
            finally:
                subprocess.run(['gpgconf', '--homedir', str(home), '--kill', 'gpg-agent'], check=False)


if __name__ == '__main__':
    unittest.main()
