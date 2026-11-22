#!/usr/bin/env python3
"""Import only checksum-verified stable release assets from the fixed project allowlist."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
TAP_ROOT = ROOT.parent
PROJECTS = {
    "clash-momo": ("fansion314/momo", r"clash-momo-v(\d+\.\d+\.\d+)-(\d+)", r"clash-momo-{version}-{release}-macos-arm64-r([1-9]\d*)\.tar\.gz"),
    "mihomomo": ("fansion314/momo", r"mihomomo-v(\d+\.\d+\.\d+)-(\d+)", r"mihomomo-{version}-{release}-macos-arm64-r([1-9]\d*)\.tar\.gz"),
    "dnr": ("fansion314/dnr", r"v(\d+\.\d+\.\d+)", r"dnr-{version}-macos-arm64(?:-r([1-9]\d*))?\.tar\.gz"),
    "pi-dnr": ("fansion314/pi", r"pi-dnr-v(\d+\.\d+\.\d+)-(\d+)", r"pi-dnr-{version}-{release}-macos-arm64-r([1-9]\d*)\.tar\.gz"),
    "etcher-dnr": ("fansion314/etcher", r"v(\d+\.\d+\.\d+)-dnr\.(\d+)", r"etcher-dnr-{version}-{release}-macos-arm64-r([1-9]\d*)\.tar\.gz"),
}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def candidates(project, releases):
    repository, tag_pattern, asset_pattern = PROJECTS[project]
    found = []
    strict = project in {'clash-momo', 'mihomomo'}
    matching = []
    incomplete = []
    for release in releases:
        if release['draft'] or release['prerelease']:
            continue
        match = re.fullmatch(tag_pattern, release['tag_name'])
        if not match:
            continue
        version = match[1]
        packaging = int(match[2]) if match.lastindex > 1 else 0
        names = {asset['name']: asset for asset in release['assets']}
        matching.append(([*map(int, version.split('.')), packaging], release['tag_name']))
        matched_assets = []
        if strict:
            for name in names:
                if name.endswith('.sha256') and re.fullmatch(asset_pattern.format(version=re.escape(version), release=packaging), name[:-7]) and name[:-7] not in names:
                    incomplete.append(([*map(int, version.split('.')), packaging], name))
        for name, asset in names.items():
            m = re.fullmatch(asset_pattern.format(version=re.escape(version), release=packaging), name)
            if not m:
                continue
            revision = int(m[1] or 0)
            matched_assets.append((revision, name, name + '.sha256' in names))
            if name + '.sha256' not in names:
                continue
            url = f"https://github.com/{repository}/releases/download/{release['tag_name']}/{name}"
            if asset['browser_download_url'] != url:
                raise ValueError('Unexpected release asset URL')
            key = [*map(int, version.split('.')), packaging, revision]
            found.append((key, {'repository': repository, 'tag': release['tag_name'], 'version': version,
                                'release': packaging, 'revision': revision, 'asset': name, 'url': url,
                                'github_digest': asset.get('digest')}))
        if strict and matched_assets:
            revision, name, complete = max(matched_assets)
            if not complete:
                incomplete.append(([*map(int, version.split('.')), packaging], name))
    if strict and matching:
        latest = max(matching)[0]
        if any(key == latest for key, _ in incomplete):
            raise ValueError('Latest macOS asset is missing its checksum')
        if not any(key[:4] == latest for key, _ in found):
            raise ValueError(f'Latest {project} release has no complete macOS asset')
    return sorted(found, key=lambda item: item[0])


def verified_digest(info):
    with tempfile.TemporaryDirectory(prefix='dnr-tap-') as directory:
        args = ['gh', 'release', 'download', info['tag'], '--repo', info['repository'],
                '--pattern', info['asset'] + '.sha256', '--dir', directory]
        github_digest = info.get('github_digest')
        if github_digest is not None and not re.fullmatch(r'sha256:[a-f0-9]{64}', github_digest):
            raise ValueError('Invalid GitHub release asset digest')
        if not github_digest:
            args.extend(['--pattern', info['asset']])
        subprocess.run(args, check=True)
        fields = (Path(directory)/(info['asset']+'.sha256')).read_text().split()
        if len(fields) != 2 or fields[1] != info['asset'] or not re.fullmatch('[a-f0-9]{64}', fields[0]):
            raise ValueError('Invalid checksum file')
        if github_digest:
            actual = github_digest.removeprefix('sha256:')
        else:
            with (Path(directory)/info['asset']).open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != fields[0]:
            raise ValueError('Release checksum mismatch')
        return actual


def cnb_tag(project, info):
    """Keep Homebrew attachments separate from pacman's managed release tags."""
    if project not in PROJECTS:
        raise ValueError('Unsupported Homebrew project')
    version = info['version']
    release = info['release']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or type(release) is not int or release < 0:
        raise ValueError('Invalid mirrored release identity')
    return f'homebrew-{project}-v{version}' + (f'-{release}' if release else '')


