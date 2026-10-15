#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source="$repo_root/.deps/legacy-ios-kit/firmware/Kernelcache.n42.raw"
zimage="${A6_ZIMAGE:-$repo_root/build/linux-a6/arch/arm/boot/zImage}"
dtb="${A6_DTB:-$repo_root/build/arm/a6-n42ap.dtb}"
payload="${A6_PAYLOAD:-$repo_root/build/arm/a6-n42ap-zImage-with-dtb}"
handoff_source="$repo_root/boot/arm/linux-handoff.S"
handoff_object="$repo_root/build/arm/a6-linux-handoff.o"
handoff_elf="$repo_root/build/arm/a6-linux-handoff.elf"
handoff_raw="$repo_root/build/arm/a6-linux-handoff.raw"
output="${A6_KERNELCACHE_RAW:-$repo_root/build/arm/a6-linux-kernelcache.raw}"
packed_output="${A6_KERNELCACHE_IMG3:-$repo_root/build/arm/a6-linux-kernelcache.img3}"
roundtrip_output="${A6_KERNELCACHE_ROUNDTRIP:-$repo_root/build/arm/a6-linux-kernelcache.roundtrip.raw}"
template="$repo_root/.deps/legacy-ios-kit/kernelcache.release.n42"
xpwntool="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/xpwntool"
kernel_iv="a037ef50ae5bf24ae2d373345b6e5be5"
kernel_key="66b8ca4f732113f54dae9de7d1713093d6c54731c06033eef94489c168a8db3a"

[[ -s "$source" ]] || {
	echo "missing matching decrypted kernelcache: $source" >&2
	exit 1
}
[[ -s "$zimage" && -s "$dtb" ]] || {
	echo "missing Linux image inputs; run scripts/build-a6-zimage.sh first" >&2
	exit 1
}
# The CPU0-only profile never releases CPU1. The separate bridge profile
# installs the owned reset trampoline and parks CPU1 before it is online.
# Every other SMP profile is still refused here.
kernel_config="$(dirname -- "$(dirname -- "$(dirname -- "$(dirname -- "$zimage")")")")/.config"
if [[ -f "$kernel_config" ]] && grep -qx 'CONFIG_SMP=y' "$kernel_config"; then
    if [[ "${A6_SMP_BRIDGE_QUARANTINE:-0}" == 1 &&
          ( ( "${A6_SMP_SCHEDULING:-0}" != 1 && "${A6_SMP_TIMER_LINE_PROBE:-0}" != 1 &&
              "$dtb" == *-smp-bridge-quarantine.dtb &&
              "$zimage" == *-smp-bridge-quarantine/arch/arm/boot/zImage ) ||
            ( "${A6_SMP_TIMER_LINE_PROBE:-0}" == 1 && "${A6_SMP_SCHEDULING:-0}" != 1 &&
              "$dtb" == *-smp-timer-line-checkpoint.dtb &&
              "$zimage" == *-smp-timer-line-checkpoint/arch/arm/boot/zImage ) ||
            ( "${A6_SMP_SCHEDULING:-0}" == 1 &&
              "$dtb" == *-smp-first-scheduling.dtb &&
              "$zimage" == *-smp-first-scheduling/arch/arm/boot/zImage ) ) ]]; then
        python3 "$repo_root/scripts/check-a6-smp-bridge.py" "$(dirname -- "$kernel_config")" "$dtb"
    else
    if [[ "${A6_SMP_CPU0_ONLY:-0}" != 1 ||
          "$dtb" != *-smp-cpu0-only.dtb ||
          "$zimage" != *-smp-cpu0-only/arch/arm/boot/zImage ]]; then
        echo "refusing SMP IMG3: CPU1 entry and timer integration are incomplete" >&2
        exit 1
    fi
    rg -q '^CONFIG_CMDLINE="[^"]* maxcpus=1"$' "$kernel_config"
    rg -q '^CONFIG_CMDLINE_FORCE=y$' "$kernel_config"
    dtc_bin="$(dirname -- "$(dirname -- "$(dirname -- "$(dirname -- "$zimage")")")")/scripts/dtc/dtc"
    [[ -x "$dtc_bin" ]]
    dts_text="$("$dtc_bin" -I dtb -O dts "$dtb" 2>/dev/null)"
    [[ "$dts_text" == *maxcpus=1* && "$dts_text" == *cpu@0* && "$dts_text" != *cpu@1* ]] || {
        echo 'refusing SMP IMG3 without a CPU0-only capped DT' >&2
        exit 1
    }
    fi
