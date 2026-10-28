#!/usr/bin/env bash
# Retry from the latest branch when another validated sync changes shared outputs.
set -euo pipefail
kind=${1:?homebrew or aur}
project=${2:-}
for attempt in 1 2 3 4 5; do
  if [[ $kind == homebrew ]]; then
    python3 homebrew/scripts/sync.py
    bash homebrew/scripts/test-install.sh
  else
    python3 -u aur/scripts/sync.py ${project:+"$project"}
    if [[ ${GITHUB_EVENT_NAME:-} != schedule ]]; then
      python3 -c 'import json,pathlib,sys; m=json.load(open("aur/sources.json")); pathlib.Path("aur/.cache/changed.json").write_text(json.dumps([n for p in m["projects"] if not sys.argv[1] or p["id"] == sys.argv[1] for n in p["packages"]]))' "$project"
    fi
    docker run --rm --volume "$PWD:/repo" --workdir /repo/aur --env "BUILD_UID=$(id -u)" --env "VALIDATE_PROJECT=${project:-all}" \
      ghcr.io/archlinux/archlinux:base-devel bash scripts/ci-validate.sh
  fi
  result=0
  bash scripts/commit-generated.sh "$kind" || result=$?
  if (( result == 0 )); then exit 0; fi
  if (( result != 75 )); then exit "$result"; fi
  # The checkout is disposable CI state. Keep the validated candidate in its local commit.
  git checkout --detach origin/main
 done
exit 1
