class Mihomomo < Formula
  desc "Mihomomo proxy core for Clash Momo"
  homepage "https://github.com/fansion314/momo"
  url "https://github.com/fansion314/momo/releases/download/mihomomo-v1.19.33-5/mihomomo-1.19.33-5-macos-arm64-r5.tar.gz"
  version "1.19.33-5"
  revision 5
  sha256 "48af6c6fd1f0de5ac65dcaef508a2684a010ddda01ee4f2d29e10812d6d7c613"
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
