"""Validate local generated desktop inputs; phone trust uses signed bundles."""
import hashlib
import json
from pathlib import Path

LEGACY = {'88d9362f58826f5154d2548edfe86c44b63e7f121ebc3804eb50402a85cf394e',
          '2edf5daa7307ed4c1e02f329667bd7759bd304577d671ab341ccfebf5bee4d07'}

def verified_base(path, root):
    path = Path(path).resolve()
    if not path.is_relative_to(root/'build'):
        raise ValueError('Desktop build input must be under build/')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    if sha not in LEGACY:
        meta = json.loads(path.with_suffix('.json').read_text())
        if meta.get('kind') != 'a6-handheld-base' or meta.get('sha256') != sha:
            raise ValueError('Generated desktop base provenance/hash mismatch')
        if not meta.get('inputs') or not meta.get('round_trip_verified'):
            raise ValueError('Generated desktop base lacks verified input/round-trip evidence')
    return sha
