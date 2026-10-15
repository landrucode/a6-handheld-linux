#!/usr/bin/env python3
"""Reject changed/unverified generated image inputs before desktop assembly."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('base',Path(__file__).with_name('a6-desktop-base.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)

class GeneratedBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'build').mkdir()
        self.image = self.root/'build/base.squashfs'
        self.image.write_bytes(b'generated image fixture')
        self.sha = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.meta = dict(kind='a6-handheld-base',sha256=self.sha,
                         inputs={'public-overlay':'verified'},round_trip_verified=True)
        self.write_meta()
    def tearDown(self): self.tmp.cleanup()
    def write_meta(self): self.image.with_suffix('.json').write_text(json.dumps(self.meta))
    def test_verified_generated_input(self):
        self.assertEqual(base.verified_base(self.image,self.root),self.sha)
    def test_changed_image(self):
        self.image.write_bytes(b'changed after verification')
        with self.assertRaises(ValueError): base.verified_base(self.image,self.root)
    def test_round_trip_required(self):
        self.meta['round_trip_verified']=False; self.write_meta()
        with self.assertRaises(ValueError): base.verified_base(self.image,self.root)
    def test_input_provenance_required(self):
        self.meta['inputs']={}; self.write_meta()
        with self.assertRaises(ValueError): base.verified_base(self.image,self.root)
    def test_build_boundary(self):
        other=self.root/'outside.squashfs';other.write_bytes(self.image.read_bytes())
        with self.assertRaises(ValueError): base.verified_base(other,self.root)

if __name__ == '__main__': unittest.main()
