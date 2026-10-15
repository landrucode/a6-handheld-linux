#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$repo_root/build/arm"
python3 - "$repo_root" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]);text=(p/'.deps/linux/include/uapi/linux/fb.h').read_text()
out='/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */\n'
out+='typedef unsigned int __u32; typedef unsigned short __u16;\n'
for name in ['fb_bitfield','fb_fix_screeninfo','fb_var_screeninfo']:
    matches=re.findall(r'struct '+name+r' \{.*?\n\};',text,re.S)
    assert len(matches)==1
    out+=matches[0]+'\n'
(p/'build/arm/a6-fb-uapi.h').write_text(out)
(p/'build/arm/a6-fb-font.S').write_text('.section .rodata\n.global a6_fb_font\na6_fb_font:\n.incbin "'+str(p/'kernel/font8x8.bin')+'"\n.section .note.GNU-stack,"",%progbits\n')
PY
clang --target=arm-linux-gnueabi -march=armv7-a -marm -mfloat-abi=soft \
  -Os -ffreestanding -fno-builtin -fno-stack-protector -fomit-frame-pointer \
  -Wall -Wextra -Werror -nostdlib -static -fuse-ld=lld \
  -I "$repo_root/build/arm" -Wl,-e,_start -Wl,--build-id=none \
  "$repo_root/rootfs/a6-mmu-test-start.S" "$repo_root/rootfs/a6-fb-test.c" \
  "$repo_root/build/arm/a6-fb-font.S" -o "$repo_root/build/arm/a6-fb-test"
sha256sum "$repo_root/build/arm/a6-fb-test"
