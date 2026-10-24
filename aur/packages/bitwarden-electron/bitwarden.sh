#!/bin/sh
# Match Arch's production mode and upstream's process memory protection.
export ELECTRON_IS_DEV=0
ulimit -c 0
export LD_PRELOAD="/usr/lib/bitwarden-electron/libprocess_isolation.so${LD_PRELOAD:+:$LD_PRELOAD}"
export PROCESS_ISOLATION_LD_PRELOAD=/usr/lib/bitwarden-electron/libprocess_isolation.so
exec /usr/bin/electron /usr/lib/bitwarden-electron/app.asar "$@"
