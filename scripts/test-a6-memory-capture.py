#!/usr/bin/env python3
"""Host tests for bounded Apple-tree capture; no device access."""
import ctypes
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
repo = Path(__file__).resolve().parents[1]

def prop(name, data):
    return name.encode().ljust(32, b'\0') + struct.pack('<I', len(data)) + data + b'\0' * (-len(data) % 4)

def node(properties, children=()):
    return struct.pack('<II', len(properties), len(children)) + b''.join(prop(*p) for p in properties) + b''.join(children)

with tempfile.TemporaryDirectory() as d:
    library = Path(d) / 'capture.so'
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DA6_CAPTURE_TEST', '-shared', '-fPIC', str(repo / 'boot/arm/capture-memory.c'), '-o', str(library)], check=True)
    metadata = ctypes.CDLL(str(library)).a6_memory_metadata
    metadata.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    metadata.restype = ctypes.c_int
    # Exact first56 bytes captured on hardware; no device access required.
    observed = [0x110001,0x9ea00000,0x80000000,0x3f7aa000,0x81018000,
                0xbf7aa000,0,0xa00,0x280,0x470,0x10020,0,0x9f9ff000,0x1584c]
    def check_metadata(values):
        out = (ctypes.c_uint * 704)()
        status = metadata(ctypes.create_string_buffer(struct.pack('<14I', *values)), out)
        return status, out
    status, result = check_metadata(observed)
    assert status == 0 and result[3] == 0x80fff000 and result[4] == 88140
    for version in (0,3,16,18,65535):
        changed = observed.copy(); changed[0] = (version << 16) | 1
        assert check_metadata(changed)[0] == 11
    for revision in (0,2,65535):
        changed = observed.copy(); changed[0] = (17 << 16) | revision
        assert check_metadata(changed)[0] == 11
    for index, value in ((2,0),(3,0x40000001),(3,0x7ffffff),
                         (12,0x9e9fffff),(12,0xffffffff),(13,0),(13,0x40001)):
        changed = observed.copy(); changed[index] = value
        assert check_metadata(changed)[0] == 12
    for version in (1,2):
        changed = observed.copy(); changed[0] = (version << 16) | 1
        assert check_metadata(changed)[0] == 0
    print('PASS observed v17 prefix, rejected layouts and RAM/tree bounds')
    parse = ctypes.CDLL(str(library)).a6_parse_memory
    parse.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
    parse.restype = ctypes.c_int
    def run(data):
        buf = ctypes.create_string_buffer(data)
        storage = (ctypes.c_uint * (704 + 2))()
        storage[0] = storage[-1] = 0xdeadbeef
        ptr = ctypes.cast(ctypes.byref(storage, 4), ctypes.POINTER(ctypes.c_uint))
        status = parse(buf, len(data), ptr)
        assert storage[0] == storage[-1] == 0xdeadbeef
        return status, list(storage)[1:-1]
    tree = node([('name', b'device-tree\0')], [
        node([('reg', struct.pack('<II', 0x80000000, 0x40000000)), ('name', b'memory\0')]),
        node([('name', b'chosen\0')], [node([('Kernel', struct.pack('<II', 0x80000000, 0x1000000)), ('name', b'memory-map\0')])])])
    status, out = run(tree)
    assert status == 1 and out[5] == 3 and out[6] == 4 and out[7] == 0
    assert out[32] == 1 and out[42:44] == [0x80000000, 0x40000000]
    assert out[50] == 2 and out[60:62] == [0x80000000, 0x1000000]
    spec = importlib.util.spec_from_file_location('decoder', repo/'scripts/decode-a6-memory-capture.py')
    decoder = importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
    out[0]=0x41364d31;out[1]=1;out[10]=0x80000000;out[11]=0x40000000
    report=decoder.decode(struct.pack('<704I',*out))
    assert report['complete_untruncated'] and report['records'][0]['candidate_address_size_pairs'][0]['within_reported_ram']
    out[7]=1
    assert not decoder.decode(struct.pack('<704I',*out))['complete_untruncated']

    for end in range(len(tree)):
        assert run(tree[:end])[0] != 1
    assert run(tree+b'\0')[0] != 1
    malformed = bytearray(tree);struct.pack_into('<I', malformed, 40, 0x7fffffff)
    assert run(bytes(malformed))[0] == 2
    deep = node([('name', b'leaf\0')])
    for _ in range(33):deep = node([('name', b'parent\0')], [deep])
    assert run(deep)[0] == 3
    status,out=run(node([('name',b'memory-map\0')]+[(f'r{i}',b'x'*40) for i in range(50)]))
    assert status == 1 and out[5] == 36 and out[7] == 3
    # Real firmware template must parse, but its zero map is not live evidence.
    status,out=run((repo/'.deps/legacy-ios-kit/firmware/DeviceTree.n42ap.raw').read_bytes())
    assert status == 1 and out[7] == 0
    print(f'PASS bounded capture parser: synthetic ranges, all truncations, depth/capacity guards, firmware template ({out[5]} records)')
stack = repo / 'build/arm/a6-capture-memory.su'
if stack.exists():
    sizes = [int(line.split('\t')[1]) for line in stack.read_text().splitlines()]
    assert sum(sizes) < 768, sizes
    print(f'PASS capture stack conservative sum {sum(sizes)} < 768 bytes')

obj = repo / 'build/arm/a6-capture-memory.o'
if obj.exists():
    # Code must remain relocatable to the loader's executable cave.
    section = ''
    for line in subprocess.check_output(['llvm-readelf', '-r', str(obj)], text=True).splitlines():
        if line.startswith('Relocation section'):
            section = line
        if 'R_ARM_' in line and "'.rel.text'" in section:
            assert 'R_ARM_CALL' in line or 'R_ARM_JUMP24' in line, line
    print('PASS capture text uses only PC-relative call relocations')
