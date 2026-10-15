#!/usr/bin/env bash
# Separate RAM-only N42 image: bounded stock-style E2 retries after calibration.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
umask 077
export A6_TOUCH_E2_RETRY=1
bash scripts/build-a6-touch-full-n42.sh
