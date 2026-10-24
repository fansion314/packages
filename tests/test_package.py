import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package', ROOT/'scripts/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def test_tags_resolve_only_the_matching_manifest(self):
        for name in package.IDS:
            value = package.tag(package.manifest(name))
            self.assertEqual(package.parse_tag(value), name)
            for invalid in [value+'x', value.replace('-2', '-0'), 'arch-v'+value]:
                with self.assertRaises(ValueError):
                    package.parse_tag(invalid)

    def test_source_recipes_pin_upstream_and_packaging_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ['motrix', 'deepseek-harness']:
                package.recipes(name, directory, 'a'*64)
                info = package.manifest(name)
                recipe = (Path(directory)/info['package']/'PKGBUILD').read_text()
                binary = (Path(directory)/(info['package']+'-bin')/'PKGBUILD').read_text()
                self.assertIn('#commit='+info['upstream']['commit'], recipe)
                self.assertIn('tag='+package.tag(info), recipe)
                self.assertIn(f'package.py" apply {name}', recipe)
                sources = subprocess.check_output(['bash', '-c', binary+'\nprintf \"%s\\n\" \"${source[@]}\" \"${source_x86_64[@]}\"'], text=True)
                self.assertIn('/packages/releases/download/'+package.tag(info), sources)
                self.assertIn("sha256sums=('"+'a'*64+"')", binary)
                subprocess.run(['bash', '-n'], input=recipe, text=True, check=True)

    def test_bin_templates_require_a_real_checksum_at_finalization(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in package.IDS:
                with self.assertRaises(ValueError):
                    package.recipes(name, directory, 'SKIP')

    def test_wrong_upstream_and_dirty_checkout_fail_before_patching(self):
        for results in [['bad'], [package.manifest('motrix')['upstream']['commit'], ' M file']]:
            with patch.object(package, 'run', side_effect=results):
                with self.assertRaises(ValueError):
                    package.apply('motrix', '/tmp/unused-source')

    def test_overlay_refuses_to_replace_upstream_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            target = source/'build/arch/entry.cjs'
            target.parent.mkdir(parents=True)
            target.write_text('upstream content')
            with patch.object(package, 'run', side_effect=[package.manifest('motrix')['upstream']['commit'], '']), \
                 patch.object(package.subprocess, 'run'):
                with self.assertRaisesRegex(ValueError, 'replace upstream'):
                    package.apply('motrix', source)
            self.assertEqual(target.read_text(), 'upstream content')


if __name__ == '__main__':
    unittest.main()
