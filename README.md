# fansion314/packages

Homebrew definitions, a signed pacman repository, a paru PKGBUILD repository, and small application packaging patches maintained together. Upstream applications keep their existing names, configuration directories and data identities.

## Homebrew

Apple Silicon, macOS 15 or newer:

```sh
brew tap fansion314/packages https://github.com/fansion314/packages.git
brew install fansion314/packages/dnr fansion314/packages/pi-dnr
brew install --cask fansion314/packages/etcher-dnr
brew update
brew upgrade
```

The explicit tap URL is required because this repository is named `packages`, without a `homebrew-` prefix. After trusting the selected definitions, short package names can also be used. Pi and Etcher share the `dnr` runtime. Etcher is ad-hoc signed, not Apple-notarized; its cask verifies the signature and removes quarantine only from the installed app.

## Arch Linux / CachyOS

### Signed binary repository

Packages are downloaded directly from their original GitHub Releases, with no
client-side compilation or repackaging. Each application/backend has one package
name, such as `dnr`, `pi-dnr` or `motrix-electron`; the binary repository has no
separate `-bin` variants. It supports x86_64, including architecture-independent
packages such as `python-pptx`.

First download the public key and check its complete fingerprint against this
repository before granting trust:

```sh
curl -fLO https://packages.fansionia.world/keys/fansionia.asc
gpg --show-keys --with-fingerprint fansionia.asc
```

Expected primary fingerprint: **338A EAB6 4ECF 2EF6 9AAF 3EEF DF31 7480 72E5 B972**.
The same public key is tracked under [`arch/keys/`](arch/keys/).

```sh
sudo pacman-key --add fansionia.asc
sudo pacman-key --lsign-key 338AEAB64ECF2EF69AAF3EEFDF31748072E5B972
```

Append this section to `/etc/pacman.conf`, preserving existing repositories:

```ini
[fansionia]
SigLevel = Required TrustedOnly
Server = https://packages.fansionia.world/$arch
```

```sh
sudo pacman -Syu fansionia-keyring
sudo pacman -S dnr dnc pi-dnr etcher-dnr
sudo pacman -S motrix-electron dsh-electron bitwarden-electron obsidian-electron
```

DSH's `python-pptx` dependency is provided here; pacman installs its other declared
dependencies from the configured official repositories. Existing `-bin` installs
can be replaced by explicitly installing the corresponding package above and
reviewing pacman's conflict-removal prompt. Other DNR backend variants are
alternatives to `dnr`, not parallel installations.

Packages and databases require trusted signatures. GitHub Pages stores immutable
database snapshots; a Cloudflare Worker embeds all download mappings and selects
the active snapshot. The most recent 32 snapshots remain available. See
[`arch/README.md`](arch/README.md) for publication, recovery and key rotation.

### paru PKGBUILD repository

Configure paru with the section below. When migrating, replace the previous PKGBUILD repository entry for these packages and preserve unrelated settings. If creating a user configuration, preserve system settings with `Include = /etc/paru.conf`. If `Mode` is explicitly set, include `pkgbuilds`.

```ini
[fansionia]
Url = https://github.com/fansion314/packages.git
Path = aur/packages
```

```sh
paru -Syu
paru -S dnr-bin pi-dnr-bin etcher-dnr-bin
paru -S motrix-electron-bin dsh-electron-bin
paru -S bitwarden-electron-bin obsidian-electron-bin
```

The optional `fansionia/` prefix selects this repository explicitly. Keep paru's normal recipe review enabled. `-bin` recipes download verified prebuilt application payloads and still use makepkg to create a pacman package. Release `.pkg.tar.zst` assets can also be installed directly with `pacman -U`.

The 20 recipes cover dnr/dnc and its backend variants, Pi, Etcher, Motrix, DeepSeek Harness, Bitwarden and Obsidian. Source and binary variants are alternatives, not parallel installations. Bitwarden and Obsidian source recipes repackage official applications rather than compiling the upstream application.

## Sources and releases

- `Formula/` and `Casks/` are generated Homebrew definitions. Their generator, templates and verified release records are in `homebrew/`.
- `aur/packages/` and `aur/state/` are generated; edit the source recipes or synchronization logic rather than maintaining a downstream fork.
- `packages/<id>/manifest.json` fixes the application version, packaging revision and upstream commit where applicable. Recipe templates are in `recipes/`; Motrix and DeepSeek Harness additionally have ordered `patches/series` and additive packaging files in `overlay/`.
- dnr, Pi and Etcher continue to publish from their external repositories. The four internal projects publish tags named `<id>-v<version>-<pkgrel>` in this repository. Each application's source and binary recipes share one Release.

Builds fetch the exact upstream commit, apply patches without fallback, and use the upstream lockfile. Standalone source PKGBUILDs fetch both upstream and the packaging tag. `imports.json` records the migration snapshots; old histories and releases remain in their original repositories.

CI builds on native Arch x86_64 as an unprivileged user, runs package-specific quality/smoke checks (including loading Bitwarden/Obsidian native addons with system Electron), and verifies binary repackaging before publishing. Every Release contains a pacman package, recipe bundle, build record and SHA-256 manifest. Public tags and assets are immutable; a changed package requires a higher `pkgrel`.

Source releases notify the applicable Homebrew/Arch distribution workflows immediately. A combined check runs every 15 minutes, in addition to the existing Homebrew and paru schedules, subject to GitHub scheduling delays. Candidates are committed only after download verification and platform-specific validation; unchanged pacman inputs produce no deployment. Homebrew installs are tested only on disposable macOS CI runners. CI smoke tests do not establish manual GUI or physical-device acceptance.

## Maintenance checks

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s homebrew/scripts -p 'test_*.py' -v
python3 -m unittest discover -s aur/tests -v
python3 -m unittest discover -s arch/tests -v
node --test arch/tests/*.test.mjs
python3 scripts/package.py recipes motrix .cache/candidate-recipes
```

Application builds, makepkg and installation tests belong in CI, not on the maintainer's local machine. Update `manifest.json`, source templates and patch series together, validate the branch CI, then push the matching application tag. To retry an existing tag with corrected release automation, dispatch the release workflow from main and supply release_tag; application sources remain fixed to the supplied tag. A failed build may be retried; never move a published tag or replace public bytes.
