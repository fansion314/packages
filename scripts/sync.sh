#!/usr/bin/env bash
# Retry from the latest branch when another validated sync changes shared outputs.
set -euo pipefail
kind=${1:?homebrew or aur}
project=${2:-}
if [[ $kind == homebrew ]]; then
  case $project in
    '') homebrew_project= ;;
    dnr|mihomomo|clash-momo) homebrew_project=$project ;;
    pi) homebrew_project=pi-dnr ;;
    etcher) homebrew_project=etcher-dnr ;;
    *) echo "Unknown Homebrew project: $project" >&2; exit 2 ;;
  esac
fi
for attempt in 1 2 3 4 5; do
  if [[ $kind == homebrew ]]; then
    python3 homebrew/scripts/sync.py ${homebrew_project:+"$homebrew_project"}
    python3 homebrew/scripts/sync.py --validate
  else
    aur_args=()
    if [[ ${FULL_VERIFY:-false} == true || ${GITHUB_EVENT_NAME:-} == push ]]; then aur_args+=(--full); fi
    python3 -u aur/scripts/sync.py "${aur_args[@]}" ${project:+"$project"}
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
