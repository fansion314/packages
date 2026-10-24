# Download this repository's preprocessed system-Electron application archive.
# No upstream DEB extraction, ASAR processing, or application build is performed.
pkgname=bitwarden-electron-bin
pkgver=2026.10.0
pkgrel=1
pkgdesc='Bitwarden using system Electron (prebuilt application)'
arch=('x86_64')
url='https://github.com/fansion314/bitwarden'
license=('GPL-3.0-only')
depends=('electron' 'bash' 'glibc' 'libgcc' 'hicolor-icon-theme'
         'libnotify' 'org.freedesktop.secrets' 'libxtst' 'libxss' 'libnss_nis')
provides=("bitwarden=$pkgver" "bitwarden-electron=$pkgver")
conflicts=('bitwarden' 'bitwarden-bin' 'bitwarden-electron')
options=('!strip' '!debug')
# Independently pin the published input: pkgrel can change without rebuilding it.
_release='2026.10.0-1'
_archive='bitwarden-electron-2026.10.0-1-x86_64.pkg.tar.zst'
source=("https://github.com/fansion314/bitwarden/releases/download/v${_release}/${_archive}")
noextract=("$_archive")
sha256sums=('8e37de6a26408437c442424e321dcba5ff36b68e7f854f3c34affc15b11297f1')

package() {
  # The release asset can also be installed directly with pacman -U.
  bsdtar -xf "$srcdir/$_archive" -C "$pkgdir" usr
}
