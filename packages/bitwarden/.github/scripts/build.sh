#!/usr/bin/env bash
# Build in Arch as an ordinary user. Publish the verified pacman package.
set -euo pipefail
cd "$(dirname "$0")/../.."
root=$PWD
if (( EUID == 0 )); then
  echo 'Run this script as a non-root build user.' >&2
  exit 1
fi

mkdir -p dist/release .cache
work=$(mktemp -d "$root/.cache/release-build.XXXXXX")
for recipe in . bitwarden-electron; do
  (cd "$recipe" && makepkg --printsrcinfo) > "$work/SRCINFO.generated"
  diff -u "$recipe/.SRCINFO" "$work/SRCINFO.generated"
done
export PKGDEST="$work/packages"
mkdir -p "$PKGDEST"
(
  cd bitwarden-electron
  makepkg --cleanbuild --force --noconfirm
)

source ./bitwarden-electron/PKGBUILD
version="${pkgver}-${pkgrel}"
[[ "$version" =~ ^[0-9][0-9A-Za-z.+_-]*$ ]]
printf 'v%s\n' "$version" > dist/tag.txt
package="$PKGDEST/${pkgname}-${version}-x86_64.pkg.tar.zst"
[[ -f "$package" ]]
archive="$root/dist/release/bitwarden-electron-${version}-x86_64.pkg.tar.zst"
cp "$package" "$archive"
bsdtar -tf "$archive" > "$work/archive-files.txt"
for entry in usr/lib/bitwarden-electron/app.asar usr/lib/bitwarden-electron/bitwarden \
             usr/lib/bitwarden-electron/desktop_proxy usr/lib/bitwarden-electron/libprocess_isolation.so usr/bin/bitwarden; do
  grep -qx "$entry" "$work/archive-files.txt"
done
if grep -Eq '(^opt/|chrome-sandbox|resources\.pak|icudtl\.dat|hibernate|patch-app)' "$work/archive-files.txt"; then
  echo 'Unexpected install path or bundled runtime in package.' >&2
  exit 1
fi
mkdir "$work/payload"
bsdtar -xf "$archive" -C "$work/payload" usr

# Exercise the AUR download recipe against the exact archive to be published.
bin_dir="$work/bin-recipe"
node .github/scripts/render-bin.mjs PKGBUILD "$bin_dir" "$pkgver" "$pkgrel" "$archive"
ln -s "$archive" "$bin_dir/$(basename "$archive")"
(
  cd "$bin_dir"
  makepkg --printsrcinfo > .SRCINFO
  makepkg --cleanbuild --force --noconfirm
)
mkdir "$work/bin-payload"
bsdtar -xf "$PKGDEST/bitwarden-electron-bin-${version}-x86_64.pkg.tar.zst" -C "$work/bin-payload" usr
diff -qr --no-dereference "$work/payload" "$work/bin-payload"
mkdir -p dist/bin-recipe
cp "$bin_dir/PKGBUILD" "$bin_dir/.SRCINFO" dist/bin-recipe/

# Refuse stale/extra publication outputs. Metadata below stays in Actions.
[[ $(find dist/release -mindepth 1 -maxdepth 1 | wc -l) -eq 1 ]]
(
  cd dist
  sha256sum "release/$(basename "$archive")" > SHA256SUMS
  sha256sum --check SHA256SUMS
)
digest=$(sha256sum "$archive" | cut -d ' ' -f 1)
cat > dist/release-notes.md <<EOF
Prepared Bitwarden Desktop ${pkgver} pacman package and \`bitwarden-electron-bin\` AUR recipe.

The package installs application files under \`/usr/lib/bitwarden-electron\` with desktop integration and depends on system Electron. Download the \`.pkg.tar.zst\` asset and install with \`pacman -U\`. The AUR recipe still runs \`makepkg\` and repackages the payload.

\`bitwarden-electron\` remains the alternative recipe that extracts the official upstream release locally.

SHA-256: \`${digest}\`
Built from commit $(git rev-parse HEAD).
EOF
