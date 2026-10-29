"""Mirror publication, recovery and reference-based collection boundaries."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mirror
import repository


class FakeClient:
    def __init__(self):
        self.uploaded = {}
        self.deleted = []

    def upload(self, item, source):
        self.uploaded[(item['tag'], item['filename'])] = item.copy()

    def delete(self, item):
        self.deleted.append(item.copy())
        self.uploaded.pop((item['tag'], item['filename']), None)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.site = Path(self.temporary.name)
        self.settings = {'architecture': 'x86_64', 'repository': 'fansionia',
                         'pages_url': 'https://pages.example', 'public_url': 'https://packages.example',
                         'mirror': {'repository': 'test/mirror', 'max_bytes': 1024*1024}}
        (self.site/'keys').mkdir()
        (self.site/'keys/fansionia.asc').write_text('public key')
        self.client = FakeClient()
        self.sources = {}

    def snapshot(self, snapshot, version, shared=False):
        base = self.site/'snapshots'/snapshot
        (base/'x86_64').mkdir(parents=True)
        packages = []
        for name, value in [('foo', version), *([('shared', '1')] if shared else [])]:
            filename = f'{name}-{value}-1-any.pkg.tar.zst'
            source = self.site/filename
            source.write_text(name+value)
            signature = Path(str(source)+'.sig')
            signature.write_text('signature '+name+value)
            url = f'https://github.com/test/{name}/releases/download/v{value}/{filename}'
            self.sources[url] = source
            self.sources[url+'.sig'] = signature
            packages.append({'repository': 'test/'+name, 'tag': 'v'+value, 'filename': filename,
                'name': name, 'version': value+'-1', 'architecture': 'any',
                'url': url, 'signature_url': url+'.sig', 'sha256': mirror.checksum(source),
                'signature_sha256': mirror.checksum(signature)})
        database = base/'x86_64/fansionia.db'
        database.write_text('database '+snapshot)
        repository.write_json(base/'manifest.json', {'packages': packages,
            'files': {'x86_64/fansionia.db': mirror.checksum(database)}})
        return packages

    def sync(self):
        def download(url, destination, digest):
            self.assertEqual(mirror.checksum(self.sources[url]), digest)
            return self.sources[url]
        with patch.object(mirror, 'download', side_effect=download), \
                patch.object(mirror, 'verify_remote') as verify:
            mirror.sync(self.site, self.settings, self.client)
        self.assertTrue(verify.call_count)

    def public(self, candidate, snapshots):
        return {'active': candidate, 'phase': 'active',
                'mirror': {'active': candidate, 'snapshots': snapshots}}

    def accept(self, candidate):
        state = mirror.read_state(self.site, self.settings)
        mirror.finish(self.site, self.settings, candidate,
                      self.public(candidate, list(state['snapshots'])))
        state = mirror.read_state(self.site, self.settings)
        mirror.prune(self.site, self.settings, self.client,
                     self.public(candidate, state['successful']))

    def test_two_successful_plus_candidate_and_shared_package_collection(self):
        a, b, c = 'f'*32, '1'*32, 'a'*32
        for snapshot, version in [(a, '1'), (b, '2'), (c, '3')]:
            self.snapshot(snapshot, version, shared=True)
        mirror.stage(self.site, self.settings, a, b)
        self.sync()
        self.accept(b)
        first = mirror.read_state(self.site, self.settings)
        self.assertEqual(first['successful'], [a, b])
        mirror.stage(self.site, self.settings, b, c)
        self.sync()
        state = mirror.read_state(self.site, self.settings)
        self.assertEqual(set(state['snapshots']), {a, b, c})
        self.assertFalse(self.client.deleted)
        assets, snapshots = mirror.routes(self.site, self.settings, b)
        self.assertEqual(snapshots, [a, b, c])
        self.assertIn('/mirror/x86_64/foo-3-1-any.pkg.tar.zst', assets)
        self.assertIn('/mirror/keys/fansionia.asc', assets)
        self.assertIn('pacman-snapshot-'+b, assets['/mirror/x86_64/fansionia.db'])
        mirror.finish(self.site, self.settings, c, self.public(c, [a, b, c]))
        with self.assertRaisesRegex(ValueError, 'retained public'):
            mirror.prune(self.site, self.settings, self.client, self.public(c, [a, b, c]))
        mirror.prune(self.site, self.settings, self.client, self.public(c, [b, c]))
        state = mirror.read_state(self.site, self.settings)
        self.assertEqual(state['successful'], [b, c])
        self.assertFalse(state['cleanup_pending'])
        removed = [p['filename'] for p in self.client.deleted]
        self.assertIn('foo-1-1-any.pkg.tar.zst', removed)
        self.assertNotIn('shared-1-1-any.pkg.tar.zst', removed)
        self.assertNotIn('foo-2-1-any.pkg.tar.zst', removed)
        assets, _ = mirror.routes(self.site, self.settings, c)
        self.assertNotIn('/mirror/x86_64/foo-1-1-any.pkg.tar.zst', assets)

    def test_corrupt_mirror_blocks_activation_and_keeps_protected_snapshots(self):
        a, b = 'a'*32, 'b'*32
        self.snapshot(a, '1')
        self.snapshot(b, '2')
        mirror.stage(self.site, self.settings, a, b)
        with patch.object(mirror, 'download', side_effect=lambda url, *_: self.sources[url]), \
                patch.object(mirror, 'verify_remote', side_effect=ValueError('bad bytes')):
            with self.assertRaises(ValueError):
                mirror.sync(self.site, self.settings, self.client)
        state = mirror.read_state(self.site, self.settings)
        self.assertEqual(state['successful'], [a])
        self.assertEqual(state['pending'], b)
        self.assertFalse(self.client.deleted)
        with self.assertRaisesRegex(ValueError, 'fully verified'):
            mirror.routes(self.site, self.settings, b)
        with self.assertRaises(ValueError):
            mirror.finish(self.site, self.settings, b, self.public(a, [a, b]))
        # A retry reuses the same candidate and exact bytes.
        mirror.stage(self.site, self.settings, a, b)
        self.sync()
        self.accept(b)

    def test_capacity_failure_does_not_delete_protected_files(self):
        a = 'a'*32
        self.snapshot(a, '1')
        mirror.stage(self.site, self.settings, '', a)
        self.settings['mirror']['max_bytes'] = 0
        with patch.object(mirror, 'download', side_effect=lambda url, *_: self.sources[url]):
            with self.assertRaisesRegex(ValueError, 'budget exceeded'):
                mirror.sync(self.site, self.settings, self.client)
        self.assertFalse(self.client.uploaded)
        self.assertFalse(self.client.deleted)

    def test_unfinished_candidate_cannot_be_replaced(self):
        a, b = 'a'*32, 'b'*32
        self.snapshot(a, '1')
        self.snapshot(b, '2')
        mirror.stage(self.site, self.settings, '', a)
        with self.assertRaisesRegex(ValueError, 'pending'):
            mirror.stage(self.site, self.settings, '', b)

    def test_receipts_cannot_change_package_hashes(self):
        a = 'a'*32
        self.snapshot(a, '1')
        mirror.stage(self.site, self.settings, '', a)
        self.sync()
        state = mirror.read_state(self.site, self.settings)
        state['snapshots'][a]['routes']['/x86_64/foo-1-1-any.pkg.tar.zst']['sha256'] = '0'*64
        repository.write_json(self.site/mirror.STATE, state)
        with self.assertRaisesRegex(ValueError, 'receipt'):
            mirror.routes(self.site, self.settings, a)

    def test_api_never_overwrites_different_assets_or_adopts_user_releases(self):
        client = mirror.Client('test/mirror', 'not-a-real-token')
        item = {'tag': 'pacman-package-abc', 'filename': 'foo', 'size': 1, 'sha256': 'a'*64}
        with patch.object(client, 'request', return_value={'body': 'user content'}):
            with self.assertRaisesRegex(ValueError, 'not owned'):
                client.release(item['tag'])
        with patch.object(client, 'release', return_value={'assets': [{'name': 'foo', 'size': 2}]}):
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                client.upload(item, '/nonexistent')
        for path in ['https://evil.example/releases', '/test/mirror/-/issues']:
            with self.assertRaisesRegex(ValueError, 'scope'):
                client.request('GET', path)

    def test_existing_identical_attachment_never_requests_an_upload_url_or_put(self):
        client = mirror.Client('test/mirror', 'not-a-real-token')
        item = {'tag': 'pacman-package-abc', 'filename': 'foo', 'size': 42, 'sha256': 'a'*64}
        release = {'assets': [{'name': 'foo', 'size': 42, 'hash_algo': 'sha256', 'hash_value': 'a'*64}]}
        with patch.object(client, 'release', return_value=release), \
                patch.object(client, 'request') as api, patch.object(client.opener, 'open') as put:
            client.upload(item, '/nonexistent-source-is-not-opened')
        api.assert_not_called()
        put.assert_not_called()


if __name__ == '__main__':
    unittest.main()
