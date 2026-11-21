# Pi DNR 1.6.0-1

Synchronizes the DNR fork with upstream Pi v1.6.0 at
`faac585884ae2c013a6b1400f3e9e77f10b34bac`. Use dnr 0.4.0 or newer.

- Adds GPT-6.2 Astra and Sol, updated Qwen gateways, and upstream terminal,
  session, tool schema, and provider retry fixes.
- Updates undici to 8.12.4 with the upstream security fixes for redirect handling,
  cache replay, credentials, and integrity verification.
- Extension render output is now readonly. Extensions that mutate returned arrays
  must copy them first.
- Preserves DeepSeek Responses (`deepseek`) and Chat Completions
  (`deepseek-completions`) using `DEEPSEEK_API_KEY`.
- Keeps Azure Foundry DeepSeek on Chat Completions with Azure-specific thinking
  levels, alongside the separate DeepSeek Responses provider.
- Retains DNP v4 with Linux x64 and macOS ARM64 native helpers, the DNR ESM
  launcher, schemas, resources, and the self-contained Codemode worker.

See the upstream 1.6.0 changelog for the complete changes.

GitHub Actions builds the Arch package, cross-platform `pi.dnp`, and macOS ARM64
Homebrew archive. The Arch package installs verified Linux groups under
`/usr/lib/pi`; `/usr/bin/pi` is a relative symlink. Runtime installation remains
separate. Checksums, signatures, and build records accompany the release assets.

The Arch build records `Fansionia Packages <packages@fansionia.world>` as its
packager and checks the value before publication.

The DNR-only tag is `pi-dnr-v1.6.0-1`.
