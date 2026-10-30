class Mihomomo < Formula
  desc "Mihomomo proxy core for Clash Momo"
  homepage "https://github.com/fansion314/momo"
  url "https://github.com/fansion314/momo/releases/download/mihomomo-v1.19.33-2/mihomomo-1.19.33-2-macos-arm64-r2.tar.gz"
  version "1.19.33-2"
  revision 2
  sha256 "eae84973071bb4579f915a3a42b255e637f2c51c8bb1c899a8d3dbac2ab5547a"
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
