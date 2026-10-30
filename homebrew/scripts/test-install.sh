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
test "$(uname -sm)" = 'Darwin arm64'
brew tap fansion314/packages https://github.com/fansion314/packages.git
brew trust fansion314/packages
tap=$(brew --repository fansion314/packages)
cp Formula/*.rb "$tap/Formula/"
mkdir -p "$tap/Casks"
cp Casks/*.rb "$tap/Casks/"
for project in "${projects[@]}"; do
  case $project in
    dnr)
      brew install --formula fansion314/packages/dnr
      brew test fansion314/packages/dnr
      ;;
    pi-dnr)
      brew install --formula fansion314/packages/pi-dnr
      brew test fansion314/packages/pi-dnr
      pi --version
      ;;
    mihomomo)
      # Exercise an actual upgrade using the same verified archive under an older
      # synthetic version; the tap is disposable CI state.
      cp "$tap/Formula/mihomomo.rb" "$RUNNER_TEMP/mihomomo.rb"
      sed -i '' 's/^  version ".*"/  version "0.0.1"/' "$tap/Formula/mihomomo.rb"
      brew install --formula fansion314/packages/mihomomo
      cp "$RUNNER_TEMP/mihomomo.rb" "$tap/Formula/mihomomo.rb"
      brew upgrade --formula fansion314/packages/mihomomo
      brew test fansion314/packages/mihomomo
      ;;
    clash-momo)
      cp "$tap/Casks/clash-momo.rb" "$RUNNER_TEMP/clash-momo.rb"
      sed -i '' 's/^  version ".*"/  version "0.0.1-1,1"/' "$tap/Casks/clash-momo.rb"
      brew install --cask fansion314/packages/clash-momo
      cp "$RUNNER_TEMP/clash-momo.rb" "$tap/Casks/clash-momo.rb"
      brew upgrade --cask fansion314/packages/clash-momo
      app="/Applications/Clash Momo.app"
      codesign --verify --deep --strict "$app"
      codesign -dv "$app" 2>&1 | grep -Fx 'Signature=adhoc'
      if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then exit 1; fi
      brew reinstall --cask fansion314/packages/clash-momo
      codesign --verify --deep --strict "$app"
      if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then exit 1; fi
      brew uninstall --cask fansion314/packages/clash-momo
      test ! -e "$app"
      ;;
    etcher-dnr)
      brew install --cask fansion314/packages/etcher-dnr
      app=/Applications/balenaEtcher.app
      codesign --verify --deep --strict "$app"
      test "$(plutil -extract DNRRuntimePath raw -o - "$app/Contents/Info.plist")" = dnr
      test "$(plutil -extract DNRLaunchMode raw -o - "$app/Contents/Info.plist")" = supervised
      if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then exit 1; fi
      dnr "$app/Contents/Resources/application.dnp" --self-test
      ;;
  esac
done
