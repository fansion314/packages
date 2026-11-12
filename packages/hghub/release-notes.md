## HGhub 1.2.1 source transition

This community Arch build now follows [bashirian777/HGhub v1.2.1](https://github.com/bashirian777/HGhub/releases/tag/v1.2.1),
pinned to `bba3152215ca0e18a3042fa854ff2dae743c2fe0`. It is a continuation fork of
Minireel/HGhub, not a release by the original maintainer.

- Uses upstream's new playback POST endpoint, legacy-response normalization,
  fallback and retry behavior. The duplicate local Rust playback patch is removed.
- Preserves upstream's Linux platform support, player retry trigger, new player
  controls, clean-screen mode and media cache improvements.
- Retains persistent interface scale, native zoom shortcuts and Linux resize
  handles. Keeps the existing scale preference and `com.hghub.huangguo` identity.
- Retains tested frontend full-stream selection and ignores stale responses after
  switching episodes. Preview streams are never substituted for full videos.
- Updates the source recipe and in-app repository link to the active fork.
  Updates continue through pacman/paru; original license and Required Notice remain intact.

## Validation

CI records the deterministic WebKitGTK playback/scaling fixture separately
from a live probe through the packaged IPC and `hg://` media transport. The
live probe checks a current source, HLS playlist, encryption key when present,
and a media segment; it does not claim physical display or audio acceptance.
Source-selection and episode-cancellation regressions run without upstream traffic.
