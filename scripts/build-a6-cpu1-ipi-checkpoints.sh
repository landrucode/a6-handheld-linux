#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "${BASH_SOURCE[0]%/*}/.." && pwd)"
export A6_CPU1_IPI_CHECKPOINTS=1
bash "$repo_root/scripts/build-a6-cpu1-ipi-image.sh"
