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
            for name in ['motrix', 'deepseek-harness', 'mygo-music', 'hghub']:
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

    def test_tauri_runtime_records_actual_native_toolchain_without_electron(self):
        versions = {
            ('pkg-config', '--modversion', 'webkit2gtk-4.1'): '2.54.1',
            ('rustc', '--version'): 'rustc fixture',
            ('cargo', '--version'): 'cargo fixture',
        }
        with patch.object(package, 'run', side_effect=lambda *args: versions[args]) as run:
            metadata = package.runtime_metadata({'runtime': 'tauri-webkitgtk'})
        self.assertIsNone(metadata['system_electron'])
        self.assertIsNone(metadata['native_go'])
        self.assertEqual(metadata['webkitgtk'], '2.54.1')
        self.assertEqual(metadata['rust'], 'rustc fixture')
        self.assertEqual(metadata['cargo'], 'cargo fixture')
        self.assertEqual(run.call_count, 3)
        note = package.runtime_note({'runtime': 'tauri-webkitgtk'})
        self.assertIn('Community Linux build', note)
        self.assertIn('WebKitGTK 4.1', note)
        self.assertIn('PolyForm Noncommercial', note)

    def test_existing_runtime_metadata_remains_compatible(self):
        with patch.object(package, 'run', return_value='electron fixture') as run:
            self.assertEqual(package.runtime_metadata({}), {
                'system_electron': 'electron fixture', 'native_go': None})
            run.assert_called_once_with('pacman', '-Q', 'electron')
        with patch.object(package, 'run', return_value='go fixture') as run:
            self.assertEqual(package.runtime_metadata({'runtime': 'native-go'}), {
                'system_electron': None, 'native_go': 'go fixture'})
            run.assert_called_once_with('go', 'version')
        with self.assertRaisesRegex(ValueError, 'Unknown application runtime'):
            package.runtime_metadata({'runtime': 'invalid'})

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

    def test_native_app_version_comes_from_evaluated_build_config_not_website(self):
        info = package.manifest('mygo-music')
        real_run = subprocess.run

        def skip_patch_commands(args, **kwargs):
            if args[:2] == ['git', 'apply']:
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)

        for version in [info['version'], '0.0.0']:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source/'package.json').write_text('{"private":true,"version":"99.0.0"}')
                (source/'mygo.config.ts').write_text(
                    'export default ({ command }: { command: string }) => ({' +
                    f'version: command === "build" ? "{version}" : "0.0.1"' + '});\n')
                with patch.object(package, 'run', side_effect=[info['upstream']['commit'], '']), \
                     patch.object(package.subprocess, 'run', side_effect=skip_patch_commands):
                    if version == info['version']:
                        package.apply('mygo-music', source)
                        self.assertTrue((source/'aur/mygo-music/PKGBUILD').is_file())
                    else:
                        with self.assertRaisesRegex(ValueError, 'application version'):
                            package.apply('mygo-music', source)

    def test_application_version_preserves_json_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for filename, info in [('package.json', {}), ('mygo.json', {'version_file': 'mygo.json'})]:
                with self.subTest(filename=filename):
                    (source/filename).write_text('{"version":"1.2.3"}')
                    self.assertEqual(package.application_version(source, info), '1.2.3')

    def test_tauri_and_rust_versions_must_match_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source/'src-tauri').mkdir()
            (source/'package.json').write_text('{"version":"1.2.0"}')
            for tauri, cargo in [('1.2.0', '1.2.0'), ('1.1.0', '1.2.0'), ('1.2.0', '1.1.0')]:
                with self.subTest(tauri=tauri, cargo=cargo):
                    (source/'src-tauri/tauri.conf.json').write_text('{"version":"'+tauri+'"}')
                    (source/'src-tauri/Cargo.toml').write_text('[package]\nversion = "'+cargo+'"\n')
                    if tauri == cargo == '1.2.0':
                        self.assertEqual(package.application_version(source, {'runtime': 'tauri-webkitgtk'}), '1.2.0')
                    else:
                        with self.assertRaisesRegex(ValueError, 'application versions'):
                            package.application_version(source, {'runtime': 'tauri-webkitgtk'})

    def test_typescript_config_can_export_an_object(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source/'mygo.config.ts').write_text(
                'const version: string = "1.2.3"; export default { version };\n')
            self.assertEqual(package.application_version(source, {'version_file': 'mygo.config.ts'}), '1.2.3')

    def test_typescript_config_requires_a_string_version(self):
        for value in ['{}', '{ version: 123 }', '{ version: null }']:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source/'mygo.config.ts').write_text('export default ' + value + ';\n')
                with self.assertRaisesRegex(ValueError, 'application version'):
                    package.application_version(source, {'version_file': 'mygo.config.ts'})

    def test_typescript_evaluation_failure_cannot_pass_version_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source/'mygo.config.ts').write_text(
                'export default () => { throw new Error("invalid build configuration"); };\n')
            with self.assertRaises(subprocess.CalledProcessError):
                package.application_version(source, {'version_file': 'mygo.config.ts'})

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
