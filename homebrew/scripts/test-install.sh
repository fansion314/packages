#!/usr/bin/env bash
set -euo pipefail
projects=("$@")
if (( ${#projects[@]} == 0 )); then
  projects=(dnr pi-dnr etcher-dnr mihomomo clash-momo)
fi
for project in "${projects[@]}"; do
  case $project in
    dnr|pi-dnr|etcher-dnr|mihomomo|clash-momo) ;;
    *) echo "Unknown project: $project" >&2; exit 1 ;;
  esac
done
[[ ${GITHUB_ACTIONS:-} == true && $(uname -sm) == 'Darwin arm64' ]]
brew tap fansionia/tap "${HOMEBREW_TAP_URL:-https://github.com/fansion314/packages.git}"
brew trust fansionia/tap
tap=$(brew --repository fansionia/tap)
if [[ ${HOMEBREW_VERIFY_PUBLISHED:-0} != 1 ]]; then
  candidate=${HOMEBREW_CANDIDATE_ROOT:-.}
  mkdir -p "$tap/Formula" "$tap/Casks"
  cp "$candidate"/Formula/*.rb "$tap/Formula/"
  cp "$candidate"/Casks/*.rb "$tap/Casks/"
fi
# Keep origin tests independent from hosted-runner and earlier-job caches.
export HOMEBREW_CACHE="$(mktemp -d "$RUNNER_TEMP/fansionia-brew-cache.XXXXXXXX")"
for project in "${projects[@]}"; do
  case $project in
    dnr)
      brew install --formula fansionia/tap/dnr
      brew test fansionia/tap/dnr
      ;;
    pi-dnr)
      brew install --formula fansionia/tap/pi-dnr
      brew test fansionia/tap/pi-dnr
      pi --version
      ;;
    mihomomo)
      # Exercise an actual upgrade using the same verified archive under an older
      # synthetic version; the tap is disposable CI state.
      cp "$tap/Formula/mihomomo.rb" "$RUNNER_TEMP/mihomomo.rb"
      sed -i '' 's/^  version ".*"/  version "0.0.1"/' "$tap/Formula/mihomomo.rb"
      brew install --formula fansionia/tap/mihomomo
      cp "$RUNNER_TEMP/mihomomo.rb" "$tap/Formula/mihomomo.rb"
      brew upgrade --formula fansionia/tap/mihomomo
      brew test fansionia/tap/mihomomo
      ;;
    clash-momo)
      cp "$tap/Casks/clash-momo.rb" "$RUNNER_TEMP/clash-momo.rb"
      sed -i '' 's/^  version ".*"/  version "0.0.1-1,1"/' "$tap/Casks/clash-momo.rb"
      brew install --cask fansionia/tap/clash-momo
      cp "$RUNNER_TEMP/clash-momo.rb" "$tap/Casks/clash-momo.rb"
      brew upgrade --cask fansionia/tap/clash-momo
      app="/Applications/Clash Momo.app"
      codesign --verify --deep --strict "$app"
      codesign -dv "$app" 2>&1 | grep -Fx 'Signature=adhoc'
      if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then exit 1; fi
      brew reinstall --cask fansionia/tap/clash-momo
      codesign --verify --deep --strict "$app"
      if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then exit 1; fi
      bash homebrew/scripts/test-clash-momo.sh
      brew uninstall --cask fansionia/tap/clash-momo
      test ! -e "$app"
      ;;
    etcher-dnr)
      brew install --cask fansionia/tap/etcher-dnr
      app=/Applications/balenaEtcher.app
      codesign --verify --deep --strict "$app"
      test "$(plutil -extract DNRRuntimePath raw -o - "$app/Contents/Info.plist")" = dnr
      test "$(plutil -extract DNRLaunchMode raw -o - "$app/Contents/Info.plist")" = supervised
      if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then exit 1; fi
      dnr "$app/Contents/Resources/application.dnp" --self-test
      ;;
  esac
done
