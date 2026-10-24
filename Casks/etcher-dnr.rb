cask "etcher-dnr" do
  version "2.1.8-dnr.1,1"
  sha256 "39ad66b4d629406e7c00be2a16b189aa4ec020cecec4a165a648bf78fcdc7dfa"

  url "https://github.com/fansion314/etcher/releases/download/v2.1.8-dnr.1/etcher-dnr-2.1.8-1-macos-arm64-r1.tar.gz"
  name "balenaEtcher (dnr)"
  desc "Flash OS images using the shared dnr runtime"
  homepage "https://github.com/fansion314/etcher"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on formula: "fansion314/packages/dnr"

  app "balenaEtcher.app"

  preflight_steps do
    run "/usr/bin/codesign",
        args: ["--verify", "--deep", "--strict", "{{staged_path}}/balenaEtcher.app"]
  end

  postflight_steps do
    # Explicit policy of this personal tap: approve only this installed app.
    run "/usr/bin/xattr",
        args: ["-dr", "com.apple.quarantine", "{{appdir}}/balenaEtcher.app"]
  end

  caveats <<~EOS
    This app is ad-hoc signed and is not notarized by Apple.
    This tap removes the quarantine attribute from this app only after installation.
    macOS Gatekeeper settings and application data are left unchanged.
  EOS
end