fi
[[ -s "$template" && -x "$xpwntool" ]] || {
	echo "missing kernelcache template or xpwntool" >&2
	exit 1
}

mkdir -p "$(dirname -- "$output")"

payload_size=$(($(stat -c %s "$zimage") + $(stat -c %s "$dtb")))
payload_size=$(((payload_size + 3) & ~3))
handoff_flags=()
if [[ "${A6_AUDIO_ALSA:-0}" == 1 ]]; then
    # Same loaded __TEXT mapping, earlier source; destination is unchanged.
    if [[ "${A6_BROWSER_SANDBOX:-0}" == 1 ]]; then
        handoff_flags+=(-DPAYLOAD_SOURCE_ADDRESS=0x800e9000)
    else
        handoff_flags+=(-DPAYLOAD_SOURCE_ADDRESS=0x800f1000)
    fi
fi
handoff_extra=()
if [[ "${A6_MEMORY_CAPTURE:-0}" == 1 ]]; then
    handoff_flags+=(-DA6_MEMORY_CAPTURE=1)
    handoff_extra+=("$repo_root/build/arm/a6-capture-memory.o")
    capture_flags=()
    if [[ "${A6_CAPTURE_AUDIO:-0}" == 1 ]]; then capture_flags+=(-DA6_CAPTURE_AUDIO=1); fi
    if [[ "${A6_CAPTURE_TOUCH:-0}" == 1 ]]; then capture_flags+=(-DA6_CAPTURE_TOUCH=1); fi
    if [[ "${A6_CAPTURE_CLOCK:-0}" == 1 ]]; then capture_flags+=(-DA6_CAPTURE_CLOCK=1); fi
    if [[ "${A6_CAPTURE_CPU_CLOCK:-0}" == 1 ]]; then capture_flags+=(-DA6_CAPTURE_CPU_CLOCK=1); fi
    clang "${capture_flags[@]}" --target=arm-none-eabi -mcpu=swift -marm -mfloat-abi=soft -Os \
        -ffreestanding -fno-builtin -fno-stack-protector -fpie -fstack-usage \
        -Wall -Wextra -Werror -c "$repo_root/boot/arm/capture-memory.c" \
        -o "${handoff_extra[0]}"
    python3 "$repo_root/scripts/test-a6-memory-capture.py"
    if [[ "${A6_CAPTURE_TOUCH:-0}" == 1 ]]; then python3 "$repo_root/scripts/test-a6-touch-capture.py"; fi
    if [[ "${A6_CAPTURE_CLOCK:-0}" == 1 ]]; then python3 "$repo_root/scripts/test-a6-clock-capture.py"; fi
    if [[ "${A6_CAPTURE_CPU_CLOCK:-0}" == 1 ]]; then python3 "$repo_root/scripts/test-a6-clock-capture.py" --cpu; fi
fi
clang --target=arm-none-eabi -mcpu=swift -marm -ffreestanding -fno-pic "${handoff_flags[@]}" \
	-nostdlib -DPAYLOAD_SIZE="$payload_size" -c \
	-o "$handoff_object" "$handoff_source"
ld.lld -m armelf --image-base=0 -Ttext=0 -e _start \
	-o "$handoff_elf" "$handoff_object" "${handoff_extra[@]}"
if llvm-readelf -r "$handoff_elf" | grep -q 'R_ARM'; then
	echo "unresolved ARM relocation in handoff" >&2
	exit 1
fi
if [[ "${A6_MEMORY_CAPTURE:-0}" == 1 ]]; then
    python3 - "$handoff_elf" <<'CHECK'
import subprocess, sys
symbols = dict((line.split()[2], int(line.split()[0],16)) for line in
               subprocess.check_output(['llvm-nm', '-n', sys.argv[1]],text=True).splitlines()
               if len(line.split()) == 3)
assert symbols['_start'] == 0
assert 'a6_capture_memory' in symbols
CHECK
fi
# The freestanding handoff never unwinds. ARM C emits an orphan exidx
# section far beyond .text under the default linker script; omit unwind
# metadata instead of relaxing the executable-cave size guard.
llvm-objcopy -O binary --remove-section=.ARM.exidx --remove-section=.ARM.extab "$handoff_elf" "$handoff_raw"