def cnb_url(project, info):
    tag = cnb_tag(project, info)
    asset = info['asset']
    if not asset or Path(asset).name != asset or asset in {'.', '..'}:
        raise ValueError('Invalid mirrored release asset')
    return f'https://cnb.cool/fansionia/packages/-/releases/download/{quote(tag, safe="")}/{quote(asset, safe="")}'


def render(project, info, source='github'):
    if project not in PROJECTS:
        raise ValueError('Unsupported Homebrew project')
    if source not in {'github', 'cnb'}:
        raise ValueError('Unsupported Homebrew source')
    url = info['url'] if source == 'github' else cnb_url(project, info)
    version, revision = info['version'], info['revision']
    if project == 'dnr':
        text = (ROOT/'templates/dnr.rb.in').read_text()
        values = {'REPOSITORY': info['repository'], 'VERSION': version, 'SHA256': info['sha256'],
                  'URL': url, 'REVISION': f'\n  revision {revision}' if revision else ''}
        for key, value in values.items():
            text = text.replace('@' + key + '@', value)
        return 'Formula/dnr.rb', text
    if project == 'mihomomo':
        return 'Formula/mihomomo.rb', f'''class Mihomomo < Formula
  desc "Mihomomo proxy core for Clash Momo"
  homepage "https://github.com/fansion314/momo"
  url "{url}"
  version "{version}-{info['release']}"
  revision {revision}
  sha256 "{info['sha256']}"
  license "GPL-3.0-only"

  depends_on arch: :arm64
  depends_on macos: :sequoia

  def install
    bin.install "bin/mihomomo"
    (share/"mihomomo").install "share/mihomomo/manifest.json"
    pkgshare.install "LICENSE", "README.md"
  end

  test do
    require "json"
    assert_match "{version}", shell_output("#{{bin}}/mihomomo -v")
    capabilities = JSON.parse(shell_output("#{{bin}}/mihomomo --momo-capabilities"))
    assert_equal 1, capabilities["protocol"]
    assert_equal true, capabilities["managedMode"]
  end
end
'''
    if project == 'clash-momo':
        return 'Casks/clash-momo.rb', f'''cask "clash-momo" do
  version "{version}-{info['release']},{revision}"
  sha256 "{info['sha256']}"

  url "{url}"
  name "Clash Momo"
  desc "Graphical proxy client using Mihomomo"
  homepage "https://github.com/fansion314/momo"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on formula: "fansionia/tap/mihomomo"

  app "Clash Momo.app"

  preflight_steps do
    run "/usr/bin/codesign",
        args: ["--verify", "--deep", "--strict", "{{{{staged_path}}}}/Clash Momo.app"]
    run "/bin/sh",
        args: ["-c", '/usr/bin/codesign -dv "$1" 2>&1 | /usr/bin/grep -Fx Signature=adhoc', "sh", "{{{{staged_path}}}}/Clash Momo.app"]
  end

  postflight_steps do
    run "/usr/bin/xattr",
        args: ["-dr", "com.apple.quarantine", "{{{{appdir}}}}/Clash Momo.app"]
  end

  caveats <<~EOS
    This app is ad-hoc signed and is not notarized by Apple.
    This tap removes quarantine from the installed app after signature verification.
  EOS
end
'''
    if project == 'pi-dnr':
        return 'Formula/pi-dnr.rb', f'''class PiDnr < Formula
  desc "Pi coding agent for the shared dnr runtime"
  homepage "https://github.com/fansion314/pi"
  url "{url}"
  version "{version}-{info['release']}"
  revision {revision}
  sha256 "{info['sha256']}"
  license "MIT"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on "fansionia/tap/dnr"
  depends_on "fd"
  depends_on "ripgrep"

  def install
    system Formula["fansionia/tap/dnr"].opt_bin/"dnc", "install", "pi.dnp", libexec/"app"
    (bin/"pi").write <<~SH
      #!/bin/sh
      exec "#{{Formula["fansionia/tap/dnr"].opt_bin}}/dnr" "#{{libexec}}/app/pi.dnp" "$@"
    SH
  end

  test do
    ENV["PI_OFFLINE"] = "1"
    ENV["PI_TELEMETRY"] = "0"
    ENV["PI_CODING_AGENT_DIR"] = (testpath/"config").to_s
    assert_equal "{version}", shell_output("#{{bin}}/pi --version").strip
    assert_match "Usage:", shell_output("#{{bin}}/pi --help")
  end
end
'''
    app = 'balenaEtcher.app'
    name = 'balenaEtcher (dnr)'
    description = 'Flash OS images using the shared dnr runtime'
    cask_version = f"{version}-dnr.{info['release']},{revision}"
    return f'Casks/{project}.rb', f'''cask "{project}" do
  version "{cask_version}"
  sha256 "{info['sha256']}"

  url "{url}"
  name "{name}"
  desc "{description}"
  homepage "https://github.com/{info['repository']}"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on formula: "fansionia/tap/dnr"

  app "{app}"

  preflight_steps do
    run "/usr/bin/codesign",
        args: ["--verify", "--deep", "--strict", "{{{{staged_path}}}}/{app}"]
  end

  postflight_steps do
    # Explicit policy of this personal tap: approve only this installed app.
    run "/usr/bin/xattr",
        args: ["-dr", "com.apple.quarantine", "{{{{appdir}}}}/{app}"]
  end

  caveats <<~EOS
    This app is ad-hoc signed and is not notarized by Apple.
    This tap removes the quarantine attribute from this app only after installation.
    macOS Gatekeeper settings and application data are left unchanged.
  EOS
end
'''


