"""Test immutable attachment publication and the exact candidate-to-Git boundary."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('homebrew_mirror', Path(__file__).with_name('mirror.py'))
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


class FakeClient:
    def __init__(self):
        self.uploads = []

    def upload(self, item, source):
        self.uploads.append((item.copy(), Path(source).read_bytes()))
        return True


class HomebrewMirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source'
        self.remote = self.root/'remote.git'
        self.candidate = self.root/'candidate'
        self.source.mkdir()
        self.run_git(self.source, 'init', '--initial-branch=main')
        self.records = {}
        for project in mirror.sync.PROJECTS:
            info = json.loads((mirror.ROOT/'homebrew/releases'/f'{project}.json').read_text())
            import hashlib
            info['sha256'] = hashlib.sha256(project.encode()).hexdigest()
            info['github_digest'] = 'sha256:'+info['sha256']
            self.records[project] = info
            mirror.write_json(self.source/'homebrew/releases'/f'{project}.json', info)
        self.run_git(self.source, 'add', '.')
        self.run_git(self.source, 'commit', '-m', 'maintenance')
        self.run_git(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        initial = self.root/'initial'
        self.run_git(self.root, 'clone', str(self.remote), str(initial))
        (initial/'README.md').write_text('# Fansionia pacman mirror\n')
        (initial/'unrelated.txt').write_text('keep me')
        self.run_git(initial, 'add', '.')
        self.run_git(initial, 'commit', '-m', 'seed')
        self.run_git(initial, 'push', 'origin', 'main')
        self.base = self.run_git(initial, 'rev-parse', 'HEAD')
        self.client = FakeClient()

    def run_git(self, path, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                                        '-C', str(path), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def files(self, info, directory):
        project = next(p for p, record in self.records.items() if record['asset'] == info['asset'])
        archive = directory/info['asset']
        archive.write_bytes(project.encode())
        checksum = directory/(info['asset']+'.sha256')
        checksum.write_text(info['sha256']+'  '+info['asset']+'\n')
        return archive, checksum

    def prepare(self):
        with patch.object(mirror, 'source_files', side_effect=self.files), patch.object(mirror, 'verify_remote') as verify:
            mirror.prepare(self.candidate, self.source, str(self.remote), self.client)
        self.assertEqual(verify.call_count, 10)

    def publish(self):
        with patch.object(mirror, 'REMOTE', str(self.remote)), patch.dict(os.environ, CNB_MIRROR_TOKEN='test-only'):
            mirror.publish(self.candidate)

    def test_full_snapshot_preserves_history_and_unrelated_files(self):
        self.prepare()
        self.assertEqual(len(self.client.uploads), 10)
        for item, data in self.client.uploads:
            self.assertTrue(item['tag'].startswith('homebrew-'))
            self.assertNotIn('pacman-', item['tag'])
            self.assertEqual(item['size'], len(data))
        self.publish()
        self.assertEqual(self.run_git(self.remote, 'show', 'main:unrelated.txt'), 'keep me')
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main^'), self.base)
        for project in mirror.sync.PROJECTS:
            state = json.loads(self.run_git(self.remote, 'show', f'main:homebrew/releases/{project}.json'))
            self.assertEqual(state['sha256'], self.records[project]['sha256'])
            self.assertTrue(state['url'].startswith('https://cnb.cool/fansionia/packages/-/releases/download/homebrew-'))
        dnr = self.run_git(self.remote, 'show', 'main:Formula/dnr.rb')
        self.assertIn('https://cnb.cool/', dnr)
        pi = self.run_git(self.remote, 'show', 'main:Formula/pi-dnr.rb')
        self.assertIn('fansionia/tap/dnr', pi)

    def test_tampered_candidate_cannot_publish(self):
        self.prepare()
        (self.candidate/'Formula/dnr.rb').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.publish()
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), self.base)

    def test_concurrent_remote_update_is_never_overwritten(self):
        self.prepare()
        other = self.root/'other'
        self.run_git(self.root, 'clone', str(self.remote), str(other))
        (other/'unrelated.txt').write_text('new user content')
        self.run_git(other, 'add', '.')
        self.run_git(other, 'commit', '-m', 'user change')
        self.run_git(other, 'push', 'origin', 'main')
        tip = self.run_git(self.remote, 'rev-parse', 'main')
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), tip)

    def test_same_version_cannot_change_digest_or_source(self):
        current = {**self.records['dnr'], 'upstream_url': self.records['dnr']['url']}
        for field in ('sha256', 'upstream_url', 'source_sha'):
            previous = {**current, field: 'different'}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'immutable'):
                mirror.compare(previous, current)
        previous = {**current, 'key': [999, 0, 0, 0, 0]}
        with self.assertRaisesRegex(ValueError, 'downgrade'):
            mirror.compare(previous, current)

    def test_anonymous_verification_failure_never_changes_public_main(self):
        with patch.object(mirror, 'source_files', side_effect=self.files), \
                patch.object(mirror, 'verify_remote', side_effect=ValueError('bad bytes')):
            with self.assertRaisesRegex(ValueError, 'bad bytes'):
                mirror.prepare(self.candidate, self.source, str(self.remote), self.client)
        self.assertFalse((self.candidate/'.git'/mirror.RECEIPT).exists())
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), self.base)

    def test_original_checksum_is_checked_before_upload(self):
        info = self.records['dnr']
        directory = self.root/'downloads'
        directory.mkdir()
        self.files(info, directory)
        (directory/info['asset']).write_text('corrupt')
        with patch.object(mirror.subprocess, 'run'), self.assertRaisesRegex(ValueError, 'mismatch'):
            mirror.source_files(info, directory)

    def test_release_record_cannot_redirect_to_another_host(self):
        with self.assertRaisesRegex(ValueError, 'URL'):
            mirror.validate_info('dnr', {**self.records['dnr'], 'url': 'https://evil.invalid/asset'})

    def test_second_identical_snapshot_is_noop(self):
        self.prepare()
        self.publish()
        tip = self.run_git(self.remote, 'rev-parse', 'main')
        self.candidate = self.root/'second'
        self.prepare()
        self.publish()
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), tip)

    def test_unrelated_staged_file_is_not_published(self):
        self.prepare()
        (self.candidate/'unrelated.txt').write_text('unexpected')
        self.run_git(self.candidate, 'add', 'unrelated.txt')
        with self.assertRaisesRegex(ValueError, 'Unrelated'):
            self.publish()
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), self.base)
