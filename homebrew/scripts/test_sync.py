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
