#!/usr/bin/env python3
"""Import only checksum-verified stable release assets from the fixed project allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TAP_ROOT = ROOT.parent
PROJECTS = {
    "dnr": ("fansion314/dnr", r"v(\d+\.\d+\.\d+)", r"dnr-{version}-macos-arm64(?:-r([1-9]\d*))?\.tar\.gz"),
    "pi-dnr": ("fansion314/pi", r"pi-dnr-v(\d+\.\d+\.\d+)-(\d+)", r"pi-dnr-{version}-{release}-macos-arm64-r([1-9]\d*)\.tar\.gz"),
    "etcher-dnr": ("fansion314/etcher", r"v(\d+\.\d+\.\d+)-dnr\.(\d+)", r"etcher-dnr-{version}-{release}-macos-arm64-r([1-9]\d*)\.tar\.gz"),
}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def candidates(project, releases):
    repository, tag_pattern, asset_pattern = PROJECTS[project]
    found = []
    for release in releases:
        if release['draft'] or release['prerelease']:
            continue
        match = re.fullmatch(tag_pattern, release['tag_name'])
        if not match:
            continue
        version = match[1]
        packaging = int(match[2]) if match.lastindex > 1 else 0
        names = {asset['name']: asset for asset in release['assets']}
        for name, asset in names.items():
            m = re.fullmatch(asset_pattern.format(version=re.escape(version), release=packaging), name)
            if not m or name + '.sha256' not in names:
                continue
            revision = int(m[1] or 0)
            url = f"https://github.com/{repository}/releases/download/{release['tag_name']}/{name}"
            if asset['browser_download_url'] != url:
                raise ValueError('Unexpected release asset URL')
            key = [*map(int, version.split('.')), packaging, revision]
            found.append((key, {'repository': repository, 'tag': release['tag_name'], 'version': version,
                                'release': packaging, 'revision': revision, 'asset': name, 'url': url,
                                'github_digest': asset.get('digest')}))
    return sorted(found, key=lambda item: item[0])


def verified_digest(info):
    with tempfile.TemporaryDirectory(prefix='dnr-tap-') as directory:
        subprocess.run(['gh', 'release', 'download', info['tag'], '--repo', info['repository'],
                        '--pattern', info['asset'], '--pattern', info['asset'] + '.sha256', '--dir', directory], check=True)
        archive = Path(directory) / info['asset']
        fields = Path(str(archive) + '.sha256').read_text().split()
        if len(fields) != 2 or fields[1] != info['asset'] or not re.fullmatch('[a-f0-9]{64}', fields[0]):
            raise ValueError('Invalid checksum file')
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != fields[0] or (info['github_digest'] and info['github_digest'] != 'sha256:' + digest):
            raise ValueError('Release checksum mismatch')
        return digest


def render(project, info):
    version, revision = info['version'], info['revision']
    if project == 'dnr':
        text = (ROOT/'templates/dnr.rb.in').read_text()
        values = {'REPOSITORY': info['repository'], 'VERSION': version, 'SHA256': info['sha256'],
                  'ARCHIVE': info['asset'], 'REVISION': f'\n  revision {revision}' if revision else ''}
        for key, value in values.items():
            text = text.replace('@' + key + '@', value)
        return 'Formula/dnr.rb', text
    if project == 'pi-dnr':
        return 'Formula/pi-dnr.rb', f'''class PiDnr < Formula
  desc "Pi coding agent for the shared dnr runtime"
  homepage "https://github.com/fansion314/pi"
  url "{info['url']}"
  version "{version}-{info['release']}"
  revision {revision}
  sha256 "{info['sha256']}"
  license "MIT"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on "fansion314/packages/dnr"
  depends_on "fd"
  depends_on "ripgrep"

  def install
    system Formula["fansion314/packages/dnr"].opt_bin/"dnc", "install", "pi.dnp", libexec/"app"
    (bin/"pi").write <<~SH
      #!/bin/sh
      exec "#{{Formula["fansion314/packages/dnr"].opt_bin}}/dnr" "#{{libexec}}/app/pi.dnp" "$@"
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

  url "{info['url']}"
  name "{name}"
  desc "{description}"
  homepage "https://github.com/{info['repository']}"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on formula: "fansion314/packages/dnr"

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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('projects', nargs='*', choices=list(PROJECTS))
    args = parser.parse_args()
    for project in args.projects or PROJECTS:
        sync(project)
