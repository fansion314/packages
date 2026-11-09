#!/usr/bin/env python3
"""Prepare a pinned CI-only WebKit driver without installing Debian libraries.

Arch's webkit2gtk-4.1 package omits WebKitWebDriver. Debian's official driver
uses the same WebKit 2.54 protocol and ICU 78 ABI as the native Arch runtime.
Only its executable is extracted; all runtime libraries remain Arch packages.
Source/hash: Debian sid main amd64 Packages metadata, verified 2026-11-09.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

URL = ('https://deb.debian.org/debian/pool/main/w/webkit2gtk/'
       'webkitgtk-webdriver_2.54.2-2_amd64.deb')
SHA256 = 'b75de42958b45cfa0fba81d65e471075cbc169bf68b7f3c63092d07979e1bd08'


def prepare(destination, evidence):
    if os.environ.get('CI') != 'true':
        raise RuntimeError('The WebKit driver is CI tooling only')
    version = subprocess.check_output(['pkg-config', '--modversion', 'webkit2gtk-4.1'], text=True).strip()
    if not version.startswith('2.54.'):
        raise RuntimeError(f'Review the pinned WebKit driver for runtime {version}; expected 2.54.x')
    with urllib.request.urlopen(URL, timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != SHA256:
        raise RuntimeError('WebKit driver Debian archive checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='hghub-webdriver-') as temporary:
        package = Path(temporary) / 'driver.deb'
        package.write_bytes(archive)
        data = subprocess.check_output(['ar', 'p', str(package), 'data.tar.xz'])
        executable = subprocess.check_output(
            ['bsdtar', '-xOf', '-', './usr/bin/WebKitWebDriver'], input=data)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(executable)
    destination.chmod(0o755)
    # Fail rather than supplying or overriding any system libraries.
    dependencies = subprocess.check_output(['ldd', str(destination)], text=True)
    if 'not found' in dependencies:
        raise RuntimeError('Pinned WebKit driver has unresolved Arch libraries:\n' + dependencies)
    help_text = subprocess.check_output([str(destination), '--help'], stderr=subprocess.STDOUT, text=True)
    if 'WebKitWebDriver' not in help_text:
        raise RuntimeError('Unexpected WebKit driver executable')
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'native-driver.json').write_text(json.dumps({
        'source': URL, 'archive_sha256': SHA256,
        'executable_sha256': hashlib.sha256(executable).hexdigest(),
        'arch_webkit_version': version, 'dependencies': dependencies,
    }, indent=2) + '\n')
    print('HGHUB_WEBKIT_DRIVER_READY ' + str(destination))


if __name__ == '__main__':
    prepare(*sys.argv[1:])
