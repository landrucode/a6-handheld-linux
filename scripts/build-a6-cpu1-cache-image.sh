#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)"
export A6_CPU1_CACHE_PROBE=1
export A6_CPU1_TLBI_PROBE=1
bash "$repo_root/scripts/build-a6-cpu1-ipi-checkpoints.sh"
