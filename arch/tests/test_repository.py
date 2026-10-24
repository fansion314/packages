import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('repository', ROOT/'repository.py')
repository = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repository)


class RepositoryTests(unittest.TestCase):
    def release(self, version='1.0.0', signature=True):
        name = f'foo-{version}-1-x86_64.pkg.tar.zst'
        assets = [{'name': name, 'digest': 'sha256:'+'a'*64,
                   'browser_download_url': f'https://github.com/test/foo/releases/download/v{version}/{name}'}]
        if signature:
            assets.append({'name': name+'.sig', 'digest': 'sha256:'+'b'*64,
                           'browser_download_url': assets[0]['browser_download_url']+'.sig'})
        return {'tag_name': 'v'+version, 'draft': False, 'assets': assets}

    project = {'id': 'foo', 'repository': 'test/foo', 'tag_pattern': r'^v\d+\.\d+\.\d+$', 'packages': ['foo']}

    def test_incomplete_new_release_does_not_silently_fall_back(self):
        with self.assertRaisesRegex(ValueError, 'completely signed'):
            repository.select_release(self.project, [self.release(), self.release('2.0.0', False)])

    def test_numeric_versions_and_prerelease_promotion(self):
        tags = ['motrix-v2.0.0-beta.52-2', 'motrix-v2.0.0-1', 'motrix-v2.0.0-2', 'motrix-v2.0.10-1']
        self.assertEqual(sorted(reversed(tags), key=repository.version_key), tags)
        self.assertLess(repository.version_key('v0.5.5'), repository.version_key('v0.5.6'))

    def test_package_prefix_does_not_match_backend_variants(self):
        release = self.release()
        for variant in ['foo-cef', 'foo-webview']:
            for asset in list(release['assets'][:2]):
                copy = dict(asset)
                copy['name'] = copy['name'].replace('foo-1', variant+'-1')
                copy['browser_download_url'] = copy['browser_download_url'].replace('/foo-1', '/'+variant+'-1')
                release['assets'].append(copy)
        packages = repository.select_release(self.project, [release])
        self.assertEqual([p['filename'] for p in packages], ['foo-1.0.0-1-x86_64.pkg.tar.zst'])

    def test_foreign_download_url_and_missing_digest_are_rejected(self):
        for bad in ['url', 'digest']:
            release = self.release()
            if bad == 'url':
                release['assets'][0]['browser_download_url'] = 'https://evil.example/foo.pkg.tar.zst'
            else:
                release['assets'][0]['digest'] = None
            with self.assertRaises((ValueError, TypeError)):
                repository.select_release(self.project, [release])

    def test_downgrade_and_same_version_replacement_fail(self):
        package = repository.select_release(self.project, [self.release()])[0]
        previous = {'packages': [package]}
        with self.assertRaisesRegex(ValueError, 'downgrade'):
            repository.ensure_monotonic([package], previous, lambda a, b: -1)
        changed = dict(package, sha256='c'*64)
        with self.assertRaisesRegex(ValueError, 'same-version'):
            repository.ensure_monotonic([changed], previous, lambda a, b: 0)

    def test_both_worker_phases_keep_old_and_new_package_maps(self):
        settings = {'architecture':'x86_64', 'repository':'fansionia', 'pages_url':'https://pages.example',
                    'public_url':'https://packages.example'}
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site/'keys').mkdir()
            (site/'keys/fansionia.asc').write_text('public')
            repository.write_json(site/'snapshots.json', ['old','new'])
            for snapshot, version in [('old','1.0.0'),('new','2.0.0')]:
                package = repository.select_release(self.project, [self.release(version)])[0]
                repository.write_json(site/'snapshots'/snapshot/'manifest.json', {
                    'packages':[package], 'files':{'x86_64/fansionia.db':'a'*64}})
            for phase, active in [('prepare','old'),('active','new')]:
                output = site/(phase+'.mjs')
                repository.worker(site, settings, 'old', 'new', phase, output)
                config = json.loads(output.with_suffix('.json').read_text())
                self.assertEqual(config['active'], active)
                self.assertEqual(len([path for path in config['assets'] if path.endswith('.pkg.tar.zst')]), 2)


if __name__ == '__main__':
    unittest.main()
