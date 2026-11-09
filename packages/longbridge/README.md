# Longbridge Linux x86_64

Repackages the official stable Linux tarball from the CDN used by
<https://longbridge.com/desktop/install.sh>. The exact versioned asset and its
vendor-published SHA-256 are pinned in `manifest.json`; no vendor installer is run.
The executable is preserved byte for byte. This is proprietary vendor software,
not an open-source build; the published Linux tarball/deb contains no license file.
Vendor product and terms: <https://longbridge.com/desktop>.

The pacman package is `longbridge`. The paru recipes are `longbridge` (repackage
the vendor tarball) and `longbridge-bin` (repackage our signed Arch archive).
They are mutually exclusive. Launch using `longbridge-desktop`, also the official
deb's command, to leave the `longbridge` command available for the separate CLI.

The official `com.longbridge.app.desktop` identity and configuration paths are
preserved. No user data is migrated, overwritten or removed. The executable and
its `.app` layout live under `/usr/lib/longbridge/`; desktop entries and icons are
installed under `/usr/share`. GTK3 and WebKitGTK 4.1 are system dependencies.
Although the installer advertises glibc 2.35, version 1.1.0 imports GLIBC_2.39;
the package declares the actual minimum. A working GPU driver is needed for
rendering; CI uses Mesa's software Vulkan driver under Xvfb.

Updates are managed by pacman/paru. Turn off automatic updates in
Settings > General > Software Update; do not run the vendor's per-user installer
to update this system package. Its uninstaller only targets per-user installs.

CI verifies archive checksums, desktop entries/icons, dynamic library resolution,
unchanged executable bytes, a visible application window in an isolated profile,
and the generated `-bin` recipe. Signed repository publication also installs and
checks the package through the candidate, primary and CNB mirror endpoints.
These checks do not exercise account login or trading.
