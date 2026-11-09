# MyGo Music for Arch Linux

The pinned official release and exact source commit are recorded in
`manifest.json`. This is the native Go music client from `egoist/mygo-music`,
with no Electron or WebView runtime. It supports local music and plugins the
listener installs; this package bundles no Provider or plugin.

The interface-scale patch adds a persistent content scale to the General
settings page, with English and Simplified Chinese translations. The choices
are 75%, 90%, 100%, 110%, 125%, 150%, 175% and 200%. Changes apply immediately
to the main and settings windows and survive restarting the app. The default
100% follows the system display scale; invalid saved values reset to 100%.

The recipe preserves upstream's name and identity (`dev.egoist.music`),
production UI and `mygo-music://` links. It supplies no official self-update
feed: updates use pacman/paru so official binaries cannot replace the patched
build. Go dependencies remain pinned by upstream `go.mod`/`go.sum`. Version
validation evaluates `mygo.config.ts` with Node's TypeScript support and checks
its build configuration against the manifest; the separate website's
`package.json` is not the application version source.

Release tag: `mygo-music-v<version>-<pkgrel>`. `release.yml` publishes the signed
pacman package and verified source/bin recipe bundle. `downstream.yml`
validates the recipes and installs the signed package through the public
primary and CNB mirror endpoints.

```sh
sudo pacman -S mygo-music
paru -S mygo-music       # build the pinned source and apply the patches
paru -S mygo-music-bin   # use the verified CI binary instead
```

Choose either the source or binary variant; they conflict with each other.
MyGo Music can coexist with the old MyGo CloudMusic client. Existing
`mygo-cloudmusic` users install the new package explicitly: it does not replace
or provide the old package. The new upstream identity uses a separate data
directory and does not read or migrate old accounts, playlists, caches or
settings. The old package leaves the current maintenance and distribution
lists, while historical Release downloads, installed applications and user
data remain intact.

Linux desktop integration uses `dev.egoist.music` for the desktop entry,
X11 WM_CLASS and Wayland app_id, and `mygo-music` for the themed icon. Standard
hicolor sizes (16–512 px) and a pixmaps fallback are generated from upstream's
PNG during CI builds. The smoke check uses KDE's real icon loader and checks
the identity and actual _NET_WM_ICON pixels of the main and settings windows.

Arch CI runs the full internal Go suite, the scaling interaction test five
times, translation checks, desktop-file validation and an X11 launch smoke
test. Physical-device audio and manual desktop acceptance remain separate
from these automated checks.
