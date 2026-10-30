#!/usr/bin/env bash
# Exercise the installed app as the ordinary user on a disposable hosted runner.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && $(uname -sm) == 'Darwin arm64' ]]
app=${1:-/Applications/Clash Momo.app}
[[ $# -le 1 && $app == /* ]]
executable=$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$app/Contents/Info.plist")
[[ -n $executable && $executable != */* && -f $app/Contents/MacOS/$executable && -x $app/Contents/MacOS/$executable ]]
app_dir="$HOME/Library/Application Support/clash-momo"
if [[ -e $app_dir || -L $app_dir ]]; then
  echo "Refusing to alter an existing Clash Momo configuration: $app_dir" >&2
  exit 1
fi
smoke_dir=$(mktemp -d /tmp/clash-momo-homebrew-smoke.XXXXXXXX)
app_pid=''
core_pid=''
core_identity=''
find_core() {
  [[ -n $app_pid ]] || return 0
  for candidate in $(pgrep -P "$app_pid" || true); do
    command=$(ps -p "$candidate" -o ucomm= | sed 's/^[[:space:]]*//' || true)
    if [[ $command == */mihomomo || $command == mihomomo ]]; then
      core_pid=$candidate
      core_identity=$(ps -p "$candidate" -o uid= -o lstart= -o ucomm= || true)
      break
    fi
  done
}
cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n $app_pid ]]; then
    [[ -n $core_pid ]] || find_core
    kill -TERM "$app_pid" 2>/dev/null || true
    for ((i=0; i<15; i++)); do
      kill -0 "$app_pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$app_pid" 2>/dev/null; then
      kill -KILL "$app_pid" 2>/dev/null || true
      status=1
    fi
    wait "$app_pid" 2>/dev/null || true
  fi
  if [[ -n $core_pid ]] && kill -0 "$core_pid" 2>/dev/null; then
    echo "App left its Mihomomo process running: $core_pid" >&2
    # Only terminate the exact child observed during this test, and only if
    # its executable still matches the installed core (avoid PID reuse).
    if [[ $(ps -p "$core_pid" -o uid= -o lstart= -o ucomm= 2>/dev/null) == "$core_identity" ]]; then
      kill -TERM "$core_pid" 2>/dev/null || true
      sleep 1
      if [[ $(ps -p "$core_pid" -o uid= -o lstart= -o ucomm= 2>/dev/null || true) == "$core_identity" ]]; then
        kill -KILL "$core_pid" 2>/dev/null || true
      fi
    fi
    status=1
  fi
  if (( status != 0 )); then
    cat "$smoke_dir/app.log" 2>/dev/null || true
    find "$app_dir/logs" "$HOME/Library/Application Support/clash-momo-dev/logs" -type f -exec tail -n 100 {} \; 2>/dev/null || true
  fi
  rm -rf "$smoke_dir" "$app_dir"
  exit "$status"
}
trap cleanup EXIT
mkdir -p "$app_dir"
cat > "$app_dir/config.yaml" <<'CONFIG'
modeSelected: true
operationMode: standard
sysProxy:
  enable: false
  mode: manual
autoSetDNS: false
enableTrafficLogger: true
enableMixedPort: false
enableSocksPort: false
enableHttpPort: false
enableRedirPort: false
enableTproxyPort: false
autoUpdateProfileOnStart: false
autoCheckUpdate: false
CONFIG
cat > "$app_dir/mihomo.yaml" <<'CONFIG'
tun:
  enable: false
dns:
  enable: false
mixed-port: 0
port: 0
socks-port: 0
redir-port: 0
tproxy-port: 0
CONFIG
core_bin="$(brew --prefix mihomomo)/bin/mihomomo"
expected_version=$("$core_bin" --momo-capabilities | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])')
"$app/Contents/MacOS/$executable" >"$smoke_dir/app.log" 2>&1 &
app_pid=$!
socket="/tmp/clash-momo-$(id -u)-$app_pid.sock"
deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  if ! kill -0 "$app_pid" 2>/dev/null; then
    echo 'Clash Momo exited before its core became ready' >&2
    exit 1
  fi
  [[ -n $core_pid ]] || find_core
  if [[ -S $socket ]] &&
    curl -fsS --max-time 2 --unix-socket "$socket" http://localhost/version |
      python3 -c 'import json,sys; assert json.load(sys.stdin)["version"] == sys.argv[1]' "$expected_version" &&
    curl -fsS --max-time 2 --unix-socket "$socket" http://localhost/traffic-history/status |
      python3 -c 'import json,sys; s=json.load(sys.stdin); assert s["enabled"] is True and s["ready"] is True'; then
    [[ -n $core_pid ]] || { echo 'Could not identify the app-owned Mihomomo child' >&2; exit 1; }
    echo "Clash Momo started Mihomomo $expected_version and traffic history is ready."
    exit 0
  fi
  sleep 1
done
echo 'Clash Momo core or traffic history did not become ready within 120 seconds' >&2
exit 1
