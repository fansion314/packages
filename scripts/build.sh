#!/usr/bin/env bash
# Native Arch CI only; no application builds run on the maintainer's machine.
set -euo pipefail
project=${1:?package id required}
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
(( EUID != 0 )) || { echo 'Run builds as an unprivileged builder.' >&2; exit 1; }
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export MOTRIX_SKIP_ELECTRON_REBUILD=1
export MOTRIX_SKIP_ENGINE_FETCH=1
packaging_ref="commit=$(git rev-parse HEAD)"
release_tag=${RELEASE_TAG:-}
if [[ -z $release_tag && ${GITHUB_REF_TYPE:-} == tag ]]; then release_tag=$GITHUB_REF_NAME; fi
if [[ -n $release_tag ]]; then
  [[ $(python scripts/package.py resolve "$release_tag") == "$project" ]]
  [[ $(git rev-parse "refs/tags/$release_tag^{commit}") == $(git rev-parse HEAD) ]]
  packaging_ref="tag=$release_tag"
fi
work="$root/.work/$project"
mkdir -p "$work"
python scripts/package.py recipes "$project" "$work/recipes" --packaging-ref "$packaging_ref" --metadata
name=$(python -c 'import sys; sys.path.insert(0,"scripts"); import package; print(package.manifest(sys.argv[1])["package"])' "$project")
case "$project" in
  motrix|deepseek-harness)
    (cd "$work/recipes/$name" && makepkg --noconfirm --nodeps)
    source_dir="$work/recipes/$name/src/$([[ $project == motrix ]] && echo Motrix || echo deepseek-harness)"
    cd "$source_dir"
    if [[ $project == motrix ]]; then
      pnpm run check:boundaries
      pnpm run lint
      pnpm exec tsc --noEmit
      pnpm run check:file-names
      pnpm run check:i18n
      pnpm exec vitest run tests/scripts/arch-package.test.ts tests/scripts/stage-electron-app.test.ts tests/scripts/postinstall-flow.test.ts src/core/settings/settings-manager.test.ts src/shared/schemas/app-settings.test.ts src/main/window/window-manager.test.ts src/main/platform/tray-icon.test.ts src/main/platform/tray.test.ts src/renderer/routes/settings/cards/appearance-dialog.test.tsx
      desktop-file-validate build/arch/motrix.desktop
      dbus-run-session -- xvfb-run -a pnpm run verify:arch -- release/*.asar --smoke
    else
      pnpm run lint
      pnpm exec vitest run apps/desktop/tests/interface-scale.spec.ts apps/desktop/tests/window-state.spec.ts apps/desktop/tests/termination.spec.ts apps/desktop/tests/tray.spec.ts apps/desktop/tests/main-startup.spec.ts apps/desktop/tests/platform-view.spec.ts packages/client/ui-settings-general/tests/desktop-scale.client.spec.tsx packages/client/ui-sidebar/tests/sidebar-snapshot.client.spec.tsx
      node --test aur/system-runtime.test.mjs
      node aur/smoke-cli.mjs
      dbus-run-session -- xvfb-run -a node aur/smoke-shell.mjs
      desktop-file-validate aur/dsh-electron.desktop
    fi
    cd "$root"
    archive=$(find "$work/recipes/$name" -maxdepth 1 -name '*.pkg.tar.zst' -print -quit)
    ;;
  bitwarden|obsidian)
    python scripts/package.py prepare "$project" "$work/app"
    cd "$work/app"
    for dir in "$project-electron" "$project-electron-bin"; do
      (cd "$dir" && makepkg --printsrcinfo > .SRCINFO)
    done
    if [[ $project == bitwarden ]]; then
      makepkg --printsrcinfo > .SRCINFO
      bash .github/scripts/build.sh
      archive=$(find "$PWD/dist/release" -name '*.pkg.tar.zst' -print -quit)
    else
      bash ci/build.sh
      archive=$(find "$PWD/dist/x86_64" -name '*.pkg.tar.zst' -print -quit)
    fi
    cd "$root"
    ;;
  *) echo 'Unknown package' >&2; exit 1 ;;
esac
python scripts/package.py finalize "$project" "$archive" "$root/dist/$project"
# Exercise the exact published recipe with the already-built input as source cache.
cp "$archive" "$root/dist/$project/aur/$name-bin/"
(cd "$root/dist/$project/aur/$name-bin" && makepkg --nodeps --noconfirm)
