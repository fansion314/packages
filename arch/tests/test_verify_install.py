import importlib.util
from pathlib import Path
import sys
import unittest

ARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARCH))
spec = importlib.util.spec_from_file_location('verify_install', ARCH/'verify-install.py')
verify_install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_install)


class InstallSelectionTests(unittest.TestCase):
    def setUp(self):
        self.packages = {name: ['old'] for name in ['fansionia-keyring', 'fixture', 'peer']}
        self.packages.update({name: ['old'] for name in verify_install.DROIDLOOM})
        self.previous = {'snapshot': 'old', 'policy': 'one', 'packages': self.packages}

    def test_unchanged_keeps_only_the_keyring_probe(self):
        self.assertEqual(verify_install.selected_packages(self.previous, self.previous), ['fansionia-keyring'])

    def test_change_selects_package_and_keyring(self):
        candidate = dict(self.previous, packages=dict(self.packages, fixture=['new']))
        self.assertEqual(verify_install.selected_packages(candidate, self.previous), ['fansionia-keyring', 'fixture'])

    def test_a_changed_droidloom_route_selects_the_entire_group(self):
        candidate = dict(self.previous, packages={**self.packages, 'droidloom-base': ['old', 'new route']})
        self.assertEqual(verify_install.selected_packages(candidate, self.previous),
                         sorted(verify_install.DROIDLOOM | {'fansionia-keyring'}))

    def test_full_acceptance_when_policy_keyring_or_baseline_changes(self):
        candidate = dict(self.previous, policy='two')
        self.assertEqual(verify_install.selected_packages(candidate, self.previous), sorted(self.packages))
        candidate = dict(self.previous, packages={**self.packages, 'fansionia-keyring': ['new']})
        self.assertEqual(verify_install.selected_packages(candidate, self.previous), sorted(self.packages))
        self.assertEqual(verify_install.selected_packages(self.previous, None), sorted(self.packages))
        self.assertEqual(verify_install.selected_packages(self.previous, self.previous, True), sorted(self.packages))
