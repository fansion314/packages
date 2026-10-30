#!/usr/bin/env bash
# Exercise documented source switching on a disposable hosted runner.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && $(uname -sm) == 'Darwin arm64' ]]
tap_name=fansionia/tap
brew tap "$tap_name" https://github.com/fansion314/packages.git
tap=$(brew --repository "$tap_name")
brew trust "$tap_name"
export HOMEBREW_CACHE="$(mktemp -d "$RUNNER_TEMP/fansionia-switch-cache.XXXXXXXX")"
brew install --formula "$tap_name/mihomomo"
for origin in cnb github cnb; do
  if [[ $origin == cnb ]]; then
    remote=https://cnb.cool/fansionia/packages
    prefix=https://cnb.cool/fansionia/packages/-/releases/download/
  else
    remote=https://github.com/fansion314/packages.git
    prefix=https://github.com/
  fi
  brew tap --custom-remote "$tap_name" "$remote"
  brew update-reset "$tap"
  test "$(git -C "$tap" remote get-url origin)" = "$remote"
  brew trust "$tap_name"
  brew info --json=v2 "$tap_name/dnr" "$tap_name/pi-dnr" "$tap_name/mihomomo" > "$RUNNER_TEMP/formula-info.json"
  brew info --json=v2 --cask "$tap_name/etcher-dnr" "$tap_name/clash-momo" > "$RUNNER_TEMP/cask-info.json"
  python3 - "$prefix" "$RUNNER_TEMP" <<'PY'
import json, pathlib, sys
prefix, directory = sys.argv[1], pathlib.Path(sys.argv[2])
formulae = json.loads((directory/'formula-info.json').read_text())['formulae']
casks = json.loads((directory/'cask-info.json').read_text())['casks']
assert len(formulae) == 3 and len(casks) == 2
for item in formulae:
    assert item['urls']['stable']['url'].startswith(prefix), item['name']
for item in casks:
    assert item['url'].startswith(prefix), item['token']
PY
  brew deps --full-name "$tap_name/pi-dnr" | grep -Fx "$tap_name/dnr"
  # Reinstall an existing package after each switch, forcing a fresh download.
  export HOMEBREW_CACHE="$(mktemp -d "$RUNNER_TEMP/fansionia-switch-cache.XXXXXXXX")"
  brew reinstall --formula "$tap_name/mihomomo"
  brew test "$tap_name/mihomomo"
done
brew uninstall --formula "$tap_name/mihomomo"
