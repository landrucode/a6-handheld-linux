"""Minimal read-only FDT property parser for build acceptance checks."""
import struct


def properties(blob):
    """Read FDT properties without depending on serialized string offsets."""
    magic, total, pos, strings = struct.unpack_from(">4I", blob)
    assert magic == 0xd00dfeed and total == len(blob)
    stack, result = [], {}
    while True:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:
            end = blob.index(0, pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, name = struct.unpack_from(">2I", blob, pos)
            pos += 8
            name += strings
            end = blob.index(0, name)
            key = ("/" + "/".join(stack[1:]), blob[name:end].decode())
            assert key not in result
            result[key] = blob[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            assert not stack
            return result
        else:
            raise AssertionError(f"bad FDT token {token}")

