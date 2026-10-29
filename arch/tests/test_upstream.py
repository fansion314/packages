"""Signed upstream discovery, collision policy, and untrusted archive boundaries."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import upstream
import repository


class UpstreamTests(unittest.TestCase):
    source = {'id': 'fixture', 'server': 'https://upstream.example/$repo/$arch',
              'key': 'upstream-keys/fixture.asc', 'fingerprint': 'A'*40}
    settings = {'architecture': 'x86_64', 'upstreams': [source]}

    def database(self, name='foo', filename='foo-1:2.0-1-x86_64.pkg.tar.zst', **updates):
        fields = {'NAME': name, 'VERSION': '1:2.0-1', 'FILENAME': filename,
                  'ARCH': 'x86_64', 'SHA256SUM': 'a'*64,
                  'PGPSIG': base64.b64encode(b'signature').decode()}
        fields.update(updates)
        desc = ''.join('%'+k+'%\n'+v+'\n\n' for k, v in fields.items() if v is not None).encode()
        result = io.BytesIO()
        with tarfile.open(fileobj=result, mode='w:gz') as archive:
            member = tarfile.TarInfo(name+'/desc')
            member.size = len(desc)
            archive.addfile(member, io.BytesIO(desc))
        return result.getvalue()

    def fetch(self, database):
        return lambda url, *args: b'signature' if url.endswith('.sig') else database

    def test_epoch_and_any_archives_preserve_exact_upstream_filename(self):
        data = self.database(ARCH='any')
        with patch.object(upstream, 'fetch', side_effect=self.fetch(data)), \
                patch.object(upstream, 'verify') as verify:
            packages = upstream.discover(self.settings, [])
        verify.assert_called_once()
        package = packages[0]
        self.assertEqual(package['version'], '1:2.0-1')
        self.assertEqual(package['architecture'], 'any')
        self.assertIn('foo-1%3A2.0-1', package['url'])
        self.assertEqual(package['signature_sha256'], hashlib.sha256(b'signature').hexdigest())
        self.assertNotIn('embedded_signature', package)

    def test_native_names_win_and_first_upstream_wins_other_collisions(self):
        data = self.database()
        other = dict(self.source, id='other', key='upstream-keys/other.asc')
        with patch.object(upstream, 'fetch', side_effect=self.fetch(data)) as fetch, \
                patch.object(upstream, 'verify'):
            self.assertEqual(upstream.discover(self.settings, ['foo']), [])
            self.assertEqual(fetch.call_count, 2)  # DB verified, colliding archive ignored.
            merged = upstream.discover(dict(self.settings, upstreams=[self.source, other]), [])
        self.assertEqual([p['upstream'] for p in merged], ['fixture'])

    def test_invalid_database_signature_stops_before_metadata_or_package_fetch(self):
        with patch.object(upstream, 'fetch', side_effect=self.fetch(self.database())) as fetch, \
                patch.object(upstream, 'verify', side_effect=ValueError('bad signature')):
            with self.assertRaisesRegex(ValueError, 'bad signature'):
                upstream.discover(self.settings, [])
            self.assertEqual(fetch.call_count, 2)

    def test_missing_embedded_signature_uses_detached_and_mismatch_is_rejected(self):
        data = self.database(PGPSIG=None)
        with patch.object(upstream, 'fetch', side_effect=self.fetch(data)), \
                patch.object(upstream, 'verify'):
            package = upstream.discover(self.settings, [])[0]
            self.assertTrue(package['signature_url'].endswith('.sig'))
        with patch.object(upstream, 'fetch', side_effect=self.fetch(self.database(PGPSIG='eA=='))), \
                patch.object(upstream, 'verify'):
            with self.assertRaisesRegex(ValueError, 'differs'):
                upstream.discover(self.settings, [])

    def test_path_traversal_foreign_arch_and_missing_digest_fail_closed(self):
        for changes in [{'filename': '../evil.pkg.tar.zst'}, {'filename': 'bad%2Fname.pkg.tar.zst'},
                        {'ARCH': 'aarch64'}, {'SHA256SUM': ''}, {'SHA256SUM': 'x'*64}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                upstream.parse_database(self.database(**changes), self.source, 'x86_64')

    def test_symlink_desc_and_duplicate_records_are_rejected(self):
        result = io.BytesIO()
        with tarfile.open(fileobj=result, mode='w:gz') as archive:
            member = tarfile.TarInfo('foo/desc')
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
            archive.addfile(member)
        with self.assertRaisesRegex(ValueError, 'desc'):
            upstream.parse_database(result.getvalue(), self.source, 'x86_64')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            upstream.fields(b'%NAME%\nfoo\n\n%NAME%\nbar\n')

    def test_unreviewed_key_paths_and_non_https_servers_are_rejected(self):
        for changes in [{'server': 'http://example/$arch'}, {'key': '../../other.asc'},
                        {'fingerprint': 'ABCD'}, {'server': 'https://example/$unknown'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                upstream.sources(dict(self.settings, upstreams=[dict(self.source, **changes)]))

    def test_upstream_worker_and_mirror_routes_preserve_origin(self):
        import mirror
        package = upstream.parse_database(self.database(), self.source, 'x86_64')[0]
        package.pop('embedded_signature')
        package['signature_sha256'] = 'b'*64
        settings = dict(self.settings, repository='fansionia', pages_url='https://pages.example',
                        public_url='https://packages.example')
        snapshot = 'a'*32
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site/'keys').mkdir()
            repository.write_json(site/'snapshots.json', [snapshot])
            repository.write_json(site/'snapshots'/snapshot/'manifest.json', {'packages': [package], 'files': {}})
            output = site/'worker.mjs'
            repository.worker(site, settings, '', snapshot, 'active', output)
            config = json.loads(output.with_suffix('.json').read_text())
            path = '/x86_64/'+package['filename']
            self.assertEqual(config['assets'][path], package['url'])
            self.assertEqual(config['assets'][path.replace(':', '%3A')], package['url'])
            plan = mirror.snapshot_plan(site, settings, snapshot)
            self.assertEqual(plan[path]['source'], package['url'])
            self.assertTrue(plan[path]['tag'].startswith('upstream-fixture-'))


if __name__ == '__main__':
    unittest.main()
