# Clash Momo Windows update mirror

This distributor mirrors only the Windows x64 Clash Momo client from public
`fansion314/momo` releases. Both installer and portable ZIP already contain the
exact paired Mihomomo core. Other Windows applications and standalone core
archives are outside this mirror.

CNB attachments use `windows-clash-momo-v<V>-<R>` releases in
`fansionia/packages`, with a separate ownership marker. Existing attachments
are reused and never replaced or deleted. The Ed25519 envelope is copied
unchanged from `clash-momo-windows-x64-update.json`; trusted public keys are in
`windows/keys.json`. Only the original momo release workflow holds the private
signing key. Windows programs remain unsigned by Authenticode.

The stable feed is:

`https://cnb.cool/fansionia/packages/-/git/raw/windows-updates/clash-momo/windows-x64/latest.json`

The isolated CNB `windows-updates` branch advances only after signature,
source digest, anonymous mirrored-download, portable-client and installed-client
verification succeeds. Failed candidates retain the previous feed. Publishing
uses a fast-forward push; it never touches CNB's Homebrew `main` branch or
pacman's persisted state. Historical attachments are retained indefinitely.

`sync-windows-clash-momo.yml` supports exact-tag/manual runs, release dispatches,
and a half-hour fallback schedule. `downstream.yml` accepts `platform=windows`
for this single project; `platform=all` includes it for Clash Momo. Other
projects cannot enter this mirror.

`CNB_MIRROR_TOKEN` needs Release read/write and code read/write on this CNB
repository, including permission to create/fast-forward `windows-updates`.
Branch write permission is checked before installer downloads or uploads.
Credentials and temporary upload URLs are never stored in Git or printed.

Native validation tests application startup, bundled-core identity, proxy
requests, persisted statistics, portable-directory relocation, reinstall and
default uninstall data retention. Interactive UAC acceptance/cancellation
requires a desktop test; an administrator runner does not provide that evidence.
