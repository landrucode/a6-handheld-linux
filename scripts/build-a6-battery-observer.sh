#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export A6_BATTERY_OBSERVER=1 A6_DIRECT_DRM=1
bash scripts/build-a6-usb-console.sh
python3 scripts/verify-a6-battery-observer.py
sha256sum build/arm/a6-linux-battery-observer.img3
