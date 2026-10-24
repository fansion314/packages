# pi-dnr-bin

Prebuilt Pi 0.87.1, packaging revision 3, for Linux x86_64. The recipe downloads
`pi-dnr-0.87.1-3-x86_64.pkg.tar.zst` and its checksum from packaging release
`pi-dnr-v0.87.1-3`. The release supplies both the pacman archive and a portable `pi.dnp`.

It verifies the exact archive name and SHA-256 before extraction, then preserves
the application and already prepared native sidecar under `/usr/lib/pi/`.
`/usr/bin/pi` is a relative symlink. It does not compile, run an installer, or
unpack native libraries into the executable search path. Only the Linux native
variant is prepared; the DNP itself also contains the macOS ARM64 variant.

Choose any runtime provider satisfying `dnr>=0.4.0`: `dnr`, `dnr-cef`, `dnr-webview`,
`dnr-bin`, `dnr-cef-bin` or `dnr-webview-bin`. Runtime packages no longer include dnc; neither
dnc nor Node.js is required for ordinary use of this prebuilt package.

```sh
cd packaging/aur/pi-dnr-bin
makepkg -si
```

The package provides `pi-dnr` and `pi-coding-agent`, conflicts with their other
implementations, and preserves `~/.pi`. Optional npm/Git support extension
installation; `wl-clipboard` and `xclip` support clipboard integration.
A manual `/usr/local/bin/pi` may take precedence over the pacman-managed command.

The source build container uses only standalone dnc and small build dependencies,
without installing CEF/GTK/WebKitGTK. Structural and Node-API tests run there;
full runtime smoke tests run separately on a host with dnr installed.
See [the source recipe](../pi-dnr/README.md) for details and validation commands.

## V4 validation (2026-09-26)

Packaging revision 3 uses dnc/dnr 0.4.0 and the v4 cache/sidecar layout.
Pi remains a CLI package with no desktop metadata or icon. `npm run check`
passed without dependency or lockfile changes. The local DNP contains both
platform helpers; its structure/real Node-API test and both cache/sidecar smoke
tests passed from isolated directories using the faux provider. No paid model
API was used. macOS and interactive PTY were not revalidated in this revision.
The DNR release workflow is pinned to standalone dnc 0.4.0.

### V4 publication and local installation

