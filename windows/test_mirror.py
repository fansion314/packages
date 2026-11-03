"""Exercise signed identity, immutable bytes, isolated publication and retry boundaries."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('windows_mirror', Path(__file__).with_name('mirror.py'))
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class FakeClient:
    def __init__(self, blobs):
        self.blobs = blobs
        self.items = {}
        self.uploaded = 0
        self.reused = 0

    def upload(self, item, source):
        url = mirror.location(mirror.REPOSITORY, item['tag'], item['filename'])
        data = Path(source).read_bytes()
        if url in self.blobs:
            if self.blobs[url] != data:
                raise ValueError('Refusing to overwrite mirrored bytes')
            self.reused += 1
            return False
        self.blobs[url] = data
        self.items[url] = item
        self.uploaded += 1
        return True


class WindowsMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = json.loads(subprocess.check_output(['node', '-e', '''
const c = require('node:crypto'), k = c.generateKeyPairSync('ed25519');
process.stdout.write(JSON.stringify({public: k.publicKey.export({type:'spki',format:'der'}).toString('base64'), private: k.privateKey.export({type:'pkcs8',format:'der'}).toString('base64')}));
'''], text=True))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root/'remote.git'
        self.candidate = self.root/'candidate'
        self.blobs = {}
        self.client = FakeClient(self.blobs)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1').start()
        self.git(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        main = self.root/'initial'
        self.git(self.root, 'clone', str(self.remote), str(main))
        (main/'homebrew.txt').write_text('untouched Homebrew main')
        self.git(main, 'add', '.')
        self.git(main, 'commit', '-m', 'existing Homebrew distribution')
        self.git(main, 'push', 'origin', 'main')
        self.main_sha = self.git(self.remote, 'rev-parse', 'main')
        self.info = {
            'schema': 1, 'product': 'clash-momo', 'platform': 'win32', 'arch': 'x64',
            'tag': 'clash-momo-v2.0.4-5', 'version': '2.0.4', 'revision': 5,
            'publishedAt': '2026-11-03T00:00:00Z', 'changelog': 'New client',
            'sourceCommit': 'a'*40,
            'core': {'tag': 'mihomomo-v1.19.33-4', 'sha256': 'b'*64, 'sourceCommit': 'c'*40},
            'assets': {},
        }
        for kind, suffix in [('installer', '-setup.exe'), ('portable', '-portable.zip')]:
            data = ('original '+kind).encode()
            name = 'clash-momo-2.0.4-5-windows-x64'+suffix
            self.info['assets'][kind] = {'name': name, 'size': len(data), 'sha256': sha(data)}
        self.envelope = self.sign(self.info)
        self.release = self.release_files()
        self.real_validate = mirror.validated_manifest
        patch.object(mirror, 'validated_manifest', side_effect=lambda raw: self.real_validate(raw, {'test': self.key['public']})).start()
        patch.object(mirror, 'source_release', side_effect=lambda _tag: self.release).start()
        patch.object(mirror, 'download', side_effect=self.download).start()

    def git(self, directory, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                                        '-C', str(directory), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def sign(self, info):
        payload = base64.b64encode(json.dumps(info).encode()).decode()
        signature = subprocess.check_output(['node', '-e', '''
const fs = require('node:fs'), c = require('node:crypto'), v = JSON.parse(fs.readFileSync(0,'utf8'));
const key = c.createPrivateKey({key:Buffer.from(v.key,'base64'),format:'der',type:'pkcs8'});
process.stdout.write(c.sign(null,Buffer.from(v.payload,'base64'),key).toString('base64'));
'''], input=json.dumps({'key': self.key['private'], 'payload': payload}), text=True)
        return json.dumps({'schema': 1, 'keyId': 'test', 'payload': payload, 'signature': signature}).encode()

    def release_files(self):
        files = {mirror.MANIFEST: self.envelope}
        for kind, item in self.info['assets'].items():
            files[item['name']] = ('original '+kind).encode()
            files[item['name']+'.sha256'] = (item['sha256']+'  '+item['name']+'\n').encode()
        name = f'clash-momo-{self.info["version"]}-{self.info["revision"]}-windows-x64-manifest.json'
        files[name] = json.dumps({'tag': self.info['tag'], 'source_commit': self.info['sourceCommit'],
                                 'architecture': 'x64', 'core': {
                                     'tag': self.info['core']['tag'], 'core_sha256': self.info['core']['sha256'],
                                     'source_commit': self.info['core']['sourceCommit']}}).encode()
        files[name+'.sha256'] = (sha(files[name])+'  '+name+'\n').encode()
        release = {'tag_name': self.info['tag'], 'draft': False, 'prerelease': False, 'assets': []}
        for name, data in files.items():
            url = f'https://github.com/{mirror.SOURCE}/releases/download/{self.info["tag"]}/{name}'
            self.blobs[url] = data
            release['assets'].append({'name': name, 'size': len(data), 'digest': 'sha256:'+sha(data),
                                      'browser_download_url': url})
        return release

    def download(self, url, target, expected=None, size=None, limit=2*1024**3):
        data = self.blobs[url]
        if len(data) > limit or (expected and sha(data) != expected) or (size and len(data) != size):
            raise ValueError('Windows asset download digest or size mismatch')
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_bytes(data)

    def prepare(self):
        return mirror.prepare(self.candidate, remote=str(self.remote), client=self.client)

    def publish(self):
        def push(directory, dry_run=False):
            self.git(directory, 'push', *(['--dry-run'] if dry_run else []), 'origin', 'HEAD:refs/heads/'+mirror.BRANCH)
        with patch.object(mirror, 'REMOTE', str(self.remote)), patch.object(mirror, 'authenticated_push', side_effect=push):
            mirror.publish(self.candidate)

    def test_full_publication_keeps_main_and_copies_signed_bytes(self):
        result = self.prepare()
        self.assertTrue(result['changed'])
        self.assertEqual(self.client.uploaded, 7)
        self.assertTrue(all(item['tag'] == 'windows-'+self.info['tag'] for item in self.client.items.values()))
        self.publish()
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main'), self.main_sha)
        actual = self.git(self.remote, 'show', mirror.BRANCH+':'+mirror.FEED)
        self.assertEqual(actual, self.envelope.decode())
        self.assertEqual(self.git(self.remote, 'ls-tree', '-r', '--name-only', mirror.BRANCH).splitlines(),
                         [mirror.FEED, mirror.STATE])

    def test_tampered_signature_never_uploads_or_publishes(self):
        item = next(a for a in self.release['assets'] if a['name'] == mirror.MANIFEST)
        raw = json.loads(self.envelope)
        raw['payload'] = base64.b64encode(b'{}').decode()
        data = json.dumps(raw).encode()
        self.blobs[item['browser_download_url']] = data
        item.update(size=len(data), digest='sha256:'+sha(data))
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.prepare()
        self.assertEqual(self.client.uploaded, 0)
        self.assertNotEqual(self.git(self.remote, 'show-ref'), '')

    def test_unknown_key_rejected(self):
        raw = json.loads(self.envelope)
        raw['keyId'] = 'untrusted'
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.real_validate(json.dumps(raw).encode(), {'test': self.key['public']})

    def test_duplicate_fields_and_wrong_schema_types_rejected(self):
        raw = self.envelope.decode().replace('"schema": 1', '"schema": 1, "schema": 1', 1)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.real_validate(raw.encode(), {'test': self.key['public']})
        for change in [lambda i: i.update(schema=True), lambda i: i.update(sourceCommit=[]),
                       lambda i: i.update(publishedAt='no timestamp'),
                       lambda i: i['core'].update(sha256={})]:
            info = copy.deepcopy(self.info)
            change(info)
            with self.subTest(info=info), self.assertRaises(ValueError):
                self.real_validate(self.sign(info), {'test': self.key['public']})

    def test_signed_wrong_product_paths_core_and_sizes_rejected(self):
        for mutate in [lambda i: i.update(platform='darwin'),
                       lambda i: i['assets']['installer'].update(name='../outside.exe'),
                       lambda i: i['assets']['installer'].update(size=-1),
                       lambda i: i['core'].update(tag='another-project-v1'),
                       lambda i: i.update(revision=6)]:
            info = copy.deepcopy(self.info)
            mutate(info)
            with self.subTest(info=info), self.assertRaises(ValueError):
                self.real_validate(self.sign(info), {'test': self.key['public']})

    def test_no_change_reuses_feed_without_installer_downloads(self):
        self.prepare()
        self.publish()
        tip = self.git(self.remote, 'rev-parse', mirror.BRANCH)
        uploads = self.client.uploaded
        self.candidate = self.root/'next'
        with patch.object(mirror, 'source_file', wraps=mirror.source_file) as files:
            self.assertFalse(self.prepare()['changed'])
        self.assertEqual(files.call_count, 1)
        self.assertEqual(self.client.uploaded, uploads)
        self.assertEqual(self.git(self.remote, 'rev-parse', mirror.BRANCH), tip)

    def test_failed_mirror_download_retains_old_public_feed_and_retry_reuses(self):
        original = self.download
        with patch.object(mirror, 'download', side_effect=lambda url, *a, **k: (_ for _ in ()).throw(
                ValueError('anonymous failed')) if url.startswith('https://cnb.cool/') else original(url, *a, **k)):
            with self.assertRaisesRegex(ValueError, 'anonymous failed'):
                self.prepare()
        self.assertFalse((self.candidate/'.git'/mirror.RECEIPT).exists())
        uploaded = self.client.uploaded
        self.candidate = self.root/'retry'
        self.prepare()
        self.assertEqual(self.client.uploaded, 7)
        self.assertEqual(self.client.reused, uploaded)
        self.publish()

    def test_packaged_core_mismatch_stops_before_any_upload(self):
        asset = next(a for a in self.release['assets'] if a['name'].endswith('-manifest.json'))
        value = json.loads(self.blobs[asset['browser_download_url']])
        value['core']['core_sha256'] = 'f'*64
        data = json.dumps(value).encode()
        self.blobs[asset['browser_download_url']] = data
        asset.update(size=len(data), digest='sha256:'+sha(data))
        checksum = next(a for a in self.release['assets'] if a['name'] == asset['name']+'.sha256')
        content = (sha(data)+'  '+asset['name']+'\n').encode()
        self.blobs[checksum['browser_download_url']] = content
        checksum.update(size=len(content), digest='sha256:'+sha(content))
        with self.assertRaisesRegex(ValueError, 'identity differs'):
            self.prepare()
        self.assertEqual(self.client.uploaded, 0)

    def test_missing_attachment_and_unsafe_url_rejected(self):
        for kind in ['missing', 'url']:
            assets = copy.deepcopy(self.release['assets'])
            if kind == 'missing':
                self.release['assets'] = [a for a in assets if not a['name'].endswith('-setup.exe')]
            else:
                next(a for a in self.release['assets'] if a['name'].endswith('-setup.exe'))['browser_download_url'] = 'https://other.invalid/setup.exe'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.prepare()
            self.assertEqual(self.client.uploaded, 0)
            self.release['assets'] = assets
            self.candidate = self.root/kind

    def test_candidate_tampering_and_unrelated_staging_rejected(self):
        self.prepare()
        (self.candidate/ mirror.FEED).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'feed changed'):
            self.publish()

    def test_unrelated_staged_files_never_enter_feed_branch(self):
        self.prepare()
        (self.candidate/'unexpected').write_text('keep out')
        self.git(self.candidate, 'add', 'unexpected')
        with self.assertRaisesRegex(ValueError, 'Unrelated'):
            self.publish()

    def test_same_release_manifest_replacement_and_downgrade_rejected(self):
        self.prepare()
        self.publish()
        tip = self.git(self.remote, 'rev-parse', mirror.BRANCH)
        self.candidate = self.root/'replacement'
        self.info['changelog'] = 'replacement signed metadata'
        self.envelope = self.sign(self.info)
        self.release = self.release_files()
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.prepare()
        self.candidate = self.root/'downgrade'
        self.info.update(tag='clash-momo-v2.0.4-4', revision=4)
        for item in self.info['assets'].values():
            item['name'] = item['name'].replace('2.0.4-5', '2.0.4-4')
        self.envelope = self.sign(self.info)
        self.release = self.release_files()
        with self.assertRaisesRegex(ValueError, 'downgrade'):
            self.prepare()
        self.assertEqual(self.git(self.remote, 'rev-parse', mirror.BRANCH), tip)

    def test_concurrent_remote_feed_never_overwritten(self):
        self.prepare()
        self.publish()
        self.candidate = self.root/'next'
        mirror.candidate_repository(self.candidate, str(self.remote))
        # Retain a stale, otherwise valid candidate while another publisher advances.
        receipt = json.loads((self.root/'candidate/.git'/mirror.RECEIPT).read_text())
        receipt['base'] = self.git(self.candidate, 'rev-parse', 'HEAD')
        receipt['download_files'] = {}
        mirror.write_json(self.candidate/'.git'/mirror.RECEIPT, receipt)
        (self.candidate/mirror.STATE).write_text((self.candidate/mirror.STATE).read_text()+'\n')
        receipt['files'][mirror.STATE] = mirror.digest(self.candidate/mirror.STATE)
        mirror.write_json(self.candidate/'.git'/mirror.RECEIPT, receipt)
        other = self.root/'other'
        self.git(self.root, 'clone', '--branch', mirror.BRANCH, str(self.remote), str(other))
        (other/'user-file').write_text('preserve user change')
        self.git(other, 'add', '.')
        self.git(other, 'commit', '-m', 'concurrent change')
        self.git(other, 'push', 'origin', mirror.BRANCH)
        tip = self.git(self.remote, 'rev-parse', mirror.BRANCH)
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertEqual(self.git(self.remote, 'rev-parse', mirror.BRANCH), tip)

    def test_code_permission_preflight_precedes_all_downloads(self):
        with patch.object(mirror, 'authenticated_push', side_effect=RuntimeError('needs repo-code:rw')), \
                patch.object(mirror, 'source_file') as source:
            with self.assertRaisesRegex(RuntimeError, 'repo-code:rw'):
                mirror.prepare(self.candidate, remote=str(self.remote))
            source.assert_not_called()

    def test_write_preflight_never_creates_a_remote_ref(self):
        mirror.candidate_repository(self.candidate, str(self.remote))
        before = self.git(self.remote, 'show-ref')
        with patch.dict(os.environ, CNB_MIRROR_TOKEN='test-only'):
            mirror.authenticated_push(self.candidate, dry_run=True)
        self.assertEqual(self.git(self.remote, 'show-ref'), before)

    def test_git_credential_fill_executes_the_real_askpass_shell(self):
        # A fake token and local credential fill prove Git executes the helper; no network is needed.
        with tempfile.TemporaryDirectory(prefix='mirror auth space ') as directory, \
                patch.dict(os.environ, CNB_MIRROR_TOKEN='test-only-credential'):
            env = mirror.askpass_environment(directory)
            result = subprocess.run(['git', '-c', 'credential.helper=', 'credential', 'fill'],
                                    input='protocol=https\nhost=example.invalid\n\n', text=True,
                                    env=env, capture_output=True, timeout=15)
            diagnostics = result.stderr.replace('test-only-credential', '[test credential]')
            self.assertEqual(result.returncode, 0, 'Git credential helper failed: '+diagnostics)
            credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            self.assertEqual(credentials.get('username'), 'cnb')
            self.assertEqual(credentials.get('password'), 'test-only-credential')

    def test_public_feed_recheck_is_small_when_no_release_changed(self):
        self.prepare()
        self.publish()
        feed_url = mirror.REMOTE+'/-/git/raw/'+mirror.BRANCH+'/'+mirror.FEED
        self.blobs[feed_url] = self.envelope
        with patch.object(mirror, 'download', side_effect=self.download) as download:
            mirror.verify_public(self.candidate, metadata_only=True)
        self.assertEqual(download.call_count, 1)
        with patch.object(mirror, 'download', side_effect=self.download) as download:
            mirror.verify_public(self.candidate)
        self.assertEqual(download.call_count, 8)
        self.blobs[feed_url] = b'outdated feed'
        with self.assertRaisesRegex(ValueError, 'digest'):
            mirror.verify_public(self.candidate, metadata_only=True)

    def test_permission_diagnostics_do_not_leak_remote_response(self):
        error = subprocess.CompletedProcess([], 128, '', '403 forbidden TOKEN_REMOTE_DIAGNOSTIC')
        with patch.dict(os.environ, CNB_MIRROR_TOKEN='test-only'), \
                patch.object(mirror.subprocess, 'run', return_value=error):
            with self.assertRaisesRegex(RuntimeError, 'repo-code:rw') as result:
                mirror.authenticated_push(self.root, dry_run=True)
        self.assertNotIn('TOKEN_REMOTE_DIAGNOSTIC', str(result.exception))

    def test_version_comparison_includes_numeric_revision(self):
        self.assertGreater(mirror.version_key('clash-momo-v2.0.4-10'), mirror.version_key('clash-momo-v2.0.4-9'))
        self.assertGreater(mirror.version_key('clash-momo-v2.0.5-1'), mirror.version_key('clash-momo-v2.0.4-99'))
        with self.assertRaises(ValueError):
            mirror.version_key('mihomomo-v1.19.33-4')

    def test_version_grammar_matches_client_safe_integer_rules(self):
        maximum = mirror.MAX_SAFE_INTEGER
        self.assertEqual(mirror.version_key(f'clash-momo-v0.0.{maximum}-{maximum}'), (0, 0, maximum, maximum))
        for value in ['clash-momo-v02.0.4-5', 'clash-momo-v2.00.4-5', 'clash-momo-v2.0.04-5',
                      'clash-momo-v2.0.4-05', 'clash-momo-v2.0.4-0', 'clash-momo-v2.0.4-1\n',
                      'clash-momo-v٢.0.4-5', f'clash-momo-v{maximum+1}.0.4-5',
                      f'clash-momo-v2.0.4-{maximum+1}']:
            with self.subTest(tag=value), self.assertRaises(ValueError):
                mirror.version_key(value)
            self.assertFalse(mirror.valid_tag(value))
        for value in ['mihomomo-v1.19.33-0', 'mihomomo-v01.19.33-4', f'mihomomo-v1.19.33-{maximum+1}']:
            info = copy.deepcopy(self.info)
            info['core']['tag'] = value
            with self.subTest(core=value), self.assertRaises(ValueError):
                self.real_validate(self.sign(info), {'test': self.key['public']})


class WindowsRoutingTests(unittest.TestCase):
    def test_downstream_routes_windows_only_for_clash_momo(self):
        workflow = (mirror.ROOT/'.github/workflows/downstream.yml').read_text()
        block = workflow.split('        run: |\n', 1)[1].split('\n  aur:', 1)[0]
        script = '\n'.join(line[10:] for line in block.splitlines())
        for project, platform, expected in [('clash-momo', 'windows', {'aur': 'false', 'homebrew': 'false', 'windows': 'true'}),
                                            ('clash-momo', 'all', {'aur': 'true', 'homebrew': 'true', 'windows': 'true'}),
                                            ('mihomomo', 'all', {'aur': 'true', 'homebrew': 'true', 'windows': 'false'}),
                                            ('clash-momo', 'macos', {'aur': 'false', 'homebrew': 'true', 'windows': 'false'}),
                                            ('clash-momo', 'arch', {'aur': 'true', 'homebrew': 'false', 'windows': 'false'})]:
            with self.subTest(project=project, platform=platform), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)/'output'
                subprocess.run([mirror.git_shell(), '-c', script], env={**os.environ, 'PROJECT': project, 'PLATFORM': platform,
                               'GITHUB_OUTPUT': str(output)}, check=True)
                self.assertEqual(dict(line.split('=') for line in output.read_text().splitlines()), expected)
        self.assertIn("inputs.platform == 'arch'", workflow)
        self.assertIn("github.event_name != 'schedule'", workflow)


if __name__ == '__main__':
    unittest.main()
