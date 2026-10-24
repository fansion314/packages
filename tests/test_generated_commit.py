"""Exercise concurrent synchronization against a real temporary Git remote."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/commit-generated.sh'


class GeneratedCommitTests(unittest.TestCase):
    def git(self, cwd, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', *args], cwd=cwd, stderr=subprocess.DEVNULL, text=True).strip()

    def scenario(self, conflict):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root/'remote.git'
            self.git(root, 'init', '--bare', '--initial-branch=main', str(remote))
            first, other = root/'first', root/'other'
            self.git(root, 'clone', str(remote), str(first))
            (first/'aur/packages').mkdir(parents=True)
            (first/'aur/packages/recipe').write_text('old')
            (first/'aur/state').mkdir()
            (first/'aur/state/project.json').write_text('{}')
            (first/'README.md').write_text('old')
            self.git(first, 'add', '.')
            self.git(first, 'commit', '-m', 'base')
            self.git(first, 'push', 'origin', 'main')
            self.git(root, 'clone', str(remote), str(other))
            target = 'aur/packages/recipe' if conflict else 'README.md'
            (other/target).write_text('concurrent')
            self.git(other, 'add', target)
            self.git(other, 'commit', '-m', 'concurrent')
            self.git(other, 'push', 'origin', 'main')
            (first/'aur/packages/recipe').write_text('candidate')
            result = subprocess.run(['bash', str(SCRIPT), 'aur'], cwd=first,
                                    env={**os.environ, 'GH_TOKEN': 'test-placeholder'}, capture_output=True, text=True)
            if conflict:
                self.assertEqual(result.returncode, 75, result.stderr)
                self.assertEqual(self.git(other, 'show', 'HEAD:aur/packages/recipe'), 'concurrent')
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.git(first, 'show', 'HEAD:README.md'), 'concurrent')
                self.assertEqual(self.git(first, 'show', 'HEAD:aur/packages/recipe'), 'candidate')
                self.assertEqual(self.git(first, 'rev-parse', 'HEAD'), self.git(remote, 'rev-parse', 'main'))
                again = subprocess.run(['bash', str(SCRIPT), 'aur'], cwd=first, capture_output=True)
                self.assertEqual(again.returncode, 0)

    def test_unrelated_commit_survives_and_second_sync_is_noop(self):
        self.scenario(False)

    def test_conflicting_generated_output_requires_regeneration(self):
        self.scenario(True)
