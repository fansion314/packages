# Pi DNR 1.5.2-1

Synchronizes the DNR fork with upstream Pi v1.5.2 at
`b4afdddf44e059c67ccf5097e5317d913521b470`. Use dnr 0.4.0 or newer.

- Offers Continue, Fork, or Cancel when a session's original working directory
  no longer exists. Fork preserves a copy in the current directory for later resumes.
- Fixes duplicate session files left by failed imports and updates the Claude Code
  version reported by Anthropic OAuth requests.
- Preserves DeepSeek Responses (`deepseek`) and Chat Completions
  (`deepseek-completions`) using `DEEPSEEK_API_KEY`.
- Keeps Azure Foundry DeepSeek on Chat Completions with Azure-specific thinking
  levels, alongside the separate DeepSeek Responses provider.
- Retains DNP v4 with Linux x64 and macOS ARM64 native helpers, the DNR ESM
  launcher, schemas, resources, and the self-contained Codemode worker.

See the upstream 1.5.2 changelog for the complete changes.

GitHub Actions builds the Arch package, cross-platform `pi.dnp`, and macOS ARM64
Homebrew archive. The Arch package installs verified Linux groups under
`/usr/lib/pi`; `/usr/bin/pi` is a relative symlink. Runtime installation remains
separate. Checksums, signatures, and build records accompany the release assets.

The DNR-only tag is `pi-dnr-v1.5.2-1`; upstream tags and npm releases are unchanged.