python3 - "$source" "$zimage" "$dtb" "$payload" "$handoff_raw" "$output" <<'PY'
from pathlib import Path
import hashlib
import os
import struct
import sys

source = Path(sys.argv[1])
zimage_path = Path(sys.argv[2])
dtb_path = Path(sys.argv[3])
payload_path = Path(sys.argv[4])
handoff_path = Path(sys.argv[5])
destination = Path(sys.argv[6])
data = bytearray(source.read_bytes())
zimage = zimage_path.read_bytes()
dtb = dtb_path.read_bytes()
payload = zimage + dtb
payload += b'\0' * (-len(payload) % 4)
handoff = handoff_path.read_bytes()

assert len(zimage) % 8 == 0
assert struct.unpack_from('>I', dtb, 0)[0] == 0xd00dfeed
assert struct.unpack_from('>I', dtb, 4)[0] == len(dtb)
payload_path.write_bytes(payload)

magic, cputype, cpusubtype, filetype, ncmds, _, _ = struct.unpack_from(
    '<7I', data, 0
)
assert (magic, cputype, cpusubtype, filetype) == (0xfeedface, 12, 11, 2)

offset = 28
text = None
thread_offset = None
for _ in range(ncmds):
    command, command_size = struct.unpack_from('<2I', data, offset)
    if command == 1:
        name = bytes(data[offset + 8:offset + 24]).split(b'\0', 1)[0]
        vmaddr, vmsize, fileoff, filesize, maxprot, initprot, _, _ = struct.unpack_from(
            '<8I', data, offset + 24
        )
        if name == b'__TEXT':
            text = (vmaddr, vmsize, fileoff, filesize, maxprot, initprot)
    elif command == 5:
        flavor, count = struct.unpack_from('<2I', data, offset + 8)
        assert (flavor, count) == (1, 17)
        thread_offset = offset + 16
    offset += command_size

assert text == (0x80001000, 0x396000, 0, 0x396000, 0x5, 0x5), text
assert thread_offset is not None

# Keep the validated Mach-O thread entry unchanged. The earlier handoff proof
# established that iBEC accepts a patched instruction at that entry, while it
# rejects a replacement LC_UNIXTHREAD PC. Put the relocatable zImage later in
# __TEXT and branch to it from the original Apple kernel entry. AUTO_ZRELADDR
# will decompress Linux to 0x80008000 from this address.
entry_vmaddr = struct.unpack_from('<I', data, thread_offset + 15 * 4)[0]
assert entry_vmaddr == 0x800b3084, hex(entry_vmaddr)
entry_file_offset = text[2] + entry_vmaddr - text[0]
assert entry_file_offset == 0xb2084, hex(entry_file_offset)

payload_file_offset = 0xff000
if os.environ.get('A6_AUDIO_ALSA') == '1':
    assert os.environ.get('A6_AUDIO_FIFO_DISCOVER') == '1'
    assert os.environ.get('A6_AUDIO_TONE') == '1'
    payload_file_offset = 0xe8000 if os.environ.get('A6_BROWSER_SANDBOX') == '1' else 0xf0000
    if os.environ.get('A6_BROWSER_SANDBOX') == '1':
        # Namespaces/memcg add 17 KiB beyond the old source slot. Both
        # slots stay after the preserved entry and within loaded __TEXT.
        config = zimage_path.parents[3] / '.config'
        options = config.read_text().splitlines()
        assert all('CONFIG_' + name + '=y' in options for name in
                   ('USER_NS', 'PID_NS', 'IPC_NS', 'UTS_NS', 'NET_NS', 'MEMCG', 'PSI'))