def sync(project):
    repository = PROJECTS[project][0]
    # Paginate so unrelated releases cannot hide a supported stable release.
    pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f'repos/{repository}/releases?per_page=100'))
    available = candidates(project, [release for page in pages for release in page])
    if not available:
        raise ValueError(f'No complete stable macOS release for {project}')
    key, info = available[-1]
    state_path = ROOT/'releases'/f'{project}.json'
    current = json.loads(state_path.read_text()) if state_path.exists() else None
    if current and key < current['key']:
        raise ValueError('Refusing to downgrade an installed tap release')
    if project in {'clash-momo', 'mihomomo'}:
        commit = json.loads(run('gh', 'api', f'repos/{repository}/commits/{info["tag"]}'))['sha']
        if not re.fullmatch(r'[a-f0-9]{40}', commit):
            raise ValueError('Invalid source commit SHA')
        info['source_sha'] = commit
        if current and key == current['key'] and current.get('source_sha') != commit:
            raise ValueError('Refusing to replace immutable source commit')
    info['sha256'] = verified_digest(info)
    info['key'] = key
    if current and key == current['key'] and (info['sha256'], info['url']) != (current['sha256'], current['url']):
        raise ValueError('Refusing to replace an immutable release; increase revision')
    path, content = render(project, info)
    (TAP_ROOT/path).parent.mkdir(exist_ok=True)
    (TAP_ROOT/path).write_text(content)
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps(info, indent=2) + '\n')
    print(f'{project}: {info["tag"]} revision {info["revision"]}, sha256 {info["sha256"]}')


def validation_inputs(root=TAP_ROOT):
    root = Path(root)
    policy = hashlib.sha256()
    for filename in ['sync.py', 'test-install.sh', 'test-clash-momo.sh']:
        policy.update((Path(__file__).parent/filename).read_bytes())
    inputs = {}
    for project in PROJECTS:
        record = json.loads((root/'homebrew/releases'/f'{project}.json').read_text())
        relative, _ = render(project, record)
        inputs[project] = hashlib.sha256(json.dumps({
            'release': record, 'recipe': (root/relative).read_text(),
            'policy': policy.hexdigest()}, sort_keys=True).encode()).hexdigest()
    return inputs


def validation_projects(current, accepted, full=False):
    changed = set(current) if full else {p for p in current if accepted.get(p) != current[p]}
    if 'dnr' in changed:
        changed.update(['pi-dnr', 'etcher-dnr'])
    if 'mihomomo' in changed:
        changed.add('clash-momo')
    return [p for p in ['dnr', 'pi-dnr', 'etcher-dnr', 'mihomomo', 'clash-momo'] if p in changed]


def install(projects):
    started = time.monotonic()
    subprocess.run(['bash', str(Path(__file__).with_name('test-install.sh')), *projects], check=True)
    origin = os.environ.get('HOMEBREW_TAP_URL', 'https://github.com/fansion314/packages.git')
    message = f'Homebrew installation from {origin} passed for {", ".join(projects)} in {time.monotonic()-started:.1f}s'
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(message+'\n')


def validate():
    receipt = ROOT/'verification.json'
    current = validation_inputs()
    previous = json.loads(receipt.read_text()).get('projects', {}) if receipt.exists() else {}
    projects = validation_projects(current, previous, os.environ.get('FULL_VERIFY') == '1')
    if projects:
        install(projects)
        receipt.write_text(json.dumps({'schema': 1, 'projects': current}, indent=2, sort_keys=True)+'\n')
    else:
        print('Homebrew primary recipes already accepted')
    return projects


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('projects', nargs='*', metavar='PROJECT')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--validate', action='store_true')
    actions.add_argument('--install', action='store_true')
    args = parser.parse_args()
    if unknown := set(args.projects)-PROJECTS.keys():
        parser.error('unknown Homebrew project: '+', '.join(sorted(unknown)))
    if args.validate:
        validate()
    elif args.install:
        install(args.projects or list(PROJECTS))
    else:
        for project in args.projects or PROJECTS:
            sync(project)
