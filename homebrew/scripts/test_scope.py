import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ScopedSyncTests(unittest.TestCase):
    def invoke(self, project):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            log = directory / "calls"
            for executable in ("python3", "bash"):
                path = directory / executable
                path.write_text('#!/bin/sh\nprintf "%s\\n" "' + executable + ' $*" >> "$CALL_LOG"\n')
                path.chmod(0o755)
            env = dict(os.environ, PATH=f"{directory}:{os.environ['PATH']}", CALL_LOG=str(log))
            result = subprocess.run(['/bin/bash', str(ROOT / 'scripts/sync.sh'), 'homebrew', project],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    def test_scoped_projects_forward_to_generator_and_install(self):
        for project, expected in [('mihomomo', 'mihomomo'), ('clash-momo', 'clash-momo'),
                                  ('dnr', 'dnr'), ('pi', 'pi-dnr'), ('etcher', 'etcher-dnr'), ('', '')]:
            with self.subTest(project=project):
                result, calls = self.invoke(project)
                self.assertEqual(result.returncode, 0, result.stderr)
                suffix = f' {expected}' if expected else ''
                self.assertEqual(calls, [f'python3 homebrew/scripts/sync.py{suffix}',
                                         f'bash homebrew/scripts/test-install.sh{suffix}',
                                         'bash scripts/commit-generated.sh homebrew'])

    def test_invalid_project_stops_before_sync(self):
        result, calls = self.invoke('unexpected')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])
