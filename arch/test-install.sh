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
    raise SystemExit('Configured upstreams contributed no packages')
if external:
    subprocess.run(['pacman', '-Sw', '--noconfirm', *['fansionia/'+p for p in external]], check=True)
    # Separate transactions avoid conflicts between otherwise valid upstream apps.
    for package in external:
        subprocess.run(['pacman', '-S', '--noconfirm', 'fansionia/'+package], check=True)
        subprocess.run(['pacman', '-Qk', package], check=True)
        subprocess.run(['pacman', '-Rns', '--noconfirm', package], check=True)
PY
pacman -Si dnr dnr-cef dnr-webview dnc pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron mygo-cloudmusic clash-momo mihomomo python-pptx
# Download and verify every variant. Mutually conflicting runtime alternatives
# cannot be installed together, but each must be a valid signed archive.
pacman -Sw --noconfirm dnr dnc pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron mygo-cloudmusic clash-momo mihomomo python-pptx
pacman -Sw --noconfirm dnr-cef
pacman -Sw --noconfirm dnr-webview
pacman -S --noconfirm dnr dnc pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron mygo-cloudmusic clash-momo mihomomo python-pptx
mihomomo -v
getcap /usr/bin/mihomomo | grep -F 'cap_net_bind_service,cap_net_admin,cap_net_raw=ep'
test ! -u /usr/bin/mihomomo
dnr --version
dnc --version
pi --help >/dev/null
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
for package in dnr dnc pi-dnr etcher-dnr motrix-electron dsh-electron bitwarden-electron obsidian-electron mygo-cloudmusic clash-momo mihomomo python-pptx fansionia-keyring; do
  pacman -Q "$package"
  pacman -Qk "$package"
done
