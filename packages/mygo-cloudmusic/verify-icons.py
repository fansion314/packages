#!/usr/bin/env python3
"""CI regression check for desktop theme lookup and real X11 window icons."""
import configparser
import os
from pathlib import Path
import re
import subprocess
import sys


def output(*args):
    return subprocess.check_output(args)


root = Path(os.environ['MYGO_SMOKE_ROOT'])
theme = configparser.ConfigParser(interpolation=None)
theme.read('/usr/share/icons/hicolor/index.theme')
expected = {}
for size in [16, 22, 24, 32, 48, 64, 128, 256, 512]:
    directory = f'{size}x{size}/apps'
    assert directory in theme, f'Icon directory is not declared by hicolor: {directory}'
    path = root/'usr/share/icons/hicolor'/directory/'mygo-cloudmusic.png'
    dimensions = output('magick', 'identify', '-format', '%w %h', str(path)).decode()
    assert dimensions == f'{size} {size}', (path, dimensions)
    rgba = output('magick', str(path), '-depth', '8', 'rgba:-')
    expected[size] = [(a << 24) | (r << 16) | (g << 8) | b
                      for r, g, b, a in zip(rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4])]

# This uses KDE's KIconLoader, as Plasma does, rather than checking files alone.
resolved = Path(output('kiconfinder6', 'mygo-cloudmusic').decode().strip())
assert resolved.is_file() and resolved.is_relative_to(root/'usr/share/icons/hicolor'), resolved
print(f'KDE icon lookup: {resolved.relative_to(root)}')

for window in sys.argv[1:]:
    wm_class = output('xprop', '-id', window, 'WM_CLASS').decode()
    assert '"dev.egoist.cloudmusic", "dev.egoist.cloudmusic"' in wm_class, wm_class
    icon = output('xprop', '-id', window, '-notype', '-f', '_NET_WM_ICON', '32c', '_NET_WM_ICON').decode()
    assert '=' in icon, f'Window {window} has no _NET_WM_ICON'
    values = [int(value) for value in re.findall(r'\d+', icon.split('=', 1)[1])]
    matched = False
    while values:
        assert len(values) >= 2, f'Window {window} has an invalid icon header'
        width, height = values[:2]
        count = width * height
        assert count > 0 and len(values) >= count + 2, f'Window {window} has incomplete icon pixels'
        if width == height and values[2:count+2] == expected.get(width):
            matched = True
        values = values[count+2:]
    assert matched, f'Window {window} icon does not match any packaged application PNG'
    print(f'Window {window}: desktop identity and actual icon pixels verified')
