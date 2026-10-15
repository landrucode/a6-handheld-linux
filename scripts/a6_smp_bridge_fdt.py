"""Remove only the explicitly reviewed N42 secondary-bridge DT additions."""
import struct


def strip_bridge_properties(current):
    def take(path, key, expected):
        value = current.pop((path, key))
        if value != expected:
            raise ValueError(f"unexpected bridge property {path}/{key}: {value!r}")

    take("/cpus", "enable-method", b"apple,a6-one-shot\0")
    take("/cpus/cpu@1", "compatible", b"apple,swift\0arm,cortex-a9\0")
    take("/cpus/cpu@1", "device_type", b"cpu\0")
    take("/cpus/cpu@1", "reg", struct.pack(">I", 1))
    for name, base, size in (
        ("a6-cpu1-reset-vector", 0x80000000, 0x2000),
        ("a6-cpu1-mailbox", 0x83ffe000, 0x1000),
    ):
        node = f"/reserved-memory/{name}@{base:x}"
        take(node, "reg", struct.pack(">II", base, size))
        take(node, "no-map", b"")
    key = ("/timer", "interrupts")
    if current[key] != struct.pack(">II", 0xa2, 0xa5):
        raise ValueError("CPU0/CPU1 virtual-timer tuple changed")
    current[key] = struct.pack(">I", 0xa2)
