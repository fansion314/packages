# Pi DNR 1.5.1-1

Synchronizes the DNR fork with upstream Pi v1.5.1 at
`dd30101cfc5b0609411dd80b6f93adbc14db14cf`. Use dnr 0.4.0 or newer.

- Adds shell login/logout (`pi auth login` / `pi auth logout`), idle prompt cache
  warming, Anthropic message threads, richer Mermaid diagrams, GitHub Copilot
  classifiers, and package update summaries.
- Preserves DeepSeek Responses (`deepseek`) and Chat Completions
  (`deepseek-completions`) using `DEEPSEEK_API_KEY`.
- Keeps Azure Foundry DeepSeek on Chat Completions with Azure-specific thinking
  levels, alongside the separate DeepSeek Responses provider.
- Retains DNP v4 with Linux x64 and macOS ARM64 native helpers, the DNR ESM
  launcher, schemas, resources, and the self-contained Codemode worker.

## Compatibility

- Custom `GrepOperations.readFile` callbacks are no longer called for context
  lines. Override grep's `execute()` when searching a remote system.
- OpenAI-compatible requests omit `tools` when tools are disabled, including
  conversations with tool history. Older LiteLLM gateways that require the field
  can set `compat.requiresToolsWithToolHistory: true` for the affected model.

See the upstream 1.5.1 changelog for the complete changes.

GitHub Actions builds the Arch package, cross-platform `pi.dnp`, and macOS ARM64
Homebrew archive. The Arch package installs verified Linux groups under
`/usr/lib/pi`; `/usr/bin/pi` is a relative symlink. Runtime installation remains
separate. Checksums, signatures, and build records accompany the release assets.

The DNR-only tag is `pi-dnr-v1.5.1-1`; upstream tags and npm releases are unchanged.
