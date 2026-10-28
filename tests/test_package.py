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
            for invalid in [value+'x', value.rsplit('-', 1)[0]+'-0', 'arch-v'+value]:
                with self.assertRaises(ValueError):
                    package.parse_tag(invalid)

    def test_source_recipes_pin_upstream_and_packaging_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ['motrix', 'deepseek-harness', 'mygo-cloudmusic']:
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

    def test_desktop_workspace_lookup_has_its_runtime_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            package.recipes('deepseek-harness', directory)
            for recipe in Path(directory).glob('*/PKGBUILD'):
                dependencies = subprocess.check_output(['bash', '-c', recipe.read_text()+'\nprintf "%s\\n" "${depends[@]}"'], text=True).splitlines()
                self.assertIn('xdg-user-dirs', dependencies)

    def test_bin_templates_require_a_real_checksum_at_finalization(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in package.IDS:
                with self.assertRaises(ValueError):
                    package.recipes(name, directory, 'SKIP')

    def test_native_app_version_comes_from_mygo_config_not_website(self):
        import json
        for version in ['0.1.20', '0.0.0']:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source/'package.json').write_text('{"private":true}')
                (source/'mygo.json').write_text(json.dumps({'version': version}))
                with patch.object(package, 'run', side_effect=[package.manifest('mygo-cloudmusic')['upstream']['commit'], '']), \
                     patch.object(package.subprocess, 'run'):
                    if version == '0.1.20':
                        package.apply('mygo-cloudmusic', source)
                        self.assertTrue((source/'aur/mygo-cloudmusic/PKGBUILD').is_file())
                    else:
                        with self.assertRaisesRegex(ValueError, 'application version'):
                            package.apply('mygo-cloudmusic', source)

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
