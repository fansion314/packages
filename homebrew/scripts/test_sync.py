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
            self.assertIn('fansionia/tap/dnr', text)
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
        self.assertIn('fansionia/tap/mihomomo', cask)
        self.assertLess(cask.index('codesign'), cask.index('xattr'))
        self.assertIn('{{appdir}}/Clash Momo.app', cask)
        _, formula = sync.render('mihomomo', info)
        self.assertIn('capabilities["protocol"]', formula)
        self.assertIn('capabilities["managedMode"]', formula)
        self.assertNotIn('service do', formula)


class MirrorRenderTests(unittest.TestCase):
    def info(self, project, release=1, revision=2):
        version = '1.2.3'
        filename = f'{project}-{version}' + (f'-{release}' if release else '')
        filename += f'-macos-arm64-r{revision}.tar.gz'
        return {'repository': sync.PROJECTS[project][0], 'tag': 'upstream-tag',
                'version': version, 'release': release, 'revision': revision,
                'asset': filename, 'url': 'https://github.com/example/upstream/archive.tar.gz',
                'sha256': 'a' * 64}

    def test_all_projects_change_only_download_origin(self):
        for project in sync.PROJECTS:
            with self.subTest(project=project):
                info = self.info(project, release=0 if project == 'dnr' else 1)
                original = info.copy()
                github_path, github = sync.render(project, info)
                mirror_path, mirror = sync.render(project, info, source='cnb')
                self.assertEqual(github_path, mirror_path)
                self.assertEqual(mirror, github.replace(info['url'], sync.cnb_url(project, info)))
                self.assertIn('sha256 "' + info['sha256'] + '"', mirror)
                self.assertIn('url "https://cnb.cool/fansionia/packages/-/releases/download/', mirror)
                self.assertNotIn('fansion314/packages/', mirror)
                self.assertNotIn('@URL@', mirror)
                self.assertEqual(info, original)

    def test_tags_separate_projects_and_packaging_releases(self):
        self.assertEqual(sync.cnb_tag('dnr', self.info('dnr', release=0)), 'homebrew-dnr-v1.2.3')
        self.assertEqual(sync.cnb_tag('etcher-dnr', self.info('etcher-dnr')), 'homebrew-etcher-dnr-v1.2.3-1')
        first = self.info('pi-dnr')
        self.assertEqual(sync.cnb_tag('pi-dnr', first), 'homebrew-pi-dnr-v1.2.3-1')
        self.assertNotEqual(sync.cnb_tag('pi-dnr', first), sync.cnb_tag('pi-dnr', {**first, 'release': 2}))
        # macOS revisions have distinct immutable filenames within one version's Release.
        later = self.info('pi-dnr', revision=3)
        self.assertEqual(sync.cnb_tag('pi-dnr', first), sync.cnb_tag('pi-dnr', later))
        self.assertNotEqual(sync.cnb_url('pi-dnr', first), sync.cnb_url('pi-dnr', later))

    def test_internal_dependencies_stay_with_selected_tap(self):
        for source in ('github', 'cnb'):
            for project, dependency in [('pi-dnr', 'dnr'), ('etcher-dnr', 'dnr'), ('clash-momo', 'mihomomo')]:
                with self.subTest(source=source, project=project):
                    _, recipe = sync.render(project, self.info(project), source=source)
                    self.assertIn(f'fansionia/tap/{dependency}', recipe)
                    self.assertNotIn('fansion314/packages/', recipe)

    def test_invalid_source_and_asset_identity_fail_closed(self):
        info = self.info('dnr')
        with self.assertRaises(ValueError):
            sync.render('dnr', info, source='other')
        with self.assertRaises(ValueError):
            sync.cnb_tag('unknown', info)
        for version, release in [('1.2', 1), ('../1.2.3', 1), ('1.2.3', -1), ('1.2.3', True)]:
            with self.subTest(version=version, release=release), self.assertRaises(ValueError):
                sync.cnb_tag('dnr', {**info, 'version': version, 'release': release})
        for name in ('../archive.tar.gz', '.', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                sync.cnb_url('dnr', {**info, 'asset': name})
