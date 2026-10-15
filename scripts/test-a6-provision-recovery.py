#!/usr/bin/env python3
"""Offline fault injection of the real provisioning recovery paths."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('provision',Path(__file__).with_name('a6-provision-boot.py'))
provision=importlib.util.module_from_spec(spec);spec.loader.exec_module(provision)

class Phone:
    def __init__(self):self.commands=[];self.partial=''
    def checked(self,command,**kwargs):self.commands.append(command)
    def serial(self,command):
        return self.partial if 'PART_BYTES=' in command else ''

class NetworkFallback(unittest.TestCase):
    def choose(self, replies):
        clock=[0.0]
        phone=Phone()
        def checked(command, **kwargs):
            phone.commands.append(command)
            return replies[min(len(phone.commands)-1,len(replies)-1)]
        phone.checked=checked
        with patch.object(provision.time,'monotonic',side_effect=lambda:clock[0]), patch.object(provision.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
            result=provision.choose_image_transport(phone)
        return result,clock[0],phone

    def test_dhcp_and_gateway_ready_uses_wifi(self):
        result,elapsed,phone=self.choose(['A6_DHCP_PENDING','A6_GATEWAY_READY'])
        self.assertEqual(result,('wifi','dhcp_and_gateway_ready'))
        self.assertEqual(elapsed,1)
        self.assertIn('ping -I wlan0 -c 1 -W 1',phone.commands[-1])

    def test_missing_dhcp_falls_back_at_sixty_seconds(self):
        result,elapsed,_=self.choose(['A6_DHCP_PENDING'])
        self.assertEqual(result,('usb','dhcp_timeout'))
        self.assertEqual(elapsed,60)

    def test_lease_without_gateway_falls_back(self):
        result,elapsed,_=self.choose(['A6_GATEWAY_FAILED'])
        self.assertEqual(result,('usb','gateway_unreachable'))
        self.assertEqual(elapsed,60)

    def test_gateway_recovery_inside_deadline_uses_wifi(self):
        result,_,_=self.choose(['A6_GATEWAY_FAILED','A6_GATEWAY_READY'])
        self.assertEqual(result[0],'wifi')

    def test_usb_fallback_is_paced_and_never_cycles(self):
        phone=Phone()
        with patch.object(provision,'upload_large_once',return_value='ok') as upload, patch.object(provision,'upload_large',side_effect=AssertionError('must not cycle USB')):
            self.assertEqual(provision.deliver_image(phone,'usb',Path('source'),'/tmp/image','digest',True),'ok')
            self.assertTrue(upload.call_args.args[-1])
        self.assertEqual(phone.upload_window_bytes,1048576)
        self.assertEqual(phone.upload_rate_bytes,262144)
        self.assertEqual(phone.commands,[])

class Recovery(unittest.TestCase):
    def test_exact_verified_selected_directory_allowed(self):
        selected=provision.ROOT/'build/ram-updates/release-test'
        provision.validate_candidate_directory(selected,selected)
        provision.validate_candidate_directory(provision.ROOT/'build/signed-updates/legacy')
        with self.assertRaises(ValueError):
            provision.validate_candidate_directory(selected)
        with self.assertRaises(ValueError):
            provision.validate_candidate_directory(selected.parent/'different',selected)

    def test_one_cycle_and_verified_resume_requested(self):
        phone=Phone()
        with patch.object(provision,'upload_large_once',side_effect=[provision.UploadTransportError(), 'ok']) as transfer:
            self.assertEqual(provision.upload_large(phone,Path('source'),'/tmp/dest'),'ok')
            self.assertEqual(transfer.call_args_list[1].args[-1],True)
        self.assertEqual(len(phone.commands),1)
        self.assertIn('test ! -d /sys/class/net/wlan0',phone.commands[0])
        self.assertIn('usb0 down && busybox ip link set usb0 up',phone.commands[0])
        with patch.object(provision,'upload_large_once',side_effect=provision.UploadTransportError()):
            with self.assertRaises(provision.UploadTransportError):
                provision.upload_large(phone,Path('source'),'/tmp/dest')
        self.assertEqual(len(phone.commands),1)

    def test_hash_error_never_cycles(self):
        phone=Phone()
        with patch.object(provision,'upload_large_once',side_effect=ValueError('bad prefix')):
            with self.assertRaises(ValueError):provision.upload_large(phone,Path('source'),'/tmp/dest')
        self.assertEqual(phone.commands,[])

    def test_socket_failure_stops_owned_receiver_before_recovery(self):
        phone=Phone()
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';source.write_bytes(b'abcdef')
            with patch.object(provision.socket,'create_connection',side_effect=OSError('bulk failure')):
                with self.assertRaises(provision.UploadTransportError):
                    provision.upload_large_once(phone,source,'/tmp/dest')
        cleanup=phone.commands[-1]
        self.assertIn('test "$(cat /proc/$pid/comm)" = busybox',cleanup)
        self.assertIn('kill -TERM -"$pid" && sleep 1',cleanup)
        self.assertIn('netstat -lnt',cleanup)

    def test_resume_rejects_corrupt_prefix_before_receiver_start(self):
        phone=Phone();phone.partial='PART_BYTES=3\n'+hashlib.sha256(b'bad').hexdigest()+'  /tmp/dest.part\n'
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source';source.write_bytes(b'abcdef')
            with self.assertRaisesRegex(ValueError,'exact source prefix'):
                provision.upload_large_once(phone,source,'/tmp/dest',True)
        self.assertEqual(phone.commands,[])

if __name__=='__main__':unittest.main()
