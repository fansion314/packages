class Mihomomo < Formula
  desc "Mihomomo proxy core for Clash Momo"
  homepage "https://github.com/fansion314/momo"
  url "https://github.com/fansion314/momo/releases/download/mihomomo-v1.19.34-1/mihomomo-1.19.34-1-macos-arm64-r6.tar.gz"
  version "1.19.34-1"
  revision 6
  sha256 "171085c67a8527e46d55fd3c750606c19b230baa2fc6ca2734081f9dd77c64be"
  license "GPL-3.0-only"

  depends_on arch: :arm64
  depends_on macos: :sequoia

  def install
    bin.install "bin/mihomomo"
    (share/"mihomomo").install "share/mihomomo/manifest.json"
    pkgshare.install "LICENSE", "README.md"
  end

  test do
    require "json"
    assert_match "1.19.34", shell_output("#{bin}/mihomomo -v")
    capabilities = JSON.parse(shell_output("#{bin}/mihomomo --momo-capabilities"))
    assert_equal 1, capabilities["protocol"]
    assert_equal true, capabilities["managedMode"]
  end
end
