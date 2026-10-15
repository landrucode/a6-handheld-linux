#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)"
export A6_CPU1_CACHE_SHAREABLE_PROBE=1
bash "$repo_root/scripts/build-a6-cpu1-cache-repeat-image.sh"
