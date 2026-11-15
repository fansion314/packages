This follows the upstream 0.2.2 release-candidate channel. It preserves system Electron,
Linux tray behavior, persistent interface scale, window state, and system-managed
workspace dependencies.

Upstream rc.3 adds the optional experimental DeepSeek chat import plugin and fixes
Windows desktop update restart behavior. The import plugin is disabled by default
and can be enabled from the Plugins page. Arch package updates continue through
pacman/paru.

Existing custom plugins and SDK integrations should follow the upstream rc.2 upgrade
guide. Archiving sessions now cleans eligible Git worktrees by default while retaining
branches and commits; disable that cleanup in DSH settings to retain those directories.
