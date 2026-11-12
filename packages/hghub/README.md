# HGhub package maintenance

The current source is `bashirian777/HGhub`, pinned by `manifest.json` to its exact
`v1.2.1` tag commit. The former `Minireel/HGhub v1.2.0` baseline was
`79827baa7542fead68919e7b45f5bfde86b18ee7`. Do not substitute the fork's later main commits.
The v1.2.1 tag includes its Linux release CI change, but this repository builds
and signs its own Arch package through the unified package workflow.

## Patch ownership after v1.2.1

| Area | Ownership |
| --- | --- |
| Playback POST, response normalization, old endpoint fallback and retry | Upstream; removed from the local backend patch |
| Linux labels, desktop styling and store platform type | Upstream; duplicate hunks removed |
| Interface scaling, shortcuts, persistence and Linux resize handles | Local patch 0001 and added overlay helpers |
| Full-stream priority and stale episode response cancellation | Local patch 0002; preserves upstream's `playTry` retry dependency |
| Active repository links and update metadata | Local patch 0003 |

Platform detection retains upstream's iPadOS `MacIntel` fallback and local X11
recognition. The native zoom setting remains `hghub_interface_scale` in the same
application data directory. Frontend source tests cover scale persistence, failed
native zoom, platform precedence, source selection and episode cancellation.

Keep `com.hghub.huangguo`, the original full LICENSE and its Required Notice.
Do not migrate or delete user accounts, history, favorites, settings or cached data.
The Linux package continues to update through pacman/paru.
