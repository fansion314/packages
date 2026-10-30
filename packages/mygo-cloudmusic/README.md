# MyGo 云音乐 for Arch Linux

The pinned upstream release is recorded in `manifest.json`. The interface feature
patch is `patches/0001-add-interface-scale-setting.patch`: a persistent
75–200% content scale in Settings, applied immediately to the main and settings
windows. A separate test-only patch limits the upstream macOS notch greeting
tests to macOS, matching the implementation’s existing platform guard. The default remains 100% of the system display scale. The upstream
application name, ID (`dev.egoist.cloudmusic`) and data directories are preserved.

The native Go application is built on Arch CI, without a WebView or Electron.
The recipe links the upstream app metadata but no upstream self-update feed;
updates are distributed through pacman/paru so official binaries cannot replace
the patched build. Go dependencies remain pinned by upstream go.mod/go.sum.
The existing root package.json describes the separate website, not the app.

Release tag: `mygo-cloudmusic-v<version>-<pkgrel>`. `release.yml` publishes the
signed pacman package and verified source/bin recipe bundle. `downstream.yml`
validates the recipes and installs the signed package from the public domain.

```sh
sudo pacman -S mygo-cloudmusic
paru -S mygo-cloudmusic       # build the pinned source and apply this patch
paru -S mygo-cloudmusic-bin   # use the verified CI binary instead
```

Both paru variants conflict with one another. Manual desktop/audio acceptance is
separate from CI's Go tests, scaling interaction test and X11 launch smoke test.

Linux desktop integration is maintained by the third patch and additive overlay:
GTK uses the existing `dev.egoist.cloudmusic` desktop identity on X11/Wayland and
inherits the themed icon in every window. Standard hicolor sizes (16–512 px) and
a pixmaps fallback are generated from the original upstream PNG during CI builds.
The package smoke check uses KDE's real icon loader and checks WM_CLASS and the
actual _NET_WM_ICON pixels of the main and Settings windows.
