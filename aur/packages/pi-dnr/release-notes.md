# Pi DNR 1.5.0-1

Synchronizes the DNR fork with upstream Pi v1.5.0. Use dnr 0.4.0 or newer.

- Adds extension update changelogs, faster streaming, custom self-update
  commands, and the upstream GPT-6.1 Terra catalog.
- Uses pi-schema for tool argument validation. Extensions using TypeBox-only
  validation features must follow the upstream migration guidance.
- Preserves DeepSeek Responses (`deepseek`) and Chat Completions
  (`deepseek-completions`) using `DEEPSEEK_API_KEY`.
- Keeps Azure Foundry DeepSeek on Chat Completions with Azure-specific thinking
  levels, alongside the separate DeepSeek Responses provider.
- Retains DNP v4 with Linux x64 and macOS ARM64 native helpers, the DNR ESM
  launcher, schemas, resources, and the self-contained Codemode worker.

See the upstream 1.5.0 changelog for the complete changes.

GitHub Actions builds the Arch package, cross-platform `pi.dnp`, and macOS ARM64
Homebrew archive. The Arch package installs verified Linux groups under
`/usr/lib/pi`; `/usr/bin/pi` is a relative symlink. Runtime installation remains
separate. Checksums and build records accompany the release assets.

The DNR-only tag is `pi-dnr-v1.5.0-1`; upstream tags and npm releases are unchanged.
