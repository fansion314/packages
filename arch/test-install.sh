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
pacman -Syu --noconfirm fansionia-keyring
pacman -Fy --noconfirm
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
