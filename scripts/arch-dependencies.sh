#!/usr/bin/env bash
set -euo pipefail
project=${1:?package id required}
pacman -Syu --noconfirm --needed base-devel git python nodejs npm pnpm electron asar rust sccache \
  gnome-keyring desktop-file-utils xorg-server-xvfb xorg-xauth dbus xdg-utils
# Source templates contain fixed metadata only; evaluated on the isolated Arch runner.
recipe=$(find "packages/$project/recipes" -mindepth 2 -maxdepth 2 -name PKGBUILD ! -path '*-bin/*' -print -quit)
source "$recipe"
packages=()
for dependency in "${depends[@]}" "${makedepends[@]:-}"; do
  if [[ -n $dependency && $dependency != org.freedesktop.secrets && $dependency != python-pptx ]]; then
    packages+=("$dependency")
  fi
done
pacman -S --noconfirm --needed "${packages[@]}"
if [[ $project == deepseek-harness ]]; then
  pacman -S --noconfirm --needed python-build python-installer python-setuptools python-wheel python-pyparsing python-pytest
  git clone https://aur.archlinux.org/python-pptx.git /tmp/python-pptx
  git -C /tmp/python-pptx checkout 74f6b47a97b0f8c476b64db9ad7fdc0f443a69c8
  chown -R builder:builder /tmp/python-pptx
  runuser -u builder -- bash -c 'cd /tmp/python-pptx && makepkg --noconfirm'
  pacman -U --noconfirm /tmp/python-pptx/python-pptx-*.pkg.tar.zst
fi
