#!/usr/bin/env bash
set -euo pipefail
projects=("$@")
if (( ${#projects[@]} == 0 )); then
  projects=(dnr pi-dnr etcher-dnr)
fi
for project in "${projects[@]}"; do
  case $project in
    dnr|pi-dnr|etcher-dnr) ;;
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
brew install --formula fansion314/packages/dnr
brew test fansion314/packages/dnr
for project in "${projects[@]}"; do
  case $project in
    dnr) ;;
    pi-dnr)
      brew install --formula fansion314/packages/pi-dnr
      brew test fansion314/packages/pi-dnr
      pi --version
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
