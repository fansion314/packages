#!/usr/bin/env bash
# Disposable Arch CI only: exercise the packaged native binary on a real X server.
set -euo pipefail
[[ ${CI:-} == true ]] || exit 2
archive=$(realpath "${1:?archive required}")
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
bsdtar -xf "$archive" -C "$stage" usr
export XDG_CONFIG_HOME="$stage/config" XDG_CACHE_HOME="$stage/cache" XDG_DATA_HOME="$stage/data"
export MYGO_SMOKE_BINARY="$stage/usr/bin/mygo-cloudmusic" MYGO_SMOKE_LOG="$stage/launch.log"
dbus-run-session -- xvfb-run -a bash -euo pipefail -c '
  "$MYGO_SMOKE_BINARY" >"$MYGO_SMOKE_LOG" 2>&1 &
  app_pid=$!
  trap '''kill "$app_pid" 2>/dev/null || true''' EXIT
  timeout 30s xdotool search --sync --onlyvisible --name "MyGo 云音乐"
  kill -0 "$app_pid"
'
cat "$stage/launch.log"
if grep -Ei 'panic:|fatal error:|symbol not found|cannot open shared object' "$stage/launch.log"; then exit 1; fi
