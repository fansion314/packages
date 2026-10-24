class Dnr < Formula
  desc "Shared Deno runtime and application packager"
  homepage "https://github.com/fansion314/dnr"
  url "https://github.com/fansion314/dnr/releases/download/v0.5.5/dnr-0.5.5-macos-arm64-r1.tar.gz"
  version "0.5.5"
  revision 1
  sha256 "7439aa361a4bbfcc10309787b95efcd65de5d76199085028fbc8ac7956209ffe"
  license "MIT"

  depends_on arch: :arm64
  depends_on macos: :sequoia

  def install
    bin.install "bin/dnr", "bin/dnc"
    doc.install "README.md", "README.zh.md", "THIRD_PARTY.md", "docs"
    (pkgshare/"licenses").install Dir["licenses/*"]
  end

  test do
    assert_match "dnr #{version}", shell_output("#{bin}/dnr --version")
    assert_match "dnc #{version}", shell_output("#{bin}/dnc --version")
    (testpath/"app/main.ts").write <<~TS
      const value: string = Deno.readTextFileSync(new URL("./data.txt", import.meta.url));
      console.log(`${value}:${Deno.args[0]}`);
    TS
    (testpath/"app/data.txt").write "homebrew"
    system bin/"dnc", "app", "--entry", "main.ts", "--app-id", "dev.dnr.homebrew.test", "-o", "app.dnp"
    assert_equal "homebrew:ok", shell_output("#{bin}/dnr app.dnp ok").strip
  end
end
