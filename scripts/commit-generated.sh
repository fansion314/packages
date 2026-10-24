#!/usr/bin/env bash
# Keep unrelated concurrent commits; reject changed inputs/outputs so the caller regenerates.
set -euo pipefail
kind=${1:?homebrew or aur}
case "$kind" in
  homebrew) paths=(Formula Casks homebrew/releases); inputs=(homebrew/scripts homebrew/templates scripts) ;;
  aur) paths=(aur/packages aur/state); inputs=(aur/sources.json aur/scripts scripts) ;;
  *) exit 2 ;;
esac
if [[ -z $(git status --porcelain -- "${paths[@]}") ]]; then exit 0; fi
base=$(git rev-parse HEAD)
git add -- "${paths[@]}"
git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
  commit -m "chore: update verified $kind packages"
for attempt in 1 2 3 4 5; do
  git fetch origin main
  remote=$(git rev-parse origin/main)
  if [[ $base != "$remote" ]]; then
    if ! git diff --quiet "$base" "$remote" -- "${inputs[@]}" "${paths[@]}"; then
      echo 'Synchronization inputs or outputs advanced; regenerate against latest main.' >&2
      exit 75
    fi
    git rebase origin/main
    base=$remote
  fi
  auth=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
  if git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $auth" push origin HEAD:main; then exit 0; fi
done
exit 1
