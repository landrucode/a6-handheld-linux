#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export A6_CPU1_ENTRY_PROBE=1
bash "$repo_root/scripts/build-a6-cpu1-alias-write-proof.sh"
