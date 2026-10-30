class Mihomomo < Formula
  desc "Mihomomo proxy core for Clash Momo"
  homepage "https://github.com/fansion314/momo"
  url "https://github.com/fansion314/momo/releases/download/mihomomo-v1.19.33-3/mihomomo-1.19.33-3-macos-arm64-r3.tar.gz"
  version "1.19.33-3"
  revision 3
  sha256 "71c04c5f788bd70e6b8797413fa8d0250e96d0f89dbbcd6388e2d5d50056d5e7"
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
