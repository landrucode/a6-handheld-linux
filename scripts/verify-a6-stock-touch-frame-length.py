#!/usr/bin/env python3
"""Verify N42 stock frame-length acceptance and successful-read sequence evidence."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
blob = (ROOT / 'build/touch-research/AppleMultitouchSPI-ios10.macho').read_bytes()
assert hashlib.sha256(blob).hexdigest() == 'bc43e0e9d9670fb9c239be866327f30ef3b6ce43c63ab79743e8f048f46350f0'
base = 0x80854000

def check(address, expected):
    data = bytes.fromhex(expected)
    assert blob[address-base:address-base+len(data)] == data, hex(address)

# AND reply command with F0; compare E0. Check checksum over fourteen bytes.
check(0x8085da2c, '00f0f001e02915d1')
check(0x8085da40, '06a80e2103f0d0faa042')
# Successful read (r6==0) updates one/two sequence; errors skip this block.
check(0x8085d898, '4eb9012084f86b0894f86a18012908bf022084f86a08')
print(json.dumps({'stock_sha256': hashlib.sha256(blob).hexdigest(),
                  'reply_command_mask': 'f0', 'reply_command_value': 'e0',
                  'checksum_bytes': 14, 'sequence_updates_on_success': True,
                  'hardware_contacts_proven': False}, indent=2))
