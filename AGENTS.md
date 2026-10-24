# Package maintenance

This repository is `fansion314/packages`, on `main`. Local directory names are not publication repository names.

- A project/version maintenance request includes source verification, compatible patch maintenance, commit/push, CI release, and applicable Homebrew/Arch synchronization. Continue until public assets and generated recipes are verified.
- Do not compile, rebuild native modules, run makepkg, or install applications locally. Local Git operations, metadata generation, static checks and build-free focused tests are allowed. Builds and installation verification belong in GitHub Actions. Supplemental remote validation follows the maintainer's cross-platform instructions and keeps sccache enabled.
- Do not create local ExecPlans unless explicitly requested. Keep changes minimal and preserve application identity, data paths, existing fork behavior and runtime integration.
- Homebrew is `fansion314/packages` with explicit URL `https://github.com/fansion314/packages.git`; keep only dnr, pi-dnr and etcher-dnr. Their source repositories remain external.
- paru's repository name is `fansionia`, URL `https://github.com/fansion314/packages.git`, path `aur/packages`. Documentation uses short install names such as `paru -S dnr-bin`.
- Internal project IDs are bitwarden, obsidian, motrix and deepseek-harness. Each `packages/<id>/manifest.json` owns version/pkgrel and pinned source metadata. Source and bin variants share `<id>-v<version>-<pkgrel>`.
- Preserve upstream lockfiles/toolchains. Existing Node projects use pnpm; do not migrate them to a new framework/tool merely to standardize tooling. Official Bitwarden/Obsidian payloads must not bundle Electron.
- Motrix/DSH source changes are ordered patches; additive packaging files belong in overlay. Never replace an existing upstream file through overlay. Validate patch preparation and preserve related regression tests. Patch conflicts require deliberate review, never silent fallback.
- `Formula/`, `Casks/`, `homebrew/releases/`, `aur/packages/` and `aur/state/` are generated. Fix generators, package templates or upstream sources, then let validated CI synchronization commit outputs.
- Use numeric version comparison and Arch vercmp; reject downgrades and same-version replacement. Filter monorepo Releases by project tag prefix, paginate, and never infer a project's current release from global latest.
- Keep public releases immutable. Build in CI, verify the exact tag/SHA, runtime ABI, asset checksums and GitHub digests, then publish. New bytes require a higher revision.
- Source/bin PKGBUILDs must work from a normal standalone download, without adjacent local source repositories. Retain provides/conflicts, licenses and runtime dependencies.
- CI synchronization uses this repository's GITHUB_TOKEN, preserves concurrent main commits, and commits only validated outputs. After an active release, invoke and follow the required sync rather than relying on its next schedule.
- Preserve existing user changes. Do not reset/stash other work, rewrite published history, move tags or force-push main. Stage only task paths; use Conventional Commits in English.
- Old source/distribution repositories and their automation are outside this migration's write scope. Do not modify, archive or delete them. Private/local-only applications are not distributed here.

Local checks: the three unittest discovery commands in README, shell syntax checks, and `git diff --check`. `homebrew/scripts/test-install.sh`, `scripts/build.sh` and Arch validation must run only on their intended disposable CI/native remote environments. Report actual completed evidence and disclose uncovered manual GUI/hardware behavior.
