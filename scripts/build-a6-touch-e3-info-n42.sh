#!/usr/bin/env bash
# Separate RAM-only N42 image: bounded E3 family report-info probe.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
umask 077
export A6_TOUCH_E2_RETRY=1 A6_TOUCH_CLK32_ENABLE=1 A6_TOUCH_E3_INFO=1
bash scripts/build-a6-touch-full-n42.sh
