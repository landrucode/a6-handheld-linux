#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source="$repo_root/.deps/legacy-ios-kit/firmware/Kernelcache.n42.raw"
output="$repo_root/build/arm/a6-kernelcache-handoff-proof.raw"
packed_output="$repo_root/build/arm/a6-kernelcache-handoff-proof.img3"
roundtrip_output="$repo_root/build/arm/a6-kernelcache-handoff-proof.roundtrip.raw"
template="$repo_root/.deps/legacy-ios-kit/kernelcache.release.n42"
xpwntool="$repo_root/.deps/legacy-ios-kit/bin/linux/x86_64/xpwntool"
kernel_iv="a037ef50ae5bf24ae2d373345b6e5be5"
kernel_key="66b8ca4f732113f54dae9de7d1713093d6c54731c06033eef94489c168a8db3a"

[[ -s "$source" ]] || {
	echo "missing $source" >&2
	exit 1
}
[[ -s "$template" && -x "$xpwntool" ]] || {
	echo "missing kernelcache template or xpwntool" >&2
	exit 1
}

mkdir -p "$(dirname -- "$output")"

python3 - "$source" "$output" <<'PY'
from pathlib import Path
import hashlib
import struct
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
data = bytearray(source.read_bytes())

magic, cputype, cpusubtype, filetype, ncmds, _, _ = struct.unpack_from(
    '<7I', data, 0
)
assert (magic, cputype, cpusubtype, filetype) == (0xfeedface, 12, 11, 2)

offset = 28
entry = None
text_vmaddr = None
text_fileoff = None
text_file_size = None
for _ in range(ncmds):
	cmd, cmdsize = struct.unpack_from('<2I', data, offset)
	if cmd == 1:
		name = bytes(data[offset + 8:offset + 24]).split(b'\0', 1)[0]
		vmaddr, _, fileoff, filesize = struct.unpack_from('<4I', data, offset + 24)
		if name == b'__TEXT':
			text_vmaddr = vmaddr
			text_fileoff = fileoff
			text_file_size = filesize
	if cmd == 5:
		flavor, count = struct.unpack_from('<2I', data, offset + 8)
		assert (flavor, count) == (1, 17)
		state = struct.unpack_from('<17I', data, offset + 16)
		entry = state[15]
	offset += cmdsize

assert entry == 0x800b3084, hex(entry)
assert (text_vmaddr, text_fileoff, text_file_size) == (0x80001000, 0, 0x396000)
entry_offset = text_fileoff + (entry - text_vmaddr)
old = struct.unpack_from('<I', data, entry_offset)[0]
assert old == 0xe3a01000, hex(old)

# Keep the complete valid kernelcache and make its entry point spin.
struct.pack_into('<I', data, entry_offset, 0xeafffffe)  # ARM: b .
destination.write_bytes(data)
print(f'entry:  {entry:#x}')
print(f'offset: {entry_offset:#x}')
print(f'patch:  {old:#010x} -> {0xeafffffe:#010x} (ARM b .)')
print(f'output: {destination} ({len(data)} bytes)')
print(f'sha256: {hashlib.sha256(data).hexdigest()}')
PY

file "$output"

"$xpwntool" "$output" "$packed_output" -t "$template" \
	-iv "$kernel_iv" -k "$kernel_key"
"$xpwntool" "$packed_output" "$roundtrip_output" \
	-iv "$kernel_iv" -k "$kernel_key"
cmp "$output" "$roundtrip_output"
rm -f "$roundtrip_output"

echo "verified decrypt-after-repack round trip"
sha256sum "$packed_output"
