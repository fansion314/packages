# Signed pacman distribution

`sources.json` is the explicit allowlist of public repositories, tag families and
package identities. Only already-built `.pkg.tar.zst` assets are indexed; the
repository job never rebuilds or repackages applications. Runtime dependencies
absent from Arch official repositories are maintained explicitly under `support/`.
For `clash-momo`, a version-only tag (`clash-momo-vX.Y.Z`) denotes package
revision 1; a suffixed tag (`clash-momo-vX.Y.Z-N`) pins revision N.

## Publishing

Each source repository signs packages in its publication job, after build and
quality checks. `packages` signs its own application/support packages and the
database. Each repository owns a distinct signing subkey of the public identity
in `keys/`. The primary private key is never uploaded to Actions. Existing public
package bytes may receive a missing `.sig` through the manual backfill workflow.
Existing packages and signatures are reused only after exact digest verification.
Each publication resolves the maintenance commit once, then pins snapshot,
candidate testing and Worker deployment to that same commit. Concurrent recipe
auto-commits cannot mix generator or Worker code within a publication.

`publish-pacman.yml` checks the newest matching Release of every allowlisted
project. An incomplete newest Release fails the candidate instead of falling back
silently. GitHub digests, downloaded SHA-256, package metadata and the expected
source signing subkey must all agree. Arch `vercmp` rejects downgrades, and an
unchanged package version cannot acquire different bytes or a different URL.

The generated `pacman-pages` branch stores complete snapshots and their ordered
index. It contains metadata and public keys, not application archives. Pages is
deployed from an Actions artifact, with real files in place of repo-add symlinks.
At most 32 snapshot directories are served, including a staged candidate; the
active snapshot is never evicted. This bounds compatibility for old cached
databases to the retained snapshots. Historical Release assets are not deleted.

After Pages download/signature checks, a disposable Arch container runs the actual
candidate Worker through a Node HTTP adapter and installs the packages with strict
pacman signature checking. Only then does CI publish two embedded Worker versions:

1. Preparation: all retained/new package mappings, with the old database selected.
2. Activation: the same mappings, with the new database selected.

The first publication selects the first verified snapshot in both phases. The
Worker does not fetch configuration or package bodies; it only returns exact 302
locations. Deployment completion plus HTTP phase checks gate activation. These
checks do not establish a globally atomic transaction across independent requests.

## Failure recovery

Before activation, a failure leaves the previous database selected. Retry the same
workflow: existing snapshot inputs reuse the same signed database bytes. Actual
Worker `/status.json`, rather than a speculative Git commit, determines the active
snapshot. The generated branch is persisted before Pages/Worker deployment, so a
retry can recover every already-published snapshot.

If activation succeeded but the public-domain installation check failed, rerun
the failed job after correcting the cause. A new manual publication also repeats
the public installation check when its snapshot is already active; unchanged
scheduled checks skip installation and deployment.

To roll back, generate a new Worker version selecting the previous retained
snapshot while keeping the full current package mappings. Do not blindly restore
an old Worker version that lacks packages referenced by newer cached databases.
Never overwrite a source asset or move a released tag to fix a publication.

Initialize the Worker once with `initialize-worker.yml`, then bind
`packages.fansionia.world` as its Custom Domain. CI uses version upload/deploy, so
routine publication does not alter the domain binding. Its account token only
requires Workers script deployment access; domain configuration is separate.
The package hostname must allow non-browser downloads. Exclude it from any
site-wide browser-challenge rule and Browser Integrity Check; pacman cannot
solve JavaScript challenges. Free Bot Fight Mode cannot be skipped for one
hostname. If it challenges repository clients, the zone owner must disable it
or select a plan with scoped bot exceptions before enabling this public service.

## Signing-key operations

The initial primary key expires after five years; repository signing subkeys after
two years. Signing fails 45 days before expiry to require deliberate renewal. Keep
the encrypted primary-key backup and revocation certificate on offline storage;
the local setup records its recovery passphrase in the macOS login Keychain under
service `world.fansionia.packages.signing`, account `primary-key-recovery`.

Renew/certify keys with the offline primary key, publish updated public material
and a higher `fansionia-keyring` version, and update only the relevant source's
Actions secrets. For a compromised subkey, revoke that subkey with the primary,
publish the updated keyring, and issue a replacement subkey. Never upload the
primary secret or copy a repository subkey into another source repository.

## Local checks

```sh
python3 -m unittest discover -s arch/tests -v
node --test arch/tests/*.test.mjs
git diff --check
```

`test-install.sh`, support builds and Worker deployment run only in CI. The
scheduled downstream workflow checks for updates every 15 minutes; unchanged
pacman inputs skip download, signing and deployment. Source releases dispatch it
immediately, with schedules covering missed notifications. Notification restores
`downstream.yml` only if GitHub marked it `disabled_inactivity`; an intentional
manual disable remains respected.
