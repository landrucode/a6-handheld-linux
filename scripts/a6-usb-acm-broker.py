#!/usr/bin/env python3
"""Hold one private raw ACM session for an attended RAM-only phone trial.

Drain console output between commands; detach/claim once, restore on exit.
A transport fault latches until explicit broker restart; no automatic rebind.
Commands and output are returned over an owner-only local Unix socket, never
saved by this broker. No USB reset, exploit, phone storage or network changes.
"""
import argparse
import ctypes as C
from datetime import datetime, timezone
import json
import importlib.util
import os
from pathlib import Path
import shlex
import secrets
import signal
import socket
import time


def prepare(command, marker):
    if marker and command.endswith('echo ' + marker):
        split = max(1, len(marker)//2)
        command = command[:-len('echo '+marker)] + "printf '\\n%s%s\\n' " + \
                  shlex.quote(marker[:split]) + ' ' + shlex.quote(marker[split:])
    return (command+'\n').encode()


def save_failed_read(data, outcome):
    directory = Path(__file__).resolve().parents[1]/'build/session-logs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/('acm-failed-read-' + str(time.time_ns()) + '.private.raw')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
    return outcome + '; raw bytes saved to ' + str(path)


def collect(read, marker, timeout, prefix=b'', begin=None):
    output = bytearray(prefix)
    def visible():
        if begin is None:
            return bytes(output)
        # Input echo can contain encoded credentials, including late echoes
        # from a prior timed-out request. A split, output-only start marker
        # separates execution output from all console input echoes.
        token = b'\n' + begin.encode() + b'\r'
        offset = output.find(token)
        return bytes(output[offset+len(token)-1:]) if offset>=0 else b''
    deadline = time.monotonic() + timeout
    token = marker.encode() if marker else None
    while time.monotonic() < deadline:
        try:
            chunk = read(100)
        except USBTransportError as error:
            output.extend(getattr(error, 'partial', b''))
            detail = save_failed_read(visible(), 'Transport error')
            raise USBTransportError(detail) from error
        if chunk:
            output.extend(chunk)
            if len(output) > 2*1024*1024:
                return 1, b'', 'Console output bound exceeded'
            if token and b'\n'+token+b'\r' in output[-16384:]:
                return 0, visible(), ''
    error = ''
    if token:
        outcome = 'Bytes received without completion marker' if output else 'No bytes received before deadline'
        error = save_failed_read(visible(), outcome)
    return (1 if token else 0), visible(), error


class USBTransportError(RuntimeError):
    pass


class USBUnavailable(USBTransportError):
    pass


class Session:
    def __init__(self):
        self.lib = C.CDLL('libusb-1.0.so.0')
        self.ctx = C.c_void_p()
        self.handle = None
        self.claimed = self.detached = False
        self.lib.libusb_init.argtypes = [C.POINTER(C.c_void_p)]
        self.lib.libusb_open_device_with_vid_pid.argtypes = [C.c_void_p, C.c_uint16, C.c_uint16]
        self.lib.libusb_open_device_with_vid_pid.restype = C.c_void_p
        for name in ('libusb_kernel_driver_active','libusb_detach_kernel_driver',
                     'libusb_attach_kernel_driver','libusb_claim_interface','libusb_release_interface'):
            getattr(self.lib,name).argtypes = [C.c_void_p,C.c_int]
        self.lib.libusb_bulk_transfer.argtypes = [C.c_void_p,C.c_ubyte,C.c_void_p,
                                                C.c_int,C.POINTER(C.c_int),C.c_uint]
        self.lib.libusb_close.argtypes = [C.c_void_p]
        self.lib.libusb_exit.argtypes = [C.c_void_p]
        if self.lib.libusb_init(C.byref(self.ctx)):
            raise RuntimeError('USB initialization failed')
        try:
            self.handle = self.lib.libusb_open_device_with_vid_pid(self.ctx,0x0525,0xa4aa)
            if not self.handle:
                raise USBUnavailable('RAM gadget unavailable')
            active = self.lib.libusb_kernel_driver_active(self.handle,3)
            if active < 0:
                raise RuntimeError('USB driver query failed')
            if active:
                if self.lib.libusb_detach_kernel_driver(self.handle,3):
                    raise RuntimeError('ACM detach failed')
                self.detached = True
            if self.lib.libusb_claim_interface(self.handle,3):
                raise RuntimeError('ACM claim failed')
            self.claimed = True
        except Exception:
            self.close()
            raise

    def read(self, timeout):
        buf = (C.c_ubyte*8192)()
        got = C.c_int()
        rc = self.lib.libusb_bulk_transfer(self.handle,0x85,buf,len(buf),C.byref(got),timeout)
        if rc not in (0,-7):
            error = USBTransportError('USB read failed: '+str(rc))
            error.partial = bytes(buf[:got.value])
            raise error
        # A timed-out transfer can still contain partial data.
        return bytes(buf[:got.value])

    def write(self, data):
        buf = (C.c_ubyte*len(data)).from_buffer_copy(data)
        got = C.c_int()
        rc = self.lib.libusb_bulk_transfer(self.handle,0x04,buf,len(buf),C.byref(got),3000)
        if rc or got.value != len(data):
            raise USBTransportError('USB command write failed')

    def close(self):
        if self.handle:
            if self.claimed:
                self.lib.libusb_release_interface(self.handle,3)
            if self.detached:
                self.lib.libusb_attach_kernel_driver(self.handle,2)
            self.lib.libusb_close(self.handle)
            self.handle = None
        self.lib.libusb_exit(self.ctx)


def capture_fault(token_path):
    if not token_path.exists():
        return
    try:
        path = Path(__file__).with_name('a6-usb-http-rpc.py')
        spec = importlib.util.spec_from_file_location('http_rpc', path)
        rpc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rpc)
        rpc.capture_incident(token_path)
        print('Pre-recovery HTTP incident saved at ' +
              datetime.now(timezone.utc).isoformat(), flush=True)
    except Exception as error:
        # Report only exception classes, never request/token/body contents.
        reason = getattr(error, 'reason', None)
        detail = type(error).__name__ + (('/' + type(reason).__name__) if reason is not None else '')
        print('Pre-recovery HTTP incident unavailable (' + detail + ') at ' +
              datetime.now(timezone.utc).isoformat(), flush=True)


