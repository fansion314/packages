import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'ci_packages', Path(__file__).resolve().parents[1]/'scripts/ci-packages.py')
ci = importlib.util.module_from_spec(spec)
# The CLI imports the sibling package module.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
spec.loader.exec_module(ci)


class BuildScopeTests(unittest.TestCase):
    def test_application_patch_does_not_rebuild_unrelated_apps(self):
        self.assertEqual(ci.affected([
            'packages/mygo-cloudmusic/patches/0001.patch', 'README.md',
            '.github/workflows/ci.yml', 'scripts/ci-packages.py',
        ]), ['mygo-cloudmusic'])

    def test_multiple_apps_are_selected_once(self):
        self.assertEqual(ci.affected([
            'packages/motrix/manifest.json', 'packages/mygo-cloudmusic/manifest.json',
            'packages/motrix/recipes/PKGBUILD',
        ]), ['motrix', 'mygo-cloudmusic'])

    def test_shared_build_changes_exercise_every_app(self):
        for path in ci.SHARED_BUILD_INPUTS:
            with self.subTest(path=path):
                self.assertEqual(ci.affected([path, 'packages/mygo-cloudmusic/manifest.json']), list(ci.IDS))

    def test_distribution_and_static_tests_need_no_application_build(self):
        self.assertEqual(ci.affected(['arch/sources.json', 'aur/scripts/sync.py', 'tests/test_package.py']), [])
