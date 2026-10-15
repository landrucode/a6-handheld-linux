#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)"
export A6_SMP_BRIDGE_QUARANTINE=1
bash "$repo_root/scripts/build-a6-smp-compile-only.sh"
sha256sum "$repo_root/build/arm/a6-linux-low-battery-boot-defaults-smp-bridge-quarantine.img3"
