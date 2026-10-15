#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
marker_pa="${A6_CPU1_MARKER_PA:?set an offline marker-page address for compilation}"
[[ "$marker_pa" =~ ^0x[[:xdigit:]]{8}$ ]] || {
    echo "A6_CPU1_MARKER_PA must be an eight-digit hex address" >&2
    exit 2
}
output="$repo_root/build/arm/a6-cpu1-entry-probe.o"
mkdir -p "$(dirname -- "$output")"
probe_defines=()
if [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]; then
    probe_defines+=(-DA6_CPU1_IPI_PROBE=1)
fi
if [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]
    probe_defines+=(-DA6_CPU1_TLBI_PROBE=1)
fi
if [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_TLBI_PROBE:-0}" == 1 ]]
    probe_defines+=(-DA6_CPU1_CACHE_PROBE=1)
fi
if [[ "${A6_CPU1_CACHE_TRE_PROBE:-0}" == 1 ]]; then
    [[ "${A6_CPU1_CACHE_PROBE:-0}" == 1 ]]
    probe_defines+=(-DA6_CPU1_CACHE_TRE_PROBE=1)
fi
if [[ "${A6_CPU1_IPI_CHECKPOINTS:-0}" == 1 ]]; then
    [[ "${A6_CPU1_IPI_PROBE:-0}" == 1 ]]
    probe_defines+=(-DA6_CPU1_IPI_CHECKPOINTS=1)
fi
clang --target=arm-none-eabi -mcpu=swift -marm -ffreestanding -nostdlib \
    -DA6_CPU1_MARKER_PA="$marker_pa" "${probe_defines[@]}" \
    -c "$repo_root/boot/arm/a6-cpu1-entry-probe.S" -o "$output"
if llvm-readelf -r "$output" | grep -q 'R_ARM'; then
    echo "CPU1 entry probe has unresolved relocations" >&2
    exit 1
fi
llvm-objcopy -O binary --only-section=.text.cpu1_probe "$output" "${output%.o}.bin"
llvm-objdump -d "$output"
sha256sum "$output"
echo "compile-only CPU1 probe; no release path or boot image was produced"
