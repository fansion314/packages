#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
root=$PWD
case ${1:-} in
    ''|--source-only) ;;
    *) echo 'Usage: ci/build.sh [--source-only]' >&2; exit 1 ;;
esac
if (( EUID == 0 )); then
    echo 'Run this script as an unprivileged makepkg user.' >&2
    exit 1
fi
source ./obsidian-electron/PKGBUILD
version="${pkgver}-${pkgrel}"
if [[ ${GITHUB_REF_TYPE:-} == tag && ${GITHUB_REF_NAME:-} != "obsidian-v${version}" ]]; then
    echo "Release tag must be obsidian-v${version}, matching PKGBUILD." >&2
    exit 1
fi
outdir="$root/dist/x86_64"
mkdir -p "$outdir" "$root/.cache/sources"
metadata=$(mktemp)
config=$(mktemp)
trap 'rm -f "$metadata" "$config"' EXIT
cat > "$config" <<EOF
source /etc/makepkg.conf
SRCDEST='$root/.cache/sources'
PKGDEST='$outdir'
EOF

build_recipe() (
    local recipe=$1
    local recipe_dir=${2:-$recipe}
    cd "$root/$recipe_dir"
    bash -n PKGBUILD
    makepkg --printsrcinfo > "$metadata"
    diff -u .SRCINFO "$metadata"
    grep -Fx "pkgname = $recipe" "$metadata"
    grep -Fx $'\tarch = x86_64' "$metadata"
    grep -Fx $'\tdepends = electron' "$metadata"
    if [[ $recipe == obsidian-electron ]]; then
        makepkg --config "$config" --cleanbuild --force --noconfirm
    else
        makepkg --config "$config" --cleanbuild --force --noconfirm --noarchive
    fi
    local appdir="pkg/$recipe/usr/lib/obsidian-electron"
    test -s "$appdir/app.asar"
    test -s "$appdir/obsidian.asar"
    desktop-file-validate "$appdir/md.obsidian.Obsidian.desktop"
    [[ $(readlink "pkg/$recipe/usr/bin/obsidian") == /usr/lib/obsidian-electron/obsidian ]]
    [[ $(readlink "pkg/$recipe/usr/share/applications/md.obsidian.Obsidian.desktop") == /usr/lib/obsidian-electron/md.obsidian.Obsidian.desktop ]]
    for addon in btime get-fonts; do
        readelf -h "$appdir/app.asar.unpacked/node_modules/$addon/binding.node" | grep -F 'Advanced Micro Devices X86-64'
    done
)

bash -n obsidian-electron/obsidian.sh
build_recipe obsidian-electron

payload="obsidian-electron-${version}-x86_64.pkg.tar.zst"
test -s "$outdir/$payload"
bsdtar -tf "$outdir/$payload" | grep -Fx 'usr/lib/obsidian-electron/app.asar'
sha256sum "$outdir/$payload"
digest=$(sha256sum "$outdir/$payload" | cut -d ' ' -f 1)
mkdir -p dist/bin-recipe
sed "s/^sha256sums_x86_64=.*/sha256sums_x86_64=('$digest')/" \
    obsidian-electron-bin/PKGBUILD > dist/bin-recipe/PKGBUILD
(cd dist/bin-recipe && makepkg --printsrcinfo > .SRCINFO)

# Maintainers can build this payload first when updating the -bin checksum.
[[ ${1:-} != --source-only ]] || exit 0
# makepkg still verifies the pinned GitHub source hash, using this CI-built
# archive as its source cache until the matching release has been published.
cp "$outdir/$payload" "$root/.cache/sources/$payload"
build_recipe obsidian-electron-bin dist/bin-recipe
diff -r obsidian-electron/pkg/obsidian-electron/usr/lib/obsidian-electron \
    dist/bin-recipe/pkg/obsidian-electron-bin/usr/lib/obsidian-electron
printf 'Built one release payload and verified both recipes for %s\n' "$version"