[Actions 36214598692](https://github.com/fansion314/pi/actions/runs/36214598692)
succeeded and published [Pi DNR 0.87.1-3](https://github.com/fansion314/pi/releases/tag/pi-dnr-v0.87.1-3).
The downloaded package and standalone DNP passed their release SHA-256 checks.
Fresh extraction of the final pi-dnr-bin archive passed all three structure,
Node-API, cache and sidecar smoke tests with the official dnr 0.4.0 binary.
The local installation is now pi-dnr-bin 0.87.1-3; `pacman -Qkk` reports 44 files,
none altered, and `/usr/bin/pi --version` reports 0.87.1. The same three isolated
offline tests passed after installation. User settings and sessions were preserved.
No paid model API or new macOS validation was involved.

## V3 release validation (2026-09-25)

Packaging revision 2 requires dnc/dnr 0.3.0. The release workflow downloads the
standalone dnc 0.3.0 asset and uses the unchanged Pi 0.87.1 application version.
`npm run check` passed after hydrating the model data. The v3 DNP contains both
Linux x64 and macOS ARM64 payloads. Linux package/Node-API checks and cache/sidecar
smoke tests passed with the dual-backend dnr 0.3.0, covering CLI, TypeScript
extensions, Photon resizing, local faux-provider bash calls, sessions and HTML
export. No paid model API was used. This run did not repeat macOS or interactive
PTY validation. The remote release workflow still verifies the published package.

### V3 publication and local installation

[Actions 36118415944](https://github.com/fansion314/pi/actions/runs/36118415944)
succeeded and published [Pi DNR 0.87.1-2](https://github.com/fansion314/pi/releases/tag/pi-dnr-v0.87.1-2).
The downloaded archive passed its SHA-256 check. Fresh extraction of the final
`pi-dnr-bin` package passed the structure/Node-API and both cache/sidecar smoke
tests with the released dnr 0.3.0. `paru -U` upgraded the local installation to
`pi-dnr-bin 0.87.1-2` together with dnr; `pi --version` reports 0.87.1 and
`pacman -Qkk pi-dnr-bin` reports 44 files with none altered. The installed DNP
matches the released payload. Existing user settings and sessions were preserved.

## 0.87.1 validation (2026-09-24)

Synchronized upstream v0.87.1 (`f07218c4d`), preserving DeepSeek Responses,
the separate completions provider and DNR format-v2 packaging. Fixed the
Copilot Opus 5.5 effort override when the live catalog already contains the model.

`npm run check` passed. The isolated offline suite found two failures: the
Copilot effort metadata and the retained development page's navigation entry.
Both were fixed; 132 targeted AI tests and the documentation test passed on rerun.
The other offline suites passed. macOS ARM64 package/Node-API checks and both
cache and sidecar runtime smoke tests passed. An isolated PTY accepted a prompt,
executed a faux-provider bash call, displayed the reply and exited successfully.
No paid model API was used. Linux packaging is validated by the release workflow.

## 0.86.1 validation (2026-09-21)

Synchronized upstream tag v0.86.1 (`13cbf77df`), retaining DeepSeek Responses,
the separate completions provider, and v2 native groups. Node's new compile-cache
launcher remains enabled for Node bundles; DNP uses an ESM launcher because dnr
0.2.0 does not export `enableCompileCache` from `node:module`.

`npm run check` passed. Targeted upstream regressions passed: 48 AI tests (4
conditional skips) and 37 coding-agent tests. The built v2 package passed its
structure/Node-API checks and both cold-cache and adjacent-installation smoke
tests. A real isolated PTY accepted input, ran a faux-provider bash call, showed
the reply and exited 0. No paid model request was made. macOS native execution
was not performed on this Linux host. Logs: `../dnr/dist/validation-pi-0.86.1/`.

## Historical v2 validation (2026-09-21)

On CachyOS x86_64, with dnc/dnr 0.2.0:

- Built a single DNP with both Linux x64 glibc and macOS ARM64 variants.
- `npm run check` passed. Package tests verified platform declarations, content
  hashes, read-only payload modes, preservation of an existing destination and
  real Node-API loading.
- Full offline smoke tests passed on both CEF and WebView, in cold/warm-cache
  and pre-extracted-sidecar modes. Repeated runs preserved native inode/mtime;
  sidecar mode did not create a user cache.
- An isolated source snapshot ran real prepare/build/check/package hooks via
  makepkg, using the standalone dnc. Local dependency lookup was explicitly
  bypassed; this does not claim a clean-container build.
- Both source and binary pacman packages preserve the `/usr/lib/pi` sidecar and
  the relative `/usr/bin/pi` symlink. The binary recipe rejected a wrong digest
  and a wrong checksum filename. The extracted package passed full runtime
  smoke tests without regenerating its sidecar.

macOS payloads were included and hash-checked, but were not executed on Linux.
No system package, user configuration or paid provider was changed. Evidence is
under `../dnr/dist/validation-v0.2.0/pi-*`; packaging CI runs on the next packaging
tag, separately from the dnr runtime release.

## Historical v1 validation (2026-09-18)

Local validation used the previously built and tested `pi-dnr` package. A wrong
checksum was rejected before extraction, the correct checksum passed, and a
real makepkg repackaging produced `pi-dnr-bin` with the expected dependencies,
provides and conflicts. Its `/usr/bin/pi` is byte-identical to the source package.
The generated `.SRCINFO`, workflow actionlint, Bash syntax checks and repository
`npm run check` passed. The old generated source snapshot was moved outside the
Pi checkout to avoid Biome treating its nested config as a project config.

No system package was installed during these checks. The remote tagged build
and release status is recorded in GitHub Actions; local repackaging alone does
not establish CI success.
