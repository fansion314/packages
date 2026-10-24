"""Draft discovery and public-release immutability regression coverage."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('publish', ROOT/'scripts/publish.py')
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class PublicationTests(unittest.TestCase):
    def scenario(self, draft, mismatch=False):
        with tempfile.TemporaryDirectory() as directory:
            before = Path.cwd()
            os.chdir(directory)
            try:
                output = Path('dist/bitwarden')
                output.mkdir(parents=True)
                info = {'id': 'bitwarden', 'version': '2026.10.0', 'pkgrel': 2}
                commit = 'a'*40
                (output/'build-info.json').write_text(json.dumps({'package': info, 'packaging_commit': commit}))
                (output/'application.pkg.tar.zst').write_bytes(b'payload')
                names = ['build-info.json', 'application.pkg.tar.zst']
                expected = {name: publish.digest(output/name) for name in names}
                (output/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in expected.items()))
                expected['SHA256SUMS'] = publish.digest(output/'SHA256SUMS')
                (output/'notes.md').write_text('notes')
                release = {'tag_name': 'bitwarden-v2026.10.0-2', 'draft': draft,
                           'target_commitish': commit,
                           'assets': [{'name': name, 'digest': 'sha256:'+digest} for name, digest in expected.items()]}
                if mismatch:
                    release['assets'][0]['digest'] = 'sha256:'+'0'*64
                calls = []
                def fake_gh(*args):
                    calls.append(args)
                    if args[:2] == ('api', '--paginate'):
                        # Matching draft is intentionally on the second page.
                        return json.dumps([[{'tag_name': 'unrelated-v1'}], [release]])
                    if args[0] == 'api':
                        return json.dumps({'sha': commit})
                    if args[:2] == ('release', 'upload'):
                        self.assertTrue(release['draft'])
                        return ''
                    if args[:2] == ('release', 'edit'):
                        release['draft'] = False
                        return ''
                    if args[:2] == ('release', 'view'):
                        return 'https://example.invalid/release'
                    self.fail(args)
                with patch.dict(os.environ, {'GITHUB_REF_NAME': release['tag_name'], 'GITHUB_REPOSITORY': 'fansion314/packages'}), patch.object(publish, 'gh', side_effect=fake_gh):
                    if mismatch:
                        with self.assertRaisesRegex(ValueError, 'bytes differ'):
                            publish.publish('bitwarden', commit)
                    else:
                        publish.publish('bitwarden', commit)
                writes = [call for call in calls if call[:2] in [('release', 'upload'), ('release', 'edit')]]
                self.assertEqual(len(writes), 2 if draft else 0)
            finally:
                os.chdir(before)

    def test_draft_on_a_later_page_can_be_completed(self):
        self.scenario(True)

    def test_identical_public_release_is_an_idempotent_noop(self):
        self.scenario(False)

    def test_public_assets_are_never_replaced(self):
        self.scenario(False, True)
