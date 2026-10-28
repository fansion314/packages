import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

scripts = Path(__file__).parents[1]/'scripts'
sys.path.insert(0, str(scripts))
spec = importlib.util.spec_from_file_location('validate', scripts/'validate.py')
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


class ValidationScopeTests(unittest.TestCase):
    def run_validation(self, *args, missing=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            projects = [
                {'id': 'dnr', 'packages': {'dnr': '', 'dnr-bin': '', 'dnc-bin': ''}},
                {'id': 'other', 'packages': {'other-bin': ''}},
            ]
            (root/'sources.json').write_text(json.dumps({'projects': projects}))
            for project in projects:
                for name in project['packages']:
                    if name in missing:
                        continue
                    path = root/'packages'/name
                    path.mkdir(parents=True)
                    (path/'PKGBUILD').touch()
            (root/'.cache').mkdir()
            (root/'.cache/changed.json').write_text(json.dumps(['dnr-bin', 'other-bin']))
            with patch.object(validate, 'ROOT', root), \
                    patch.object(sys, 'argv', ['validate.py', *args]), \
                    patch.object(sys, 'platform', 'linux'), \
                    patch.object(validate.os, 'geteuid', return_value=1000), \
                    patch.object(validate, 'validate_recipe') as metadata, \
                    patch.object(validate, 'package_binary') as binary, \
                    patch.object(validate, 'smoke') as smoke:
                validate.main()
                return ([call.args[0].name for call in metadata.call_args_list],
                        [call.args[0].name for call in binary.call_args_list],
                        set(smoke.call_args.args[0]))

    def test_project_limits_metadata_and_binary_packages(self):
        self.assertEqual(self.run_validation('--project', 'dnr', '--build-bins'),
                         (['dnc-bin', 'dnr', 'dnr-bin'], ['dnc-bin', 'dnr-bin'], {'dnc-bin', 'dnr-bin'}))

    def test_project_keeps_changed_only_binary_filter(self):
        self.assertEqual(self.run_validation('--project', 'dnr', '--build-bins', '--changed-only'),
                         (['dnc-bin', 'dnr', 'dnr-bin'], ['dnr-bin'], {'dnr-bin'}))

    def test_default_keeps_all_metadata_and_binaries(self):
        metadata, binaries, smoke = self.run_validation('--build-bins')
        self.assertEqual(metadata, ['dnc-bin', 'dnr', 'dnr-bin', 'other-bin'])
        self.assertEqual(binaries, ['dnc-bin', 'dnr-bin', 'other-bin'])
        self.assertEqual(smoke, set(binaries))

    def test_project_allows_missing_unrelated_recipes(self):
        metadata, _, _ = self.run_validation('--project', 'dnr', missing=('other-bin',))
        self.assertEqual(metadata, ['dnc-bin', 'dnr', 'dnr-bin'])

    def test_missing_selected_or_global_recipe_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Package inventory'):
            self.run_validation('--project', 'dnr', missing=('dnr-bin',))
        with self.assertRaisesRegex(ValueError, 'Package inventory'):
            self.run_validation(missing=('other-bin',))

    def test_unknown_project_is_rejected(self):
        with self.assertRaises(SystemExit) as error:
            self.run_validation('--project', 'unknown')
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
