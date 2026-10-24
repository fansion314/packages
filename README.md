# fansion314/packages

Homebrew definitions, a paru PKGBUILD repository, and small application packaging patches maintained together. Upstream applications keep their existing names, configuration directories and data identities.

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

Append this section to your existing paru configuration. If creating a user configuration, preserve system settings with `Include = /etc/paru.conf`. If `Mode` is explicitly set, include `pkgbuilds`.

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

CI builds on native Arch x86_64 as an unprivileged user, runs package-specific quality/smoke checks, and verifies binary repackaging before publishing. Every Release contains a pacman package, recipe bundle, build record and SHA-256 manifest. Public tags and assets are immutable; a changed package requires a higher `pkgrel`.

Homebrew synchronization runs at minutes 17 and 47, and Arch synchronization at minute 23, subject to GitHub scheduling delays. Both support manual dispatch. Internal releases call Arch synchronization directly after publication. Candidates are committed only after download verification and platform-specific validation; no-change runs produce no commit. Homebrew installs are tested only on disposable macOS CI runners. CI smoke tests do not establish manual GUI or physical-device acceptance.

## Maintenance checks

```sh
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s homebrew/scripts -p 'test_*.py' -v
python3 -m unittest discover -s aur/tests -v
python3 scripts/package.py recipes motrix .cache/candidate-recipes
```

Application builds, makepkg and installation tests belong in CI, not on the maintainer's local machine. Update `manifest.json`, source templates and patch series together, validate the branch CI, then push the matching application tag. Manual release dispatch must select that same existing tag as its workflow ref. A failed build may be retried; never move a published tag or replace public bytes.
