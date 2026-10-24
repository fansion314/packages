#!/bin/bash
# System Electron renders the shell and supplies Node for the Host.
set -euo pipefail
app=$(realpath -- "$(dirname -- "${BASH_SOURCE[0]}")/../lib/dsh-electron")
export DSH_DESKTOP_DSH_DIR="$app/app.asar/dsh"
export DSH_DESKTOP_NODE_BIN="$app/runtime/bin"
system_runtime=$("$app/runtime/bin/node" "$app/system-runtime.mjs" "$app" "${XDG_CACHE_HOME:-$HOME/.cache}/dsh-electron/runtimes")
export DSH_DESKTOP_PNPM_ENTRY="$app/runtime/pnpm/bin/pnpm.mjs"
export DSH_DESKTOP_PRIMARY_RUNTIME_DIR="$system_runtime/primary-runtime"
export DSH_DESKTOP_PRIMARY_RUNTIME_IN_PLACE=1
export DSH_DESKTOP_HOST_NODE="$app/runtime/bin/node"
export DSH_DESKTOP_OPEN_DEVTOOLS=0
export ELECTRON_FORCE_IS_PACKAGED=false
unset ELECTRON_RUN_AS_NODE
exec /usr/bin/electron --class=dsh-electron "$app/app.asar" "$@"
