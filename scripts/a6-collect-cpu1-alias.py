#!/usr/bin/env python3
"""Collect frozen, read-only alias evidence; retain raw bytes and page hashes."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import struct
import subprocess
import sys


def decode(capture, prefix):
    text = capture.read_text(errors="replace").replace("\r", "")
    header = re.search(r"^A6_CPU1_ALIAS_V2 .*?$", text, re.M)
    if not header:
        raise ValueError("missing alias status; raw console capture retained")
    info = dict(re.findall(r"(\w+)=([^\s]+)", header[0]))
    begin = re.search(r"^A6_ALIAS_BEGIN_([0-9a-f]+)$", text, re.M)
    if not begin:
        raise ValueError("missing binary start marker")
    end = re.search(r"^A6_ALIAS_END_" + begin[1] + r"$", text[begin.end():], re.M)
    if not end:
        raise ValueError("missing binary end marker")
    encoded = text[begin.end():begin.end() + end.start()]
    raw = base64.b64decode("".join(encoded.split()), validate=True)
    if len(raw) != 16384:
        raise ValueError(f"expected 16384 bytes, received {len(raw)}")
    phone_hash = re.search(r"^([0-9a-f]{64})\s+/tmp/a6-cpu1-alias-snapshot.bin$", text, re.M)
    digest = hashlib.sha256(raw).hexdigest()
    if not phone_hash or digest != phone_hash[1]:
        raise ValueError("phone/host SHA-256 mismatch")
    prefix.with_suffix(".bin").write_bytes(raw)
    pages = {}
    rows = []
    for index, name in enumerate(("ram0", "zero0", "ram1000", "zero1000")):
        page = raw[index * 4096:(index + 1) * 4096]
        pages[name] = hashlib.sha256(page).hexdigest()
        words = struct.unpack("<1024I", page)
        rows.append(name)
        rows.extend(f"{offset * 4:03x}: " + " ".join(f"{v:08x}" for v in words[offset:offset + 4])
                    for offset in range(0, 1024, 4))
    prefix.with_suffix(".words.txt").write_text("\n".join(rows) + "\n")
    verdicts = []
    complete = int(info["result"]) == 0 and int(info["words"]) == 2048
    for page, key in enumerate(("same0", "same1000")):
        ram = raw[page * 8192:page * 8192 + 4096]
        zero = raw[page * 8192 + 4096:(page + 1) * 8192]
        valid_words = max(0, min(1024, int(info["words"]) - page * 1024))
        same = sum(ram[i * 4:i * 4 + 4] == zero[i * 4:i * 4 + 4]
                   for i in range(valid_words))
        if same != int(info[key]):
            raise ValueError("binary comparison disagrees with kernel counters")
        verdicts.append("incomplete" if not complete else
                        "no_match" if ram != zero else
                        "all_zero_inconclusive" if not any(ram) else "match")
    if info.get("uncached") != "1" or info.get("release_writes") != "0":
        raise ValueError("unexpected mapping/release status")
    manifest = {"status": info, "sha256": digest, "page_sha256": pages,
                "offset_0": verdicts[0], "offset_1000": verdicts[1],
                "capture": str(capture), "raw_order": list(pages),
                "scope": "CPU0 observation only; no write test or CPU1 fetch proof"}
    prefix.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decode", type=Path, help="decode an existing console capture")
    parser.add_argument("--output-dir", type=Path, default=Path("logs/smp"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(6)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = args.output_dir / f"{stamp}-cpu1-alias-{nonce}"
    capture = args.decode or prefix.with_suffix(".console.txt")
    if not args.decode:
        done = "A6_ALIAS_DONE_" + nonce
        command = (
            "test -r /sys/firmware/a6_cpu1_alias/snapshot && "
            "cat /sys/firmware/a6_cpu1_alias/snapshot && "
            "cat /sys/firmware/a6_cpu1_alias/snapshot_raw > /tmp/a6-cpu1-alias-snapshot.bin && "
            "sha256sum /tmp/a6-cpu1-alias-snapshot.bin && "
            f"printf '\\nA6_ALIAS_BEGIN_{nonce}\\n' && "
            "base64 /tmp/a6-cpu1-alias-snapshot.bin && "
            f"printf 'A6_ALIAS_END_{nonce}\\n'; printf '{done}\\n'"
        )
        helper = Path(__file__).with_name("a6-usb-acm-direct.py")
        with capture.open("wb") as output:
            result = subprocess.run([sys.executable, str(helper), command,
                                     "--until", done, "--timeout", "60"],
                                    stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"capture failed; partial evidence retained at {capture}")
    manifest = decode(capture, prefix)
    print(f"offset 0: {manifest['offset_0']}; offset 0x1000: {manifest['offset_1000']}")
    print(f"raw words, binary and hashes: {prefix}")


if __name__ == "__main__":
    main()
