#!/usr/bin/env bash
# Disposable native Arch CI only. Uses the packaged production executable.
set -euo pipefail
[[ ${CI:-} == true ]] || exit 2
archive=$(realpath "${1:?archive required}")
source_dir=$(realpath "${2:?prepared source required}")
root=$(cd "$(dirname "$0")/../.." && pwd)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
bsdtar -xf "$archive" -C "$stage" usr
export HGHUB_SMOKE_BINARY="$stage/usr/bin/hghub"
export HGHUB_SMOKE_EVIDENCE="$root/.work/evidence/hghub"
export HGHUB_SMOKE_SOURCE="$source_dir"
export XDG_CONFIG_HOME="$stage/config" XDG_CACHE_HOME="$stage/cache" XDG_DATA_HOME="$stage/data"
# Xvfb has no hardware display; keep rendering overrides confined to CI smoke.
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe WEBKIT_DISABLE_DMABUF_RENDERER=1
export LANG=C.UTF-8 LC_ALL=C.UTF-8
mkdir -p "$HGHUB_SMOKE_EVIDENCE" "$stage/media"
# Generated color bars and a sine wave contain no upstream content.
ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=320x240:rate=15 \
  -f lavfi -i sine=frequency=440:sample_rate=44100 -t 12 -c:v libx264 -preset ultrafast \
  -pix_fmt yuv420p -g 30 -c:a aac -f hls -hls_time 2 -hls_playlist_type vod \
  -hls_segment_filename "$stage/media/segment%02d.ts" "$stage/media/list.m3u8"
export HGHUB_SMOKE_MEDIA="$stage/media"
export HGHUB_NATIVE_DRIVER="$root/.work/tools/hghub/WebKitWebDriver"
python "$root/packages/hghub/prepare-webdriver.py" "$HGHUB_NATIVE_DRIVER" "$HGHUB_SMOKE_EVIDENCE"
dbus-run-session -- xvfb-run -a -s '-screen 0 1920x1080x24' python "$root/packages/hghub/smoke.py"
