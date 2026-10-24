import importlib.util
import json
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

    def test_active_workflow_needs_only_dispatch(self):
        with patch.object(dispatch.subprocess, 'check_output', return_value=json.dumps({'state':'active'})), \
             patch.object(dispatch.subprocess, 'run') as run:
            dispatch.dispatch('etcher', 'macos')
        self.assertEqual(run.call_count, 1)
        self.assertIn('platform=macos', run.call_args.args[0])
