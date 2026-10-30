import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('sync', Path(__file__).with_name('sync.py'))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class ReleaseSelectionTests(unittest.TestCase):
    def fixture(self, revision=1):
        name = f'dnr-0.4.2-macos-arm64-r{revision}.tar.gz'
        return {'tag_name': 'v0.4.2', 'draft': False, 'prerelease': False,
                'assets': [{'name': name, 'browser_download_url': f'https://github.com/fansion314/dnr/releases/download/v0.4.2/{name}'},
                           {'name': name + '.sha256'}]}

    def test_numeric_revisions_and_incomplete_releases(self):
        incomplete = self.fixture(11)
        incomplete['assets'].pop()
        found = sync.candidates('dnr', [self.fixture(2), self.fixture(10), incomplete])
        self.assertEqual(found[-1][1]['revision'], 10)

    def test_drafts_and_prereleases_are_never_imported(self):
        for field in ['draft', 'prerelease']:
            release = self.fixture()
            release[field] = True
            self.assertEqual(sync.candidates('dnr', [release]), [])

    def test_wrong_download_host_is_rejected(self):
        release = self.fixture()
        release['assets'][0]['browser_download_url'] = 'https://example.com/package.tar.gz'
        with self.assertRaises(ValueError):
            sync.candidates('dnr', [release])

    def test_other_project_tags_are_ignored(self):
        release = self.fixture()
        release['tag_name'] = 'songjian-v0.4.2'
        self.assertEqual(sync.candidates('dnr', [release]), [])


if __name__ == '__main__':
    unittest.main()

class NewTapTests(unittest.TestCase):
    def test_shared_runtime_uses_new_tap(self):
        for project in ['pi-dnr', 'etcher-dnr']:
            _, text = sync.render(project, {'version': '1.2.3', 'release': 1, 'revision': 1,
                                           'sha256': 'a'*64, 'url': 'https://example.com/package',
                                           'repository': 'fansion314/etcher'})
            self.assertIn('fansion314/packages/dnr', text)
            self.assertNotIn('fansion314/dnr/dnr', text)


class MomoReleaseTests(unittest.TestCase):
    def release(self, project, version, pkgrel, revision, checksum=True):
        tag = f'{project}-v{version}-{pkgrel}'
        name = f'{project}-{version}-{pkgrel}-macos-arm64-r{revision}.tar.gz'
        assets = [{'name': name, 'browser_download_url': f'https://github.com/fansion314/momo/releases/download/{tag}/{name}'}]
        if checksum:
            assets.append({'name': name + '.sha256'})
        return {'tag_name': tag, 'draft': False, 'prerelease': False, 'assets': assets}

    def test_numeric_selection_and_tag_family(self):
        releases = [self.release('mihomomo', '1.19.9', 2, 10), self.release('mihomomo', '1.19.10', 1, 2),
                    self.release('mihomomo', '1.19.10', 1, 10), self.release('clash-momo', '9.0.0', 1, 1)]
        self.assertEqual(sync.candidates('mihomomo', releases)[-1][0], [1, 19, 10, 1, 10])

    def test_latest_release_and_revision_fail_closed(self):
        older = self.release('clash-momo', '2.0.3', 1, 1)
        latest = self.release('clash-momo', '2.0.4', 1, 1)
        latest['assets'] = []
        with self.assertRaises(ValueError):
            sync.candidates('clash-momo', [older, latest])
        latest = self.release('clash-momo', '2.0.4', 1, 1)
        latest['assets'] += self.release('clash-momo', '2.0.4', 1, 2, False)['assets']
        with self.assertRaises(ValueError):
            sync.candidates('clash-momo', [older, latest])
        self.assertEqual(sync.candidates('clash-momo', [self.release('clash-momo', '2.0.2', 1, 1, False), older])[-1][1]['version'], '2.0.3')

    def test_render_security_and_independent_formula(self):
        info = {'version': '2.0.4', 'release': 1, 'revision': 1, 'sha256': 'a'*64,
                'url': 'https://example.com/archive', 'repository': 'fansion314/momo'}
        _, cask = sync.render('clash-momo', info)
        self.assertIn('fansion314/packages/mihomomo', cask)
        self.assertLess(cask.index('codesign'), cask.index('xattr'))
        self.assertIn('{{appdir}}/Clash Momo.app', cask)
        _, formula = sync.render('mihomomo', info)
        self.assertIn('capabilities["protocol"]', formula)
        self.assertIn('capabilities["managedMode"]', formula)
        self.assertNotIn('service do', formula)
