class Mihomomo < Formula
  desc "Mihomomo proxy core for Clash Momo"
  homepage "https://github.com/fansion314/momo"
  url "https://github.com/fansion314/momo/releases/download/mihomomo-v1.19.33-1/mihomomo-1.19.33-1-macos-arm64-r1.tar.gz"
  version "1.19.33-1"
  revision 1
  sha256 "9403935d16952a4e0b2b8e10cf46aea7487ece3de9cea2201e70ef116d3223b7"
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
    assert_match "1.19.33", shell_output("#{bin}/mihomomo -v")
    capabilities = JSON.parse(shell_output("#{bin}/mihomomo --momo-capabilities"))
    assert_equal 1, capabilities["protocol"]
    assert_equal true, capabilities["managedMode"]
  end
end
