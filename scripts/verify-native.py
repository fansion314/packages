#!/usr/bin/env python3
"""Load the official applications' native addons with Arch's system Electron."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

MODULES = {
    'bitwarden': ['@bitwarden/desktop-napi/desktop_napi.linux-x64-gnu.node'],
    'obsidian': ['btime/binding.node', 'get-fonts/binding.node'],
}


def verify(project, archive):
    prefix = f'usr/lib/{project}-electron'
    with tempfile.TemporaryDirectory(prefix=project+'-native-') as directory:
        subprocess.run(['bsdtar', '-xf', str(Path(archive).resolve()), '-C', directory, prefix], check=True)
        files = [str(Path(directory)/prefix/'app.asar.unpacked/node_modules'/name) for name in MODULES[project]]
        for name in files:
            if not Path(name).is_file():
                raise ValueError('Missing native addon: '+name)
        code = r'''
const fs = require('node:fs');
const crypto = require('node:crypto');
const files = process.argv.slice(1).map(file => {
  const loaded = require(file);
  return { path: file.slice(file.indexOf('/usr/lib/') + 1), exports: typeof loaded,
    sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') };
});
console.log('NATIVE_ABI_OK '+JSON.stringify({ electron: process.versions.electron,
  abi: process.versions.modules, napi: process.versions.napi, files }));
'''
        subprocess.run(['dbus-run-session', '--', '/usr/bin/electron', '-e', code, *files],
                       env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'}, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', choices=MODULES)
    parser.add_argument('archive')
    arguments = parser.parse_args()
    verify(arguments.project, arguments.archive)
