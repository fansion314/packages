## Motrix 2.4.5 upgrade notes

Motrix 2.4.5 enables recoverable download handoffs from paired browser
extensions by default. Browser Extension 0.1.25 can recover the existing task
identity after a lost reply. Set `MOTRIX_DOWNLOAD_HANDOFF=0` before launching
Desktop to stop accepting new handoffs while allowing prepared operations to
finish. Existing extensions retain their original submission method.

This update also includes the 2.4.4 fixes for engine stalls when adding large
torrents, visible submission errors, and task recovery after uncertain creation.

This package uses system Electron and bundles the pinned Motrix aria2
1.37.0-motrix.25 engine. Native modules are rebuilt and tested against the
system Electron installed in the Arch build environment; its actual version is
recorded in build-info.json. No Electron runtime is bundled.

Back up your profile and download files before upgrading. The bundled engine
uses SQLite schema 6. When upgrading an older engine database, retain its
complete pre-upgrade backup: older engines cannot open schema 6. Stop all
engines before restoring a verified backup to a separate path for a downgrade.
Do not reset or delete the upgraded database as a substitute for recovery.

Users migrating from Motrix v1 should follow the
[upstream migration guide](https://github.com/agalwood/Motrix/blob/v2.4.5/docs/legacy-migration.md)
and retain their original profile and engine database backups.
