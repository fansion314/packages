import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('dispatch', Path(__file__).resolve().parents[1]/'dispatch.py')
dispatch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dispatch)


class DispatchTests(unittest.TestCase):
    def test_inactivity_is_restored_before_notifying(self):
        with patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'disabled_inactivity'})), \
             patch.object(dispatch.subprocess, 'run') as run:
            dispatch.dispatch('pi', 'arch')
        self.assertEqual([call.args[0][2] for call in run.call_args_list], ['enable', 'run'])

    def test_manual_disable_is_respected(self):
        with patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'disabled_manually'})), \
             patch.object(dispatch.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'intentionally disabled'):
                dispatch.dispatch('pi', 'arch')
        run.assert_not_called()

    def test_tag_caller_dispatches_main(self):
        with patch.dict(os.environ, {'GITHUB_REF': 'refs/tags/motrix-v2.0.1-1',
                                     'GITHUB_REF_TYPE': 'tag'}), \
             patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'active'})), \
             patch.object(dispatch.subprocess, 'run') as run:
            dispatch.main(['motrix', 'arch'])
        run.assert_called_once_with(
            ['gh', 'workflow', 'run', 'downstream.yml', '-R', 'fansion314/packages',
             '--ref', 'main', '-f', 'project=motrix', '-f', 'platform=arch'], check=True)

    def test_internal_and_support_packages_are_accepted(self):
        for project in ['motrix', 'deepseek-harness', 'bitwarden', 'obsidian',
                        'python-pptx', 'fansionia-keyring', 'clash-momo', 'mihomomo', 'mygo-cloudmusic']:
            with self.subTest(project=project), \
                 patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'active'})), \
                 patch.object(dispatch.subprocess, 'run') as run:
                dispatch.main([project, 'arch'])
                self.assertIn('project='+project, run.call_args.args[0])

    def test_downstream_workflow_accepts_momo_project_ids(self):
        import subprocess
        workflow = (Path(__file__).resolve().parents[2]/'.github/workflows/downstream.yml').read_text()
        project_case = next(line.strip() for line in workflow.splitlines()
                            if line.strip().startswith('case "$PROJECT" in'))
        for project in ['clash-momo', 'mihomomo', 'mygo-cloudmusic']:
            with self.subTest(project=project):
                result = subprocess.run(['bash', '-c', project_case], env={'PROJECT': project})
                self.assertEqual(result.returncode, 0)
        result = subprocess.run(['bash', '-c', project_case], env={'PROJECT': 'unregistered'})
        self.assertEqual(result.returncode, 2)

    def test_internal_package_does_not_restore_manual_disable(self):
        with patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'disabled_manually'})), \
             patch.object(dispatch.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'intentionally disabled'):
                dispatch.main(['motrix', 'arch'])
        run.assert_not_called()

    def test_active_workflow_needs_only_dispatch(self):
        with patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'active'})), \
             patch.object(dispatch.subprocess, 'run') as run:
            dispatch.dispatch('etcher', 'macos')
        self.assertEqual(run.call_count, 1)
        self.assertIn('platform=macos', run.call_args.args[0])
