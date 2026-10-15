#!/usr/bin/env python3
"""Actual phone firewall proof: TCP 1..65535, common UDP, positive controls.

Imported by the connection runner. Scans only its newly leased phone address.
Private addresses and rule counters go to ignored evidence, never stdout.
"""
import asyncio
import secrets
import socket
import time

TCP_CONTROL = 49152
UDP_CONTROL = 49153
UDP_PORTS = (53, 67, 68, 123, 137, 138, 161, 500, 1900, 4500, 5353, UDP_CONTROL)


async def scan_tcp(address):
    """Connect scanning requires no raw socket privileges on the laptop."""
    queue = asyncio.Queue()
    for port in range(1, 65536):
        queue.put_nowait(port)
    opened = []
    errors = []

    async def worker():
        while not queue.empty():
            port = queue.get_nowait()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            try:
                await asyncio.wait_for(asyncio.get_running_loop().sock_connect(
                    sock, (address, port)), timeout=0.4)
                opened.append(port)
            except (TimeoutError, ConnectionRefusedError):
                pass
            except OSError as exc:
                # A closed/filtered port is not a host routing/resource error.
                if exc.errno not in (104, 110):
                    errors.append((port, exc.errno))
            finally:
                sock.close()

    await asyncio.gather(*(worker() for _ in range(256)))
    if errors:
        raise RuntimeError('TCP scanner encountered host/network errors')
    return sorted(opened)


def tcp_open(address, port):
    try:
        with socket.create_connection((address, port), timeout=2):
            return True
    except (TimeoutError, ConnectionRefusedError):
        return False


def udp_probe(address, port, payload):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(1)
        sock.connect((address, port))
        sock.send(payload)
        try:
            return sock.recv(4096)
        except (TimeoutError, ConnectionRefusedError):
            return None


def prove(serial, address, nft, socat, evidence):
    # Two listeners exist only for this bounded, explicitly authorized test.
    # A phone-side timer independently restores DROP if the laptop disconnects.
    stem = '/tmp/a6-firewall-control-' + secrets.token_hex(4)
    serial('busybox setsid busybox timeout 180 ' + socat +
           ' TCP4-LISTEN:49152,bind=' + address + ',reuseaddr,fork EXEC:/bin/cat '
           '</dev/null >' + stem + '.tcp.log 2>&1 & echo $! >' + stem + '.tcp.pid; '
           'busybox setsid busybox timeout 180 ' + socat +
           ' UDP4-RECVFROM:49153,bind=' + address + ',reuseaddr,fork EXEC:/bin/cat '
           '</dev/null >' + stem + '.udp.log 2>&1 & echo $! >' + stem + '.udp.pid; sleep 1')
    try:
        token = secrets.token_bytes(24)
        if tcp_open(address, TCP_CONTROL) or udp_probe(address, UDP_CONTROL, token) is not None:
            raise RuntimeError('Firewall failed to block test listeners')
        # Insert a named temporary chain ahead of normal rules. Removing it
        # atomically restores the complete policy; no ruleset flush is needed.
        serial(nft + ' add chain ip a6_guard positive_control')
        # The first jump carries a handle, but do not rely on its numeric value.
        # Flushing this temporary chain makes it return into the DROP policy.
        serial("busybox setsid busybox sh -c 'sleep 15; " + nft +
               " flush chain ip a6_guard positive_control' </dev/null >" +
               stem + '.timer.log 2>&1 & echo $! >' + stem + '.timer.pid')
        # Arm restoration before granting the temporary exception.
        serial(nft + ' add rule ip a6_guard positive_control accept; ' + nft +
               ' insert rule ip a6_guard input iifname \'"wlan0"\' jump positive_control')
        positive = tcp_open(address, TCP_CONTROL) and udp_probe(address, UDP_CONTROL, token) == token
        # Bound the permissive interval even when a test assertion fails.
        serial(nft + ' flush chain ip a6_guard positive_control; echo CONTROL_CLOSED')
        if not positive:
            raise RuntimeError('Firewall positive control failed; scan would be inconclusive')
        print('Firewall positive controls passed: blocked, reachable during control, blocked again')
        if tcp_open(address, TCP_CONTROL) or udp_probe(address, UDP_CONTROL, token) is not None:
            raise RuntimeError('Firewall did not restore DROP after positive control')
        # Keep listeners alive during the full scan: a real firewall failure
        # would be detected, rather than hidden by the absence of services.
        started = time.monotonic()
        opened = asyncio.run(scan_tcp(address))
        udp_responses = [p for p in UDP_PORTS if udp_probe(address, p, token) is not None]
        evidence.append('FIREWALL_TCP_SCANNED=65535 OPEN=' + repr(opened) +
                        ' UDP_PROBED=' + repr(UDP_PORTS) + ' UDP_RESPONSES=' +
                        repr(udp_responses) + ' SECONDS=' + str(round(time.monotonic()-started, 1)))
        if opened or udp_responses:
            raise RuntimeError('Firewall scan found an accessible inbound port')
        serial(nft + ' list table ip a6_guard')
        print('Firewall scan passed: all 65,535 TCP ports and 12 UDP ports blocked or closed')
    finally:
        serial(nft + ' flush chain ip a6_guard positive_control 2>/dev/null; '
               'for f in ' + stem + '.tcp.pid ' + stem + '.udp.pid ' + stem +
               '.timer.pid; do test ! -f "$f" || kill -TERM -- "-$(cat "$f")" 2>/dev/null || :; done; '
               'sleep 1; echo CONTROL_LISTENERS_STOPPED')
