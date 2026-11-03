cask "clash-momo" do
  version "2.0.4-5,5"
  sha256 "d81d4dda3273757fd804a2aef240e23f9f09705d6a6b997e568120d569d74a4b"

  url "https://github.com/fansion314/momo/releases/download/clash-momo-v2.0.4-5/clash-momo-2.0.4-5-macos-arm64-r5.tar.gz"
  name "Clash Momo"
  desc "Graphical proxy client using Mihomomo"
  homepage "https://github.com/fansion314/momo"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on formula: "fansionia/tap/mihomomo"

  app "Clash Momo.app"

  preflight_steps do
    run "/usr/bin/codesign",
        args: ["--verify", "--deep", "--strict", "{{staged_path}}/Clash Momo.app"]
    run "/bin/sh",
        args: ["-c", '/usr/bin/codesign -dv "$1" 2>&1 | /usr/bin/grep -Fx Signature=adhoc', "sh", "{{staged_path}}/Clash Momo.app"]
  end

  postflight_steps do
    run "/usr/bin/xattr",
        args: ["-dr", "com.apple.quarantine", "{{appdir}}/Clash Momo.app"]
  end

  caveats <<~EOS
    This app is ad-hoc signed and is not notarized by Apple.
    This tap removes quarantine from the installed app after signature verification.
  EOS
end
