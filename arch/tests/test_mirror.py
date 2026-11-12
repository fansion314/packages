"""Mirror publication, recovery and reference-based collection boundaries."""
import json
import io
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mirror
import repository


class FakeClient:
    def __init__(self):
        self.uploaded = {}
        self.sources = {}
        self.deleted = []

    def upload(self, item, source):
        self.uploaded[(item['tag'], item['filename'])] = item.copy()
        self.sources[(item['tag'], item['filename'])] = source

    def delete(self, item):
        self.deleted.append(item.copy())
        self.uploaded.pop((item['tag'], item['filename']), None)


class OriginProbeTests(unittest.TestCase):
    def test_acquisition_outages_recover_but_unsupported_methods_do_not(self):
        url = 'https://upstream.example/foo.pkg.tar.zst'
        for code in [404, 410, 403, 405, 429, 500, 503]:
            with self.subTest(code=code), patch.object(mirror.urllib.request, 'urlopen',
                    side_effect=urllib.error.HTTPError(url, code, 'fixture', {}, None)) as probe:
                self.assertEqual(mirror.origin_unavailable(url), code != 405)
                self.assertEqual(probe.call_args.args[0].get_method(), 'HEAD')
        with patch.object(mirror.urllib.request, 'urlopen', side_effect=urllib.error.URLError('timeout')):
            self.assertTrue(mirror.origin_unavailable(url))
        with patch.object(mirror.urllib.request, 'urlopen', return_value=MagicMock()):
            self.assertFalse(mirror.origin_unavailable(url))


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        probe = patch.object(mirror, 'origin_unavailable', return_value=False)
        self.origin_unavailable = probe.start()
        self.addCleanup(probe.stop)
        self.site = Path(self.temporary.name)
        self.settings = {'architecture': 'x86_64', 'repository': 'fansionia',
                         'pages_url': 'https://pages.example', 'public_url': 'https://packages.example',
                         'mirror': {'repository': 'test/mirror', 'max_bytes': 1024*1024}}
        (self.site/'keys').mkdir()
        (self.site/'keys/fansionia.asc').write_text('public key')
        self.client = FakeClient()
        self.sources = {}

    def upstream_snapshot(self, snapshot):
        package = self.snapshot(snapshot, '1')[0]
        package.update(upstream='fixture', repository='upstream/fixture', project='fixture')
        manifest_path = self.site/'snapshots'/snapshot/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['packages'] = [package]
        repository.write_json(manifest_path, manifest)
        repository.write_json(self.site/'snapshots.json', [snapshot])
        mirror.stage(self.site, self.settings, '', snapshot)
        self.sync()
        self.accept(snapshot)
        return package

    def test_removed_upstream_repairs_a_pending_active_snapshot_without_resigning(self):
        a = 'a'*32
        package = self.upstream_snapshot(a)
        manifest_path = self.site/'snapshots'/a/'manifest.json'
        original = manifest_path.read_bytes()
        urls = mirror.archived_urls(mirror.read_state(self.site, self.settings), self.settings, package)
        self.sources.pop(package['url'])
        self.sources.pop(package['signature_url'])
        self.origin_unavailable.return_value = True
        state = mirror.stage(self.site, self.settings, a, a)
        route = '/x86_64/'+package['filename']
        self.assertEqual(set(state['pinned']), {route, route+'.sig'})
        self.sync()
        self.accept(a)
        self.assertEqual(manifest_path.read_bytes(), original)
        output = self.site/'worker.mjs'
        repository.worker(self.site, self.settings, a, a, 'active', output)
        config = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual(config['assets'][route], urls['archive_url'])
        self.assertEqual(config['assets'][route+'.sig'], urls['signature_archive_url'])
        # A retry cannot silently move the original bytes back to a mutable URL.
        self.origin_unavailable.reset_mock(return_value=True)
        self.origin_unavailable.return_value = False
        mirror.stage(self.site, self.settings, a, a)
        self.origin_unavailable.assert_not_called()
        self.sync()
        self.accept(a)
        self.assertEqual(manifest_path.read_bytes(), original)

    def test_outage_recovers_pending_and_retained_routes_without_resigning(self):
        a, b = 'a'*32, 'b'*32
        package = self.upstream_snapshot(a)
        original = (self.site/'snapshots'/a/'manifest.json').read_bytes()
        self.snapshot(b, '2')
        repository.write_json(self.site/'snapshots.json', [a, b])
        self.sources.pop(package['url'])
        self.sources.pop(package['signature_url'])
        self.origin_unavailable.return_value = True
        mirror.stage(self.site, self.settings, a, b)
        self.sync()
        self.accept(b)
        self.assertEqual((self.site/'snapshots'/a/'manifest.json').read_bytes(), original)
        output = self.site/'worker.mjs'
        repository.worker(self.site, self.settings, a, b, 'active', output)
        assets = json.loads(output.with_suffix('.json').read_text())['assets']
        route = '/x86_64/'+package['filename']
        for suffix in ['', '.sig']:
            self.assertTrue(assets[route+suffix].startswith('https://cnb.cool/'))
        self.assertEqual(assets['/x86_64/foo-2-1-any.pkg.tar.zst'],
                         'https://github.com/test/foo/releases/download/v2/foo-2-1-any.pkg.tar.zst')

    def test_removed_upstream_requires_both_verified_receipts_and_exact_ledger(self):
        a = 'a'*32
        package = self.upstream_snapshot(a)
        original = mirror.read_state(self.site, self.settings)
        for invalid in ['unverified', 'missing-signature', 'wrong-hash']:
            state = json.loads(json.dumps(original))
            if invalid == 'unverified':
                state['snapshots'][a]['verified'] = False
            else:
                item = state['snapshots'][a]['routes']['/x86_64/'+package['filename']+'.sig']
                url = mirror.location(state['repository'], item['tag'], item['filename'])
                if invalid == 'missing-signature':
                    del state['objects'][url]
                else:
                    state['objects'][url]['sha256'] = '0'*64
            repository.write_json(self.site/mirror.STATE, state)
            before = (self.site/mirror.STATE).read_bytes()
            self.origin_unavailable.return_value = True
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'No verified immutable'):
                mirror.stage(self.site, self.settings, a, a)
            self.assertEqual((self.site/mirror.STATE).read_bytes(), before)

    def test_recovered_copies_follow_all_retained_primary_database_references(self):
        a, b, c, d = ('a'*32, 'b'*32, 'c'*32, 'd'*32)
        package = self.upstream_snapshot(a)
        url = mirror.archived_urls(mirror.read_state(self.site, self.settings), self.settings, package)['archive_url']
        self.origin_unavailable.return_value = True
        # The new candidate no longer contains this upstream. Freeze the old
        # verified mirror's copy before its last mirror-database reference ages out.
        for previous, candidate, version in [(a, b, '2'), (b, c, '3'), (c, d, '4')]:
            self.snapshot(candidate, version)
            index = json.loads((self.site/'snapshots.json').read_text())+[candidate]
            repository.write_json(self.site/'snapshots.json', index)
            mirror.stage(self.site, self.settings, previous, candidate)
            self.sync()
            self.accept(candidate)
        state = mirror.read_state(self.site, self.settings)
        self.assertEqual(state['successful'], [c, d])
        self.assertIn(url, state['objects'])
        self.assertNotIn('archive_url', json.loads((self.site/'snapshots'/a/'manifest.json').read_text())['packages'][0])
        repository.write_json(self.site/'snapshots.json', [c, d])
        mirror.stage(self.site, self.settings, d, d)
        self.sync()
        self.accept(d)
        self.assertNotIn(url, mirror.read_state(self.site, self.settings)['objects'])

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
        mirrored = {mirror.location(self.settings['mirror']['repository'], tag, filename): source
                    for (tag, filename), source in self.client.sources.items()}
        def download(url, destination, digest):
            source = mirrored.get(url) or self.sources[url]
            self.assertEqual(mirror.checksum(source), digest)
            return source
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
        self.assertIn('snapshot-'+b, assets['/mirror/x86_64/fansionia.db'])
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

    def test_retry_reads_existing_mirror_when_original_source_is_gone(self):
        a = 'a'*32
        self.snapshot(a, '1')
        mirror.stage(self.site, self.settings, '', a)
        self.sync()
        self.sources.clear()
        mirror.stage(self.site, self.settings, '', a)
        # Both the immutable cache source and the mirror bytes are checked;
        # reusing a ledger entry must never require the removed upstream URL.
        self.sync()

    def test_interrupted_upload_falls_back_only_for_missing_attachment(self):
        a = 'a'*32
        package = self.snapshot(a, '1')[0]
        mirror.stage(self.site, self.settings, '', a)
        self.sync()
        state = mirror.read_state(self.site, self.settings)
        item = state['snapshots'][a]['routes']['/x86_64/'+package['filename']]
        url = mirror.location(state['repository'], item['tag'], item['filename'])
        mirror.stage(self.site, self.settings, '', a)
        mirrored = {mirror.location(state['repository'], tag, filename): source
                    for (tag, filename), source in self.client.sources.items()}
        def download(source, destination, digest):
            if source == url:
                raise urllib.error.HTTPError(source, 404, 'not uploaded yet', {}, None)
            return mirrored.get(source) or self.sources[source]
        with patch.object(mirror, 'download', side_effect=download) as fetch, \
                patch.object(mirror, 'verify_remote'):
            mirror.sync(self.site, self.settings, self.client)
        urls = [call.args[0] for call in fetch.call_args_list]
        self.assertIn(url, urls)
        self.assertIn(package['url'], urls)
        mirror.stage(self.site, self.settings, '', a)
        with patch.object(mirror, 'download', side_effect=ValueError('checksum mismatch')) as fetch, \
                patch.object(mirror, 'verify_remote'):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                mirror.sync(self.site, self.settings, self.client)
        self.assertEqual(fetch.call_count, 1)

    def test_frozen_upstream_survives_mirror_retention_and_repairs_primary_routes(self):
        a, b, c, d = ('a'*32, 'b'*32, 'c'*32, 'd'*32)
        package = self.snapshot(a, '1')[0]
        package.update(upstream='fixture', repository='upstream/fixture', project='fixture')
        manifest_path = self.site/'snapshots'/a/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['packages'] = [package]
        repository.write_json(manifest_path, manifest)
        mirror.stage(self.site, self.settings, '', a)
        self.sync()
        self.accept(a)
        state = mirror.read_state(self.site, self.settings)
        pinned = dict(package, **mirror.archived_urls(state, self.settings, package))
        self.snapshot(b, '2')
        path = self.site/'snapshots'/b/'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['packages'].append(pinned)
        repository.write_json(path, manifest)
        repository.write_json(self.site/'snapshots.json', [a, b])
        mirror.stage(self.site, self.settings, a, b)
        self.sync()
        self.accept(b)
        # Later releases no longer include the old upstream. Its immutable
        # copy must outlive the two mirror databases for cached primary DBs.
        for previous, candidate, version in [(b, c, '3'), (c, d, '4')]:
            self.snapshot(candidate, version)
            index = json.loads((self.site/'snapshots.json').read_text())+[candidate]
            repository.write_json(self.site/'snapshots.json', index)
            mirror.stage(self.site, self.settings, previous, candidate)
            self.sync()
            self.accept(candidate)
        state = mirror.read_state(self.site, self.settings)
        self.assertEqual(state['successful'], [c, d])
        self.assertIn(pinned['archive_url'], state['objects'])
        for phase in ['prepare', 'active']:
            output = self.site/(phase+'.mjs')
            repository.worker(self.site, self.settings, c, d, phase, output)
            config = json.loads(output.with_suffix('.json').read_text())
            route = '/x86_64/'+package['filename']
            self.assertEqual(config['assets'][route], pinned['archive_url'])
            self.assertEqual(config['assets'][route+'.sig'], pinned['signature_archive_url'])
        state['pinned'][route]['sha256'] = '0'*64
        repository.write_json(self.site/mirror.STATE, state)
        with self.assertRaisesRegex(ValueError, 'Pinned upstream'):
            mirror.routes(self.site, self.settings, d)

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

    def test_cleanup_waits_for_retired_routes_to_disappear(self):
        import state as publication_state
        a, b = 'a'*32, 'b'*32
        self.snapshot(a, '1')
        self.snapshot(b, '2')
        mirror.stage(self.site, self.settings, '', a)
        self.sync()
        self.accept(a)
        mirror.stage(self.site, self.settings, a, b)
        self.sync()
        mirror.finish(self.site, self.settings, b, self.public(b, [a, b]))
        stale = self.public(b, ['retired', a, b])
        matching = self.public(b, [a, b])
        with patch.object(publication_state, 'public_status', side_effect=[stale, matching]) as fetch, \
                patch.object(mirror.time, 'sleep', side_effect=lambda _: self.assertFalse(self.client.deleted)) as sleep:
            mirror.prune(self.site, self.settings, self.client)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once()
        self.assertFalse(mirror.read_state(self.site, self.settings)['cleanup_pending'])
        with patch.object(publication_state, 'public_status', return_value=stale), \
                patch.object(mirror.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'retained public'):
                mirror.prune(self.site, self.settings, self.client)

    def test_epoch_filename_routes_to_cnb_safe_name_with_original_bytes(self):
        a = 'a'*32
        package = self.snapshot(a, '1')[0]
        package['filename'] = package['filename'].replace('foo-', 'foo-1:')
        manifest_path = self.site/'snapshots'/a/'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['packages'] = [package]
        repository.write_json(manifest_path, manifest)
        state = mirror.stage(self.site, self.settings, '', a)
        path = '/x86_64/'+package['filename']
        item = state['snapshots'][a]['routes'][path]
        self.assertNotIn(':', item['filename'])
        self.assertEqual(item['source'], package['url'])
        self.assertEqual(item['sha256'], package['sha256'])
        self.sync()
        # Re-stage/retry a pending candidate without modifying its database.
        mirror.stage(self.site, self.settings, '', a)
        self.sync()
        routes, _ = mirror.routes(self.site, self.settings, a)
        self.assertIn('/mirror'+path, routes)
        self.assertTrue(routes['/mirror'+path].endswith('/'+item['filename']))
        self.assertNotIn('%3A', routes['/mirror'+path])

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

    def test_null_assets_on_new_cnb_release_uploads_with_permanent_retention(self):
        client = mirror.Client('test/mirror', 'not-a-real-token')
        source = self.site/'new-attachment'
        source.write_bytes(b'new attachment')
        item = {'tag': 'new', 'filename': source.name, 'size': source.stat().st_size,
                'sha256': mirror.checksum(source)}
        upload = {'upload_url': 'https://storage.example/upload',
                  'verify_url': 'https://api.cnb.cool/test/mirror/-/releases/123/asset-upload-confirmation/t/path'}
        with patch.object(client, 'release', return_value={'id': '123', 'assets': None}), \
                patch.object(client, 'request', side_effect=[upload, None]) as api, \
                patch.object(client.opener, 'open', return_value=io.BytesIO()) as put:
            self.assertTrue(client.upload(item, source))
        self.assertEqual(api.call_args_list[0].args[2]['ttl'], 0)
        self.assertFalse(api.call_args_list[0].args[2]['overwrite'])
        self.assertTrue(api.call_args_list[1].args[1].endswith('?ttl=0'))
        self.assertEqual(put.call_count, 1)

    def test_legacy_urls_are_preserved_while_new_tags_include_names_and_versions(self):
        a = 'a'*32
        package = self.snapshot(a, '1')[0]
        identity = mirror.hashlib.sha256(mirror.canonical([package['repository'], package['tag']])).hexdigest()[:32]
        legacy = 'pacman-package-'+identity
        objects = {'old': {'tag': legacy}}
        before = mirror.snapshot_plan(self.site, self.settings, a, objects)
        fresh = mirror.snapshot_plan(self.site, self.settings, a)
        path = '/x86_64/'+package['filename']
        self.assertEqual(before[path]['tag'], legacy)
        self.assertEqual(fresh[path]['tag'], 'foo-v1')
        self.assertIn('foo 1-1', before[path]['title'])
        client = mirror.Client('test/mirror', 'not-a-real-token')
        release = {'id': '123', 'body': mirror.OWNER, 'name': legacy, 'assets': []}
        with patch.object(client, 'request', side_effect=[release, None]) as api:
            client.release(legacy, title='foo 1-1')
        self.assertEqual(api.call_args_list[1].args, ('PATCH', '/test/mirror/-/releases/123', {'name': 'foo 1-1'}))


if __name__ == '__main__':
    unittest.main()
