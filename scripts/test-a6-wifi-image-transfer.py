#!/usr/bin/env python3
"""Verify fail-before-network behavior and exact completed-image reuse."""
import hashlib,importlib.util,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('transfer',Path(__file__).with_name('a6-wifi-image-transfer.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Phone:
 def __init__(self,result=''):self.result=result;self.commands=[]
 def checked(self,command):self.commands.append(command);return self.result
class Transfer(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.source=Path(self.temp.name)/'image';self.source.write_bytes(b'public image');self.digest=hashlib.sha256(self.source.read_bytes()).hexdigest()
 def tearDown(self):self.temp.cleanup()
 def test_bad_hash_never_contacts_phone(self):
  p=Phone()
  with self.assertRaises(ValueError):m.transfer(p,self.source,'/tmp/image','0'*64)
  self.assertEqual(p.commands,[])
 def test_path_escape_never_contacts_phone(self):
  p=Phone()
  with self.assertRaises(ValueError):m.transfer(p,self.source,'/tmp/../etc/image',self.digest)
  self.assertEqual(p.commands,[])
 def test_verified_complete_image_reused(self):
  p=Phone(self.digest+'  /tmp/image\n');m.transfer(p,self.source,'/tmp/image',self.digest)
  self.assertEqual(len(p.commands),1)
 def test_differing_complete_image_preserved(self):
  p=Phone('0'*64+'  /tmp/image\n')
  with self.assertRaises(ValueError):m.transfer(p,self.source,'/tmp/image',self.digest)
  self.assertEqual(len(p.commands),1)
if __name__=='__main__':unittest.main()
