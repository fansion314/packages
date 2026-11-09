#!/usr/bin/env bash
# Disposable native Arch CI only. Never sign in or place orders in smoke tests.
set -euo pipefail
[[ ${CI:-} == true && $(uname -sm) == 'Linux x86_64' ]] || exit 2
archive=$(realpath "${1:?archive required}")
stage=$(mktemp -d)
evidence="${DSH_ARCH_SCREENSHOTS:-$stage/evidence}"
mkdir -p "$evidence"
trap 'cat "$evidence/launch.log" 2>/dev/null || true; rm -rf "$stage"' EXIT
bsdtar -xf "$archive" -C "$stage" usr
binary="$stage/usr/lib/longbridge/longbridge.app/bin/longbridge"
desktop="$stage/usr/share/applications/longbridge-desktop.desktop"
desktop-file-validate "$desktop"
grep -Fx 'Exec=longbridge-desktop' "$desktop"
grep -Fx 'TryExec=longbridge-desktop' "$desktop"
grep -Fx 'StartupWMClass=com.longbridge.app.desktop' "$desktop"
test "$(readlink "$stage/usr/bin/longbridge-desktop")" = /usr/lib/longbridge/longbridge.app/bin/longbridge
test -s "$stage/usr/share/icons/hicolor/512x512/apps/longbridge.png"
test -s "$stage/usr/share/icons/hicolor/1024x1024/apps/longbridge.png"
ldd "$binary" | tee "$evidence/ldd.txt"
! grep -F 'not found' "$evidence/ldd.txt"
# Assert repackaging preserves the vendor executable exactly.
upstream=$(find .work/longbridge/recipes/longbridge/src -path '*/longbridge.app/bin/longbridge' -print -quit)
cmp "$binary" "$upstream"
export LANG=C.UTF-8 LC_ALL=C.UTF-8
export XDG_CONFIG_HOME="$stage/config" XDG_CACHE_HOME="$stage/cache" XDG_DATA_HOME="$stage/data"
export XDG_RUNTIME_DIR="$stage/runtime" LIBGL_ALWAYS_SOFTWARE=1
mkdir -m700 "$XDG_RUNTIME_DIR"
export LONGBRIDGE_SMOKE_BINARY="$binary" LONGBRIDGE_SMOKE_EVIDENCE="$evidence"
dbus-run-session -- xvfb-run -a -s '-screen 0 1920x1080x24' bash -euo pipefail <<'SMOKE'
  openbox >"$LONGBRIDGE_SMOKE_EVIDENCE/openbox.log" 2>&1 &
  wm_pid=$!
  "$LONGBRIDGE_SMOKE_BINARY" >"$LONGBRIDGE_SMOKE_EVIDENCE/launch.log" 2>&1 &
  app_pid=$!
  trap 'kill "$app_pid" "$wm_pid" 2>/dev/null || true' EXIT
  window=$(timeout 60s xdotool search --sync --onlyvisible --limit 1 --pid "$app_pid")
  xdotool getwindowname "$window" | tee "$LONGBRIDGE_SMOKE_EVIDENCE/window.txt"
  xdotool getwindowgeometry "$window" | tee -a "$LONGBRIDGE_SMOKE_EVIDENCE/window.txt"
  kill -0 "$app_pid"
SMOKE
if grep -Ei 'panicked at|symbol lookup error|cannot open shared object' "$evidence/launch.log"; then exit 1; fi
