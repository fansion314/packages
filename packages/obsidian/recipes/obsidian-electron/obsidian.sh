#!/bin/bash

# One argument per line; ignore blank lines and comments. Do not eval user data.
flags=()
flags_file="${XDG_CONFIG_HOME:-$HOME/.config}/obsidian/user-flags.conf"
if [[ -r $flags_file ]]; then
    while IFS= read -r flag || [[ -n $flag ]]; do
        [[ $flag =~ ^[[:space:]]*(#|$) ]] && continue
        flags+=("$flag")
    done < "$flags_file"
fi

exec /usr/bin/electron /usr/lib/obsidian-electron/app.asar "${flags[@]}" "$@"
