"""Outages defer only affected packages, with verified originals and fresh retries."""
import contextlib
import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mirror
import repository
import upstream


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.settings = {'architecture': 'x86_64', 'mirror': {'repository': 'test/mirror'}}
        self.state = {'repository': 'test/mirror', 'objects': {},
                      'snapshots': {'old': {'verified': True, 'routes': {}}}}

    def package(self, name, version='1.0.0', external=False):
        filename = f'{name}-{version}-1-any.pkg.tar.zst'
        package = {'project': name, 'repository': 'test/'+name, 'tag': 'v'+version,
                   'name': name, 'version': version+'-1', 'architecture': 'any', 'filename': filename,
                   'url': 'https://github.com/test/'+name+'/releases/download/v'+version+'/'+filename,
                   'signature_url': 'https://github.com/test/'+name+'/releases/download/v'+version+'/'+filename+'.sig',
                   'sha256': hashlib.sha256((name+version).encode()).hexdigest(),
                   'signature_sha256': hashlib.sha256((name+version+'sig').encode()).hexdigest()}
        if external:
            package.update(upstream=name, project=name, repository='upstream/'+name)
        return package

    def preserve(self, package):
        for suffix, prefix in [('', ''), ('.sig', 'signature_')]:
            item = {'tag': package['tag'], 'filename': package['filename']+suffix,
                    'sha256': package[prefix+'sha256']}
            self.state['snapshots']['old']['routes']['/x86_64/'+package['filename']+suffix] = item
            self.state['objects'][mirror.location('test/mirror', item['tag'], item['filename'])] = dict(item, size=1)

    def project(self, name):
        return {'id': name, 'repository': 'test/'+name, 'packages': [name], 'tag_pattern': r'^v\d+\.\d+\.\d+$'}

    def release(self, package, signed=True):
        return {'draft': False, 'tag_name': package['tag'], 'assets': [
            {'name': package['filename']+suffix, 'digest': 'sha256:'+package[prefix+'sha256'],
             'browser_download_url': package[prefix+'url']}
            for suffix, prefix in ([('', ''), ('.sig', 'signature_')] if signed else [('', '')])]}

    def test_api_and_incomplete_release_defer_old_package_and_next_sync_selects_new(self):
        old, new, normal = self.package('foo'), self.package('foo', '2.0.0'), self.package('bar', '3.0.0')
        self.preserve(old)
        settings = dict(self.settings, projects=[self.project('foo'), self.project('bar')])
        for failure in ['api', 'incomplete']:
            def github(path):
                if 'test/foo/' in path:
                    if failure == 'api':
                        raise subprocess.CalledProcessError(1, ['gh', 'api'])
                    return [[self.release(new, signed=False)]]
                return [[self.release(normal)]]
            summary = io.StringIO()
            with self.subTest(failure=failure), patch.object(repository, 'github', side_effect=github), \
                    contextlib.redirect_stdout(summary):
                selected = repository.discover(settings, {'packages': [old]}, self.state)
            frozen = next(p for p in selected if p['name'] == 'foo')
            self.assertEqual(frozen['version'], old['version'])
            self.assertTrue(frozen['archive_url'].startswith('https://cnb.cool/'))
            self.assertIn(normal, selected)
            self.assertIn('next sync retries', summary.getvalue())
        with patch.object(repository, 'github', side_effect=lambda path: [[self.release(new if 'test/foo/' in path else normal)]]):
            selected = repository.discover(settings, {'packages': [frozen]}, self.state)
        self.assertIn(new, selected)
        self.assertNotIn('archive_url', next(p for p in selected if p['name'] == 'foo'))

    def test_new_failed_package_is_skipped_but_bad_digest_or_foreign_url_is_not_an_outage(self):
        package = self.package('foo')
        settings = dict(self.settings, projects=[self.project('foo')])
        with patch.object(repository, 'github', return_value=[[self.release(package, signed=False)]]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(repository.discover(settings), [])
        for field, value in [('digest', 'sha256:not-a-hash'), ('browser_download_url', 'https://evil.example/foo')]:
            release = self.release(package)
            release['assets'][0][field] = value
            with self.subTest(field=field), patch.object(repository, 'github', return_value=[[release]]), \
                    self.assertRaises(ValueError):
                repository.discover(settings)

    def test_download_outage_keeps_verified_old_input_while_other_packages_validate(self):
        old, new, normal = self.package('foo'), self.package('foo', '2.0.0'), self.package('bar')
        self.preserve(old)
        def download(url, path, expected):
            if url == new['url']:
                raise urllib.error.HTTPError(url, 503, 'unavailable', {}, None)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b'fixture')
            return path
        with tempfile.TemporaryDirectory() as temporary, patch.object(repository, 'ROOT', Path(temporary)/'arch'), \
                patch.object(repository, 'download', side_effect=download), \
                patch.object(repository, 'verify_package') as verify, contextlib.redirect_stdout(io.StringIO()):
            selected = repository.acquire_packages([new, normal], {'packages': [old]}, self.settings, self.state)
        self.assertEqual(selected[0]['sha256'], old['sha256'])
        self.assertTrue(selected[0]['signature_archive_url'].startswith('https://cnb.cool/'))
        self.assertEqual(selected[1], normal)
        self.assertEqual(verify.call_args.args[0], normal)
        with patch.object(repository, 'download', side_effect=ValueError('checksum mismatch')), self.assertRaisesRegex(ValueError, 'checksum'):
            repository.acquire_packages([new], {'packages': [old]}, self.settings, self.state)
        with tempfile.TemporaryDirectory() as temporary, patch.object(repository, 'ROOT', Path(temporary)/'arch'), \
                patch.object(repository, 'download', side_effect=download), \
                patch.object(repository, 'verify_package', side_effect=subprocess.CalledProcessError(1, ['gpgv'])), \
                self.assertRaises(subprocess.CalledProcessError):
            repository.acquire_packages([normal], None, self.settings, self.state)

    def test_missing_original_receipts_never_become_a_trusted_fallback(self):
        old = self.package('foo')
        self.preserve(old)
        self.state['snapshots']['old']['verified'] = False
        with self.assertRaisesRegex(ValueError, 'No verified immutable'):
            repository.defer_packages(self.settings, self.state, [old], 'foo', TimeoutError())

    def test_upstream_database_and_signature_outages_are_scoped_and_retry_next_run(self):
        source = {'id': 'foo', 'server': 'https://upstream.example/$arch',
                  'key': 'upstream-keys/foo.asc', 'fingerprint': 'A'*40}
        old, new = self.package('foo', external=True), self.package('foo', '2.0.0', external=True)
        new['signature_url'] = 'https://upstream.example/foo.sig'
        settings = dict(self.settings, upstreams=[source])
        for failed in ['database', 'signature']:
            def fetch(url, *args):
                if (failed == 'database' and url.endswith('.db')) or url == new['signature_url']:
                    raise urllib.error.HTTPError(url, 503, 'unavailable', {}, None)
                return b'fixture'
            with self.subTest(failed=failed), patch.object(upstream, 'fetch', side_effect=fetch), \
                    patch.object(upstream, 'verify'), patch.object(upstream, 'parse_database', return_value=[new]), \
                    patch.object(upstream.hashlib, 'sha256') as sha:
                sha.return_value.hexdigest.return_value = new['signature_sha256']
                deferred = []
                def defer(source_id, name, error):
                    deferred.append((source_id, name))
                    return [old]
                self.assertEqual(upstream.discover(settings, [], defer), [old])
                self.assertEqual(deferred, [('foo', None if failed == 'database' else 'foo')])
        with patch.object(upstream, 'fetch', return_value=b'fixture'), patch.object(upstream, 'verify'), \
                patch.object(upstream, 'parse_database', return_value=[new]):
            selected = upstream.discover(settings, [], lambda *_: self.fail('healthy source must retry normally'))
        self.assertEqual(selected[0]['version'], '2.0.0-1')


if __name__ == '__main__':
    unittest.main()
