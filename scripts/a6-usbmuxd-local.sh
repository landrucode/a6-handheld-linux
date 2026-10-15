#!/usr/bin/env bash
# Run the project-local iOS USB helper; restore private pairing after reboot.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
umask 077
state="$repo_root/build/host/lockdown"
install -d -m 700 "$state" /tmp/a6l/lockdown
for record in "$state"/*.plist; do
    [[ -f "$record" ]] || continue
    install -m 600 "$record" /tmp/a6l/lockdown/
done
exec "$repo_root/build/host/usbmuxd-local/usbmuxd-user" -f -p
