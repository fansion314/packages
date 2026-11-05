# Pacman publication recovery — 2026-11-05

The primary repository and CNB mirror are updated. All candidate and public
pacman installation checks passed; signature verification was retained.

## Causes and repairs

1. Publication kept resuming pending snapshot
   `48cb9e9f2f641871b1da33ea80dc445f` before discovering newer releases.
   Old external package URLs, including Denial 0.6.1, had become HTTP 404.
   Commit `6e5e7b155844eed00ee271cd0062637ae7ae9b36` recovers definitive
   404/410 URLs from previously verified CNB archives only when the original
   package and signature have exact snapshot receipts and immutable object
   ledger entries. Static routes preserve original bytes and signatures;
   manifests are not rewritten. Retained primary databases protect those objects.
2. Fresh discovery then encountered Warp's signing-subkey rotation. The
   primary key was unchanged, but the reviewed client keyring lacked the new
   signing subkey. Commit `9d1a19249ddd920c79c996be926876187896c2dc`
   imports the official public-key update, checks the new binding and old
   revocation, rejects revoked signatures, and requires the updated keyring to
   be published before discovery uses it.

Official rotation announcement:
<https://www.warp.dev/blog/updated-gpg-signing-key-for-warp-linux-releases>

No packages were rebuilt or re-signed to work around upstream removal. No
signature or installation checks were skipped. Unrelated network errors do
not permanently pin routes, and missing recovery proof fails closed.

## Validation and publication

- Local targeted checks: 47 Python tests passed with one native-only skip;
  four Node routing tests passed. Generated public keyring consistency passed.
- Full CI: [41960826938](https://github.com/fansion314/packages/actions/runs/41960826938).
- Previous pending transaction recovered:
  [41955549256](https://github.com/fansion314/packages/actions/runs/41955549256).
- Keyring release:
  [fansionia-keyring-v20261105-1](https://github.com/fansion314/packages/releases/tag/fansionia-keyring-v20261105-1).
- Final publication:
  [41961261623](https://github.com/fansion314/packages/actions/runs/41961261623).
  Primary and mirror candidate/public installation, Worker deployment, and
  retention all succeeded.
- Independently downloaded primary and mirror databases were GPG-verified and
  had identical SHA-256:
  `9af28b01188e1cc784999f79073bf57cf580a759226e3b085a3ec58dea5a2339`.
- Active snapshot: `6f9e6b38d9c45b38f0bb8a3315f6fb70` on both public entrances.
  Retention preserved 32 primary snapshots and two successful mirror snapshots.

Verified database versions:

| Package | Version |
| --- | --- |
| clash-momo | 2.0.4-8 |
| mihomomo | 1.19.33-5 |
| fansionia-keyring | 20261105-1 |
| denial | 0.6.2-1 |
| denial-flutter-engine | 1:0.6.2-1 |
| denial-plugin-manager | 0.6.2-1 |
| Warp / Oz | v0.2026.11.03.17.08.stable_00-1 |

## Existing client upgrade

Update the keyring first so the subsequent full upgrade can verify the new
upstream signing subkey:

```sh
sudo pacman -Syy fansionia/fansionia-keyring
sudo pacman -Su
```
