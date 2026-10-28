import importlib.util
import hashlib
import io
import json
import tarfile
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1]/'scripts/sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def test_reject_escaping_paths(self):
        for value in ['../secret', '/root/file', 'app/../../secret', '']:
            with self.assertRaises(ValueError):
                sync.safe_path(value)

    def test_source_alias_and_arch_version(self):
        self.assertEqual(sync.source_name('app.tar.gz::https://example.com/download'), ('app.tar.gz', 'https://example.com/download'))
        self.assertEqual(sync.version(sync.metadata('pkgver = 2.0.0beta.41\npkgrel = 2\n')), '0:2.0.0beta.41-2')

    def test_missing_local_companion_fails(self):
        with self.assertRaisesRegex(ValueError, 'Missing recipe companion'):
            sync.check_local_sources({'.SRCINFO': b'source = launcher.sh\nsha256sums = SKIP\n'})

    def test_local_companion_digest_is_checked(self):
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            sync.check_local_sources({'.SRCINFO': b'source = launcher.sh\nsha256sums = bad\n', 'launcher.sh': b'changed'})

    def test_binary_sources_cannot_escape_project(self):
        with self.assertRaisesRegex(ValueError, 'this project'):
            sync.GitHub().asset('fansion314/dnr', 'https://example.com/app.tar.gz')

    def test_skip_is_replaced_with_verified_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'app.tar.gz'
            file.write_bytes(b'archive')
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            class FakeGitHub:
                def asset(self, repository, url):
                    return {'name': file.name, 'digest': 'sha256:' + digest, 'size': file.stat().st_size}
                def download(self, url, expected):
                    return file
            files = {'PKGBUILD': b'pkgname=app-bin\nsha256sums=(SKIP)\n', '.SRCINFO': b'source = https://github.com/fansion314/app/releases/download/v1/app.tar.gz\nsha256sums = SKIP\n'}
            sync.pin_binary(files, 'fansion314/app', FakeGitHub())
            self.assertEqual(sync.metadata(files['.SRCINFO'].decode())['sha256sums'], [digest])
            self.assertIn(digest.encode(), files['PKGBUILD'])
            files['.SRCINFO'] = files['.SRCINFO'].replace(digest.encode(), b'0'*64)
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                sync.pin_binary(files, 'fansion314/app', FakeGitHub())


if __name__ == '__main__':
    unittest.main()

class MultiPackageReleaseTests(unittest.TestCase):
    def setUp(self):
        self.settings = {'tag_pattern': r'^motrix-v([0-9]+)\.([0-9]+)\.([0-9]+)(?:-(alpha|beta|rc)\.([0-9]+))?-([1-9][0-9]*)$'}

    def test_numeric_version_and_prerelease_order(self):
        values = ['motrix-v2.0.0-beta.9-2', 'motrix-v2.0.0-beta.10-1', 'motrix-v2.0.0-1', 'motrix-v2.0.0-2', 'motrix-v2.0.1-alpha.1-1']
        self.assertEqual(sorted(reversed(values), key=lambda t: sync.release_key(self.settings, t)), values)

    def test_mygo_release_pattern_matches_the_sort_key_contract(self):
        sources = json.loads((Path(__file__).parents[1]/'sources.json').read_text())
        project = next(p for p in sources['projects'] if p['id'] == 'mygo-cloudmusic')
        self.assertEqual(sync.release_key(project['release_bundle'], 'mygo-cloudmusic-v0.1.20-1'),
                         (0, 1, 20, 3, 0, 1))

    def test_other_packages_are_not_candidates(self):
        with self.assertRaises(ValueError):
            sync.release_key(self.settings, 'obsidian-v2.0.0-1')

class SharedMomoReleaseTests(unittest.TestCase):
    def test_each_project_selects_its_own_release_bundle(self):
        sources = json.loads((Path(__file__).parents[1]/'sources.json').read_text())
        projects = [p for p in sources['projects'] if p['id'] in ('clash-momo', 'mihomomo')]
        self.assertEqual({p['id'] for p in projects}, {'clash-momo', 'mihomomo'})
        with tempfile.TemporaryDirectory() as temporary:
            files = {}
            releases = []
            for name, version in [('clash-momo', '0.1.0'), ('mihomomo', '0.1.0'),
                                  ('clash-momo', '0.2.0')]:
                tag = f'{name}-v{version}-1'
                archive = Path(temporary)/f'{tag}.tar.gz'
                with tarfile.open(archive, 'w:gz') as bundle:
                    content = f'pkgver={version}\n'.encode()
                    info = tarfile.TarInfo(f'aur/{name}/PKGBUILD')
                    info.size = len(content)
                    bundle.addfile(info, io.BytesIO(content))
                url = f'https://github.com/fansion314/momo/releases/download/{tag}/{name}-aur.tar.gz'
                files[url] = archive
                releases.append({'tag_name': tag, 'draft': False, 'assets': [{
                    'name': f'{name}-aur.tar.gz', 'browser_download_url': url,
                    'digest': 'sha256:'+hashlib.sha256(archive.read_bytes()).hexdigest()}]})
            releases.append({'tag_name': 'mihomomo-v9.0.0-1', 'draft': True, 'assets': []})

            class FakeGitHub:
                def releases(self, repository):
                    assert repository == 'fansion314/momo'
                    return releases

                def download(self, url, digest):
                    file = files[url]
                    assert hashlib.sha256(file.read_bytes()).hexdigest() == digest
                    return file

            selected = {p['id']: sync.recipe_files(p, FakeGitHub()) for p in projects}
            self.assertEqual(selected['clash-momo'][0], 'clash-momo-v0.2.0-1')
            self.assertEqual(selected['mihomomo'][0], 'mihomomo-v0.1.0-1')
            for project in projects:
                self.assertEqual(set(selected[project['id']][1]),
                                 {f'aur/{project["id"]}/PKGBUILD'})
