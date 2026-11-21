class PiDnr < Formula
  desc "Pi coding agent for the shared dnr runtime"
  homepage "https://github.com/fansion314/pi"
  url "https://github.com/fansion314/pi/releases/download/pi-dnr-v1.6.0-1/pi-dnr-1.6.0-1-macos-arm64-r1.tar.gz"
  version "1.6.0-1"
  revision 1
  sha256 "580367675145e3deefdf203c8845f1b7c9bd77cdcf10fbea0708cd8de330a6de"
  license "MIT"

  depends_on arch: :arm64
  depends_on macos: :sequoia
  depends_on "fansionia/tap/dnr"
  depends_on "fd"
  depends_on "ripgrep"

  def install
    system Formula["fansionia/tap/dnr"].opt_bin/"dnc", "install", "pi.dnp", libexec/"app"
    (bin/"pi").write <<~SH
      #!/bin/sh
      exec "#{Formula["fansionia/tap/dnr"].opt_bin}/dnr" "#{libexec}/app/pi.dnp" "$@"
    SH
  end

  test do
    ENV["PI_OFFLINE"] = "1"
    ENV["PI_TELEMETRY"] = "0"
    ENV["PI_CODING_AGENT_DIR"] = (testpath/"config").to_s
    assert_equal "1.6.0", shell_output("#{bin}/pi --version").strip
    assert_match "Usage:", shell_output("#{bin}/pi --help")
  end
end