payload_vmaddr = text[0] + payload_file_offset - text[2]
assert payload_vmaddr == ((0x800e9000 if os.environ.get('A6_BROWSER_SANDBOX') == '1' else 0x800f1000) if os.environ.get('A6_AUDIO_ALSA') == '1' else 0x80100000), hex(payload_vmaddr)
assert entry_file_offset + 4 < payload_file_offset
assert payload_file_offset + len(payload) <= text[3]
# The shell includes a static libc/BusyBox. Its aligned relocation starts
# at 0x82000000; the decompressor maps both 1-MiB execution sections (and
# the surrounding RAM). Keep this expansion opt-in and below 0x82200000.
payload_limit = 0x200000 if os.environ.get('A6_USB_SHELL') == '1' else 0x100000
# ECM/IPv4 adds compressed code beyond two MiB. __setup_mmu maps RAM
# 0x80000000..0x8fffffff, including the third relocation section. The
# source __TEXT extent assertion above remains stricter than the old image
# container; cap this profile at 2.5 MiB, ending below 0x82280000.
if os.environ.get('A6_USB_NETWORK') == '1':
    assert os.environ.get('A6_USB_SHELL') == '1'
    payload_limit = 0x280000
    # The isolated touch/RAM-root frame probe exceeds the legacy cap by
    # 148 bytes. Permit one additional 64 KiB only for this reviewed profile;
    # the actual __TEXT boundary and decompressed identity-map check remain.
    if os.environ.get('A6_TOUCH_FRAME_CAPTURE') == '1':
        assert os.environ.get('A6_RAM_ROOT') == '1'
        assert os.environ.get('A6_TOUCH_RAM_ROOT_CANDIDATE') == '1'
        assert os.environ.get('A6_SMP_SCHEDULING') == '1'
        payload_limit = 0x290000
        # The ROM-only downloader/FW_LOADER adds 3212 bytes beyond this cap.
        # Permit 8 KiB only for its fully gated RAM profile; the stock __TEXT
        # extent above and mapped third relocation section remain mandatory.
        if os.environ.get('A6_WIFI_USB_DOWNLOAD') == '1':
            assert os.environ.get('A6_WIFI_USB_OTP') == '1'
            assert os.environ.get('A6_WIFI_USB_IDENTITY') == '1'
            assert os.environ.get('A6_WIFI_EHCI_ENUM') == '1'
            payload_limit = 0x292000
            if os.environ.get("A6_AUDIO_FIFO_DISCOVER") == "1":
                # Still within stock __TEXT (0x297000 available) and identity map.
                payload_limit = 0x296000
                if os.environ.get('A6_AUDIO_ALSA') == '1':
                    payload_limit += 0xff000 - payload_file_offset
assert len(payload) < payload_limit, len(payload)

data[payload_file_offset:payload_file_offset + len(payload)] = payload

# Put the handoff in a verified zero-filled executable cave. It copies the
# payload to 0x82000000 before entering it, avoiding decompressor overlap.
prelink_vmaddr = 0x80465000
prelink_fileoff = 0x41d000
handoff_file_offset = 0xc7338c
handoff_vmaddr = prelink_vmaddr + handoff_file_offset - prelink_fileoff
assert len(handoff) < 0x1000
assert all(x == 0 for x in data[handoff_file_offset:handoff_file_offset + len(handoff)])
data[handoff_file_offset:handoff_file_offset + len(handoff)] = handoff

branch_delta = handoff_vmaddr - (entry_vmaddr + 8)
assert branch_delta % 4 == 0
assert -(1 << 25) <= branch_delta < (1 << 25)
branch = 0xea000000 | ((branch_delta >> 2) & 0x00ffffff)
old_entry = struct.unpack_from('<I', data, entry_file_offset)[0]
assert old_entry == 0xe3a01000, hex(old_entry)
struct.pack_into('<I', data, entry_file_offset, branch)

destination.write_bytes(data)
print(f'zImage:  {zimage_path} ({len(zimage)} bytes)')
print(f'DTB:     {dtb_path} ({len(dtb)} bytes)')
print(f'payload: {payload_path} ({len(payload)} bytes)')
print(f'entry:   {entry_vmaddr:#010x} -> {handoff_vmaddr:#010x}')
print(f'handoff: {handoff_vmaddr:#010x} ({len(handoff)} bytes)')
print('copy:    0x80100000 -> 0x82000000')
print(f'branch:  {branch:#010x}')
print(f'payload offset: {payload_file_offset:#x}')
print(f'output:  {destination} ({len(data)} bytes)')
print(f'sha256:  {hashlib.sha256(data).hexdigest()}')
PY

file "$output"
sha256sum "$output"

"$xpwntool" "$output" "$packed_output" -t "$template" \
	-iv "$kernel_iv" -k "$kernel_key"
"$xpwntool" "$packed_output" "$roundtrip_output" \
	-iv "$kernel_iv" -k "$kernel_key"
cmp "$output" "$roundtrip_output"
rm -f "$roundtrip_output"

echo "verified decrypt-after-repack round trip"
sha256sum "$packed_output"
