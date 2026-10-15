#!/bin/bash
set -euo pipefail
printf 'Onscreen keyboard test: click a, then Enter.\n'
IFS= read -r received
printf '%s\n' "$received" > /home/a6/osk-proof
if [[ "$received" == a ]]; then
    printf 'ONSCREEN_KEYBOARD_PASS (UID=%s)\n' "$(id -u)"
else
    printf 'Unexpected input; inspect /home/a6/osk-proof\n'
fi
exec /bin/bash
