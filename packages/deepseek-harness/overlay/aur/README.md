# Arch Linux and CachyOS

English | [中文](README.zh.md)

## Summary

`dsh-electron` builds DeepSeek Harness from source; `dsh-electron-bin` installs the prebuilt application. Both target x86_64 and depend on Arch's `electron` package, without bundling Electron. These are community packages from [fansion314/packages](https://github.com/fansion314/packages), independent of upstream Desktop releases.

## Contents

- [Installation](#installation)
- [Release builds](#release-builds)
- [System packages](#system-packages)
- [Runtime](#runtime)

## Installation

The GitHub release contains one `.pkg.tar.zst` package that can be installed directly with `sudo pacman -U`. The `dsh-electron-bin` PKGBUILD downloads and verifies it, then makepkg repackages it for AUR installation. The source and binary recipes, including `.SRCINFO`, live in this directory. The workflow does not upload recipes to aur.archlinux.org.

The desktop command is `dsh-desktop`; the sidebar, window title, and application menu entry use DeepSeek Harness. The packages conflict with each other. Application updates use pacman or an AUR helper; the upstream in-app updater is inactive. System Electron reads its version-specific flags file first and falls back to `~/.config/electron-flags.conf` for display and Chromium options.

The package also installs `dsh`, using the same-version upstream CLI and bundled pnpm under Electron Node. `dsh web --host 127.0.0.1 --port 0 --no-open` serves the Web UI without opening a browser. The CLI retains the `headless`, `sdk`, `sdk-minimal`, and `acp` profiles, configuration export, and `dsh plugin --profile <name> ...` package management. Model requests still require provider credentials. CLI profiles and the reserved Desktop profile use their own configuration and plugin installations; window and tray integration belong to `dsh-desktop`.

## Release builds

The [workflow](https://github.com/fansion314/packages/blob/main/.github/workflows/release.yml) builds in an Arch container as an unprivileged user. It builds a pinned AUR recipe for `python-pptx`, which is absent from the official repositories; local installations need that AUR dependency or an equivalent package from a configured repository. An `deepseek-harness-v<upstream-version>-<pkgrel>` tag publishes the pacman package after runtime checks and packaging succeed. Manual runs create an Actions artifact without publishing. Both recipes must have matching versions and release numbers before tagging.

The build uses the repository's pinned pnpm, compiles the desktop and Web frontend, and deploys production JavaScript dependencies. Runtime interpreters and Python libraries come from pacman. Native-module, PTY, search, Host, frontend, Office-conversion, and Electron-window checks run before publication. Release recipes receive the actual package checksum and generated `.SRCINFO`; the checked-in binary recipe must match the published package before AUR submission.

## System packages

| Capability | Arch packages used at runtime |
|---|---|
| Desktop shell | `electron` |
| Host and JavaScript execution | Node supplied by `electron` |
| Plugin package operations | Bundled pnpm, run by Electron Node |
| Python interpreter | `python` |
| Data analysis | `python-numpy`, `python-pandas` |
| Word and PowerPoint authoring | `python-docx`, `python-pptx` |
| Excel authoring | `python-openpyxl`, `python-xlsxwriter` |
| Images and XML | `libvips`, `python-pillow`, `python-lxml` |
| Python supporting libraries | `python-dateutil`, `python-six`, `python-tzdata`, `python-typing_extensions`, `python-et-xmlfile` |
| File search | `ripgrep` |
| Native libraries and desktop integration | `glibc`, `gcc-libs`, `xdg-utils` |

Both recipes declare these dependencies. Existing installations are shared; package-size reduction does not remove the disk space required by missing system dependencies. Build-only tools include Git, Rust, Clang, CMake, Node.js, pnpm, node-gyp, and pkgconf.

The DSH-specific `libreoffice-kit-wasm` engine remains bundled: document preview and conversion use its JavaScript/worker API, not the system `libreoffice` command. The qualified npm graph, native Node bindings, and speech engine remain package-owned. Sharp is compiled against system libvips; its bundled libvips binaries are omitted. Other-platform PTY binaries, source maps, and TypeScript declarations are omitted using the existing Desktop file policy.

## Runtime

Resources live under `/usr/lib/dsh-electron`. The launcher uses Desktop's configurable resource paths and disables development tools. User profiles remain in the normal DSH home. Arch's `electron` package tracks its latest stable Electron release; after a major upgrade, verify the desktop and native modules before relying on the existing binary package.

The launcher uses Electron Node for Host, package operations, and the primary JavaScript runtime. It reads current system Python distribution versions and creates only metadata, links, and a Python launcher under `${XDG_CACHE_HOME:-~/.cache}/dsh-electron/runtimes`. Python aliases point directly to the versioned launcher, which executes `/usr/bin/python`; library paths link to `/usr/lib`. The Host uses these dependencies in place; it does not copy `/usr` or interpreters into `~/.dsh`. Metadata is refreshed after system versions change. Missing dependencies stop startup with an error. System Python follows Arch's externally managed environment policy; install additional system libraries with pacman or use a workspace virtual environment.

Linux keeps an application tray icon. Activating it restores the window; its context menu contains Open, About, Check for Updates, Reload Page, Restart App and Host, and Quit. Closing the workspace or welcome window hides it while tasks continue. A desktop environment with a system tray is required. If tray creation fails, closing exits instead. Linux tray activation follows the desktop environment and may require a double click.

The Arch build applies a small [compatibility patch](require-builtin.patch) to the deployed internal-module helper: an explicit `--expose-internals` uses Node’s builtin loader without probing Electron’s V8 memory layout. Workspace and upstream dependency sources remain unchanged. Runtime smoke checks exercise this helper and the rebuilt sharp addon under the installed Electron version.

Application JavaScript, frontend assets, and the dsh dependency tree are stored in `app.asar`. The adjacent `app.asar.unpacked` holds native libraries, executable helpers, and the complete Office package closure using the upstream Desktop exclusions. pnpm, its Node launcher, and Office skill resources stay in `runtime/` because external processes need real paths. ASAR is an archive, not compression; user profiles, plugin installation directories, and workspaces remain writable outside it. Packaging verifies the archived Host, native modules, frontend, plugin loading, PTY, search, package scripts, and Office conversion before release.
