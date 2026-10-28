#!/usr/bin/env bash
# Disposable Arch CI only: exercise the packaged native binary on a real X server.
set -euo pipefail
[[ ${CI:-} == true ]] || exit 2
archive=$(realpath "${1:?archive required}")
stage=$(mktemp -d)
trap 'cat "$stage/launch.log" 2>/dev/null || true; rm -rf "$stage"' EXIT
bsdtar -xf "$archive" -C "$stage" usr
export XDG_CONFIG_HOME="$stage/config" XDG_CACHE_HOME="$stage/cache" XDG_DATA_HOME="$stage/data"
export XDG_DATA_DIRS="$stage/usr/share:/usr/local/share:/usr/share"
export MYGO_SMOKE_ROOT="$stage" QT_QPA_PLATFORM=offscreen
export MYGO_ICON_CHECK="$(realpath "$(dirname "$0")/verify-icons.py")"
export MYGO_SMOKE_BINARY="$stage/usr/bin/mygo-cloudmusic" MYGO_SMOKE_LOG="$stage/launch.log"
dbus-run-session -- xvfb-run -a bash -euo pipefail <<'SMOKE'
  "$MYGO_SMOKE_BINARY" >"$MYGO_SMOKE_LOG" 2>&1 &
  app_pid=$!
  trap 'kill "$app_pid" 2>/dev/null || true' EXIT
  main=$(timeout 30s xdotool search --sync --onlyvisible --limit 1 --name '^MyGo 云音乐$')
  xdotool windowfocus --sync "$main"
  xdotool key --clearmodifiers ctrl+comma
  settings=$(timeout 15s xdotool search --sync --onlyvisible --limit 1 --name '^设置$')
  python "$MYGO_ICON_CHECK" "$main" "$settings"
  kill -0 "$app_pid"
SMOKE
if grep -Ei 'panic:|fatal error:|symbol not found|cannot open shared object' "$stage/launch.log"; then exit 1; fi
