## Playback API compatibility

- Fix video playback after the service moved source lookup to the logical
  `POST /api/videos/{id}/episodes/{ep}/playback` endpoint. Requests retain the
  existing edge envelope, session handling and network policy.
- The player and playback self-test prefer `streams.main`, with `video_url`
  compatibility for older mirror responses. Missing full streams report an
  explicit error; previews are not substituted for full videos.
- Adapted from [zxsos/HGhub cfcde4a6](https://github.com/zxsos/HGhub/commit/cfcde4a6e2123c0d6054151ad946c018961cff26)
  for [Minireel/HGhub#31](https://github.com/Minireel/HGhub/issues/31), retaining
  the official v1.2.0 source baseline and this package's Linux interface scaling.

## Validation

CI records the deterministic WebKitGTK playback/scaling fixture separately
from a live probe through the packaged IPC and `hg://` media transport. The
live probe checks a current source, HLS playlist, encryption key when present,
and a media segment; it does not claim physical display or audio acceptance.
Source-selection and episode-cancellation regressions run without upstream
traffic. Updates continue through pacman/paru.