def receive(sock):
    data = bytearray()
    while b'\n' not in data:
        chunk = sock.recv(4096)
        if not chunk or len(data)+len(chunk)>16384:
            raise ValueError('Invalid broker request')
        data.extend(chunk)
    return json.loads(data.split(b'\n',1)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', type=Path, required=True)
    parser.add_argument('--hours', type=float, default=12)
    parser.add_argument('--incident-token', type=Path, default=
                        Path.home()/'.a6-usb-rpc.token')
    args = parser.parse_args()
    if not 0 < args.hours <= 24:
        parser.error('--hours must be greater than zero and at most 24')
    if args.socket.exists():
        parser.error('Broker socket already exists; stop its owner first')
    os.umask(0o077)
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    session = None
    retry_at = 0
    retry_delay = 5
    failed = False
    server = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        server.bind(str(args.socket));args.socket.chmod(0o600)
        server.listen(1);server.settimeout(.05)
        print('Persistent ACM broker ready; transport faults latch without rebinding',flush=True)
        deadline = time.monotonic()+args.hours*3600
        idle = b''
        while time.monotonic()<deadline:
            if session is None and not failed and time.monotonic() >= retry_at:
                try:
                    session = Session()
                    failed = False
                    retry_delay = 5
                    print('ACM session claimed at ' +
                          datetime.now(timezone.utc).isoformat(), flush=True)
                except USBUnavailable:
                    # Search while absent; no interface exists to rebind.
                    retry_at = time.monotonic() + retry_delay
                    retry_delay = 10 if retry_delay == 5 else 30
                except Exception:
                    failed = True
                    print('ACM setup fault latched at ' +
                          datetime.now(timezone.utc).isoformat(), flush=True)
            try:
                client,_ = server.accept()
            except TimeoutError:
                if session is not None and not failed:
                    try:
                        idle = (idle+session.read(50))[-65536:]
                    except USBTransportError as error:
                        save_failed_read(b'', 'Idle transport error; unframed input echoes omitted')
                        # Keep ownership: close/open would attach/detach cdc_acm
                        # repeatedly and change the endpoint state under test.
                        failed = True; idle = b''
                        print('ACM transport fault latched at ' +
                              datetime.now(timezone.utc).isoformat(), flush=True)
                        capture_fault(args.incident_token)
                continue
            with client:
                client.settimeout(5)
                try:
                    request = receive(client)
                    command,marker,timeout = request['command'],request.get('until'),request['timeout']
                    if not isinstance(command,str) or not 1<=len(command.encode())<=2048:
                        raise ValueError('Command length invalid')
                    if marker and (not isinstance(marker,str) or '\n' in marker or '\r' in marker):
                        raise ValueError('Marker invalid')
                    if not isinstance(timeout,(int,float)) or not 1<=timeout<=120:
                        raise ValueError('Timeout invalid')
                    if session is None or failed:
                        raise USBTransportError('USB transport unavailable; command omitted')
                    begin = 'A6_BROKER_BEGIN_' + secrets.token_hex(8)
                    split = len(begin)//2
                    framed = "printf '%s%s\\n' " + begin[:split] + ' ' + begin[split:] + '; ' + command
                    payload = prepare(framed,marker)
                    if len(payload) > 1000:
                        response = {'returncode':1, 'stdout':'',
                                    'stderr':'ACM shell line exceeds safe bound; upload a RAM script'}
                        client.sendall(json.dumps(response).encode()+b'\n')
                        idle = b''
                        continue
                    session.write(payload)
                    rc,output,error = collect(session.read,marker,timeout,idle,begin)
                    response={'returncode':rc,'stdout':output.decode(errors='replace'),'stderr':error}
                except USBTransportError:
                    first_fault = not failed
                    failed = True
                    print('ACM command transport fault latched at ' +
                          datetime.now(timezone.utc).isoformat(), flush=True)
                    if first_fault:
                        capture_fault(args.incident_token)
                    response={'returncode':1,'stdout':'','stderr':'ACM transport unavailable; command not replayed'}
                except Exception:
                    response={'returncode':1,'stdout':'','stderr':'Persistent ACM command failed'}
                idle = b''
                try:
                    client.sendall(json.dumps(response).encode()+b'\n')
                except OSError:
                    pass
    finally:
        server.close();args.socket.unlink(missing_ok=True)
        if session is not None:
            session.close()


if __name__=='__main__':
    main()
