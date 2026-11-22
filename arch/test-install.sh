#!/usr/bin/env bash
# Only in a disposable native Arch CI container, never on the maintainer host.
set -euo pipefail
[[ ${CI:-} == true && $(uname -sm) == 'Linux x86_64' ]] || exit 2
server=${1:?repository server URL}
targets=${2:?accepted package selection}
SECONDS=0
pacman-key --init
pacman-key --add arch/keys/fansionia.asc
fingerprint=$(cat arch/keys/fingerprint.txt)
pacman-key --lsign-key "$fingerprint"
cat >> /etc/pacman.conf <<EOF

[fansionia]
SigLevel = Required TrustedOnly
Server = $server
EOF
# Bootstrap only the keyring before a full upgrade can encounter upstream keys.
pacman -Sy --noconfirm fansionia/fansionia-keyring
pacman -Syu --noconfirm
pacman -Fy --noconfirm
available_names=$(pacman -Slq fansionia)
mapfile -t available <<< "$available_names"
mapfile -t selected < "$targets"
has_package() { [[ " ${selected[*]} " == *" $1 "* ]]; }
for package in "${selected[@]}"; do
  if [[ " ${available[*]} " != *" $package "* ]]; then
    echo "Expected package missing from the signed database: $package" >&2
    exit 1
  fi
done

python - "$targets" <<'PYTHON'
import json
from pathlib import Path
import subprocess
import sys

settings = json.loads(Path('arch/sources.json').read_text())
internal = {name for project in settings['projects'] for name in project['packages']}
selected = set(Path(sys.argv[1]).read_text().splitlines())
# Use separate transactions because independently maintained upstream packages
# may conflict. Their dependencies are resolved by pacman from the live DB.
for package in sorted(selected - internal):
    subprocess.run(['pacman', '-S', '--noconfirm', 'fansionia/'+package], check=True)
    subprocess.run(['pacman', '-Qk', package], check=True)
    subprocess.run(['pacman', '-Rns', '--noconfirm', package], check=True)
PYTHON
# The DNR variants conflict with each other and with the standard runtime.
for package in dnr-cef dnr-webview; do
  if has_package "$package"; then
    pacman -S --noconfirm "fansionia/$package"
    dnr --version
    pacman -Qk "$package"
    pacman -R --noconfirm "$package"
  fi
done
# Droidloom's runtime, image and base are released and accepted together.
if has_package droidloom-runtime || has_package droidloom-image || has_package droidloom-base; then
  droidloom=(droidloom-runtime droidloom-image droidloom-base)
  pacman -S --noconfirm "${droidloom[@]/#/fansionia/}"
  pacman -Qk "${droidloom[@]}"
fi
applications=()
for package in dnr dnc pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron mygo-music hghub longbridge clash-momo mihomomo python-pptx; do
  if has_package "$package"; then applications+=("$package"); fi
done
if ((${#applications[@]})); then
  pacman -S --noconfirm "${applications[@]/#/fansionia/}"
fi
if has_package longbridge; then
test -x /usr/bin/longbridge-desktop
test -r /usr/share/applications/longbridge-desktop.desktop
grep -Fx 'Exec=longbridge-desktop' /usr/share/applications/longbridge-desktop.desktop
grep -Fx 'StartupWMClass=com.longbridge.app.desktop' /usr/share/applications/longbridge-desktop.desktop
test -s /usr/share/icons/hicolor/512x512/apps/longbridge.png
ldd /usr/lib/longbridge/longbridge.app/bin/longbridge > /tmp/longbridge-ldd.txt
! grep -F 'not found' /tmp/longbridge-ldd.txt
fi
if has_package hghub; then
test -x /usr/bin/hghub
test -r /usr/share/applications/com.hghub.huangguo.desktop
grep -F 'Exec=hghub' /usr/share/applications/com.hghub.huangguo.desktop
grep -F 'PolyForm Noncommercial License 1.0.0' /usr/share/licenses/hghub/LICENSE
grep -F 'Required Notice: Copyright (c) 2026 HGhub contributors' /usr/share/licenses/hghub/LICENSE
ldd /usr/bin/hghub > /tmp/hghub-ldd.txt
! grep -F 'not found' /tmp/hghub-ldd.txt
grep -F 'libwebkit2gtk-4.1.so' /tmp/hghub-ldd.txt
grep -F 'libgtk-3.so' /tmp/hghub-ldd.txt
fi
if has_package mihomomo; then
mihomomo -v
getcap /usr/bin/mihomomo | grep -F 'cap_net_bind_service,cap_net_admin,cap_net_raw=ep'
test ! -u /usr/bin/mihomomo
fi
if has_package dnr; then dnr --version; fi
if has_package dnc; then dnc --version; fi
if has_package pi-dnr; then pi --help >/dev/null; fi
if has_package python-pptx; then
python - <<'PY'
from pptx import Presentation
import io
presentation = Presentation()
presentation.slides.add_slide(presentation.slide_layouts[6])
stream = io.BytesIO()
presentation.save(stream)
stream.seek(0)
assert len(Presentation(stream).slides) == 1
PY
fi
for package in "${applications[@]}" fansionia-keyring; do
  pacman -Q "$package"
  pacman -Qk "$package"
done

python - <<'PYTHON'
from pathlib import Path
import os
import subprocess

output = subprocess.check_output(['pacman', '-Sl', 'fansionia'], text=True)
archives = list(Path('/var/cache/pacman/pkg').glob('*.pkg.tar.*'))
packages = {tuple(line.split()[1:3]) for line in output.splitlines()}
size = sum(path.stat().st_size for path in archives if any(
    path.name.removeprefix(name+'-').startswith(version+'-') and path.name.startswith(name+'-')
    for name, version in packages))
message = f'Package bytes downloaded from the repository: {size}'
print(message)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(message+'\n')
PYTHON
message="Install acceptance completed in ${SECONDS}s"
echo "$message"
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then echo "$message" >> "$GITHUB_STEP_SUMMARY"; fi
