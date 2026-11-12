#!/usr/bin/env bash
# Only in a disposable native Arch CI container, never on the maintainer host.
set -euo pipefail
[[ ${CI:-} == true && $(uname -sm) == 'Linux x86_64' ]] || exit 2
server=${1:?repository server URL}
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
python - "$server" <<'PY'
import json
from pathlib import Path
import subprocess
settings = json.loads(Path('arch/sources.json').read_text())
# Discover from the merged database, so future configured packages are covered
# without keeping a second hard-coded allowlist. Existing apps are tested below.
internal = {name for p in settings['projects'] for name in p['packages']}
packages = subprocess.check_output(['pacman', '-Slq', 'fansionia'], text=True).splitlines()
external = sorted(set(packages)-internal)
if settings.get('upstreams') and not external:
    print('WARNING: no available upstream packages in this snapshot; acquisition failures are retried next sync')
if external:
    # Separate transactions avoid conflicts between otherwise valid upstream apps.
    for package in external:
        subprocess.run(['pacman', '-Sw', '--noconfirm', 'fansionia/'+package], check=True)
        subprocess.run(['pacman', '-S', '--noconfirm', 'fansionia/'+package], check=True)
        subprocess.run(['pacman', '-Qk', package], check=True)
        subprocess.run(['pacman', '-Rns', '--noconfirm', package], check=True)
PY
available_names=$(pacman -Slq fansionia)
mapfile -t available <<< "$available_names"
has_package() { [[ " ${available[*]} " == *" $1 "* ]]; }
applications=()
for package in dnr dnc pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron mygo-music hghub longbridge clash-momo mihomomo python-pptx; do
  if has_package "$package"; then applications+=("$package"); fi
done
# Download and verify every variant. Mutually conflicting runtime alternatives
# cannot be installed together, but each must be a valid signed archive.
if ((${#applications[@]})); then
  pacman -Si "${applications[@]}"
  pacman -Sw --noconfirm "${applications[@]}"
  pacman -S --noconfirm "${applications[@]}"
fi
for package in dnr-cef dnr-webview; do
  if has_package "$package"; then
    pacman -Si "$package"
    pacman -Sw --noconfirm "$package"
  fi
done
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
