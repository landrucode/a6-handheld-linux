#!/usr/bin/env bash
# Isolated, opt-in N42 PMU current trial; retains the working touch/USB shell.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
umask 077
export A6_TOUCH_E2_RETRY=1 A6_TOUCH_CLK32_ENABLE=1
export A6_CHARGER_ACTIVE_TRIAL=1
bash scripts/build-a6-touch-full-n42.sh
python3 scripts/verify-a6-touch-charge-trial-n42.py
