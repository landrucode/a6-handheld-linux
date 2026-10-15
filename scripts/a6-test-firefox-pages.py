#!/usr/bin/env python3
"""Collect sandbox evidence and a bounded real-page workload via USB-only Marionette."""
import argparse
import json
import os
from pathlib import Path
import socket
import time

ROOT = Path(__file__).resolve().parents[1]
PAGES = ('https://en.wikipedia.org/wiki/Linux',
         'https://developer.mozilla.org/en-US/docs/Web/JavaScript',
         'https://www.bbc.co.uk/news')

class Marionette:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=120)
        self.stream = self.sock.makefile('rb')
        self.sequence = 0
        self.hello = self.receive()
        if self.hello.get('marionetteProtocol') != 3:
            raise ValueError('Unexpected Marionette protocol')

    def receive(self):
        digits = b''
        while True:
            byte = self.stream.read(1)
            if not byte:
                raise EOFError('Browser connection closed')
            if byte == b':':
                break
            if not byte.isdigit() or len(digits) >= 9:
                raise ValueError('Invalid browser response frame')
            digits += byte
        length = int(digits)
        if length > 2 * 1024 * 1024:
            raise ValueError('Oversized browser response')
        data = self.stream.read(length)
        if len(data) != length:
            raise EOFError('Incomplete browser response')
        return json.loads(data)

    def command(self, name, parameters=None):
        started = time.monotonic()
        print('Browser command: ' + name, flush=True)
        self.sequence += 1
        data = json.dumps([0, self.sequence, name, parameters or {}]).encode()
        self.sock.sendall(str(len(data)).encode() + b':' + data)
        response = self.receive()
        if response[:2] != [1, self.sequence]:
            raise ValueError('Unexpected browser response sequence')
        if response[2]:
            raise RuntimeError(json.dumps(response[2]))
        print('Browser command completed: ' + name + ' (' + str(round(time.monotonic()-started, 3)) + 's)', flush=True)
        return response[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=2828)
    parser.add_argument('--workload', choices=('heavy', 'docs'), default='heavy')
    parser.add_argument('--pages', type=int, choices=(2, 3), default=3)
    args = parser.parse_args()
    os.umask(0o077)
    output = ROOT / 'build/session-logs/firefox-pages.private.json'
    evidence = {'pages': [], 'text_measurement': 'textContent'}
    client = Marionette('192.168.7.2', args.port)
    try:
        client.command('WebDriver:NewSession', {'capabilities': {'alwaysMatch': {'acceptInsecureCerts': False, 'pageLoadStrategy': 'eager'}}})
        client.command('WebDriver:SetTimeouts', {'pageLoad': 60000, 'script': 30000})
        client.command('WebDriver:Navigate', {'url': 'about:support'})
        script = "return Array.from(document.querySelectorAll('#sandbox-tbody tr')).map(r=>({key:r.querySelector('th').getAttribute('data-l10n-id'),value:r.querySelector('td').textContent.trim()}));"
        rows = []
        for _ in range(20):
            rows = client.command('WebDriver:ExecuteScript', {'script': script, 'args': []})['value']
            if rows:
                break
            time.sleep(.5)
        evidence['sandbox'] = rows
        checks = {row['key']: row['value'] for row in rows}
        required = ('has-seccomp-bpf', 'has-seccomp-tsync', 'has-user-namespaces', 'can-sandbox-content')
        if any(checks.get(key) != 'true' for key in required):
            raise RuntimeError('about:support full sandbox prerequisites not active: ' + json.dumps(checks))
        level = checks.get('effective-content-sandbox-level', '0')
        if int(level) < 4:
            raise RuntimeError('Unexpected effective content sandbox level: ' + level)
        print('about:support reports active namespace and seccomp sandbox support, level ' + level)
        output.write_text(json.dumps(evidence, indent=2) + '\n')
        active = client.command('WebDriver:GetWindowHandle')['value']
        existing = [active] + [h for h in client.command('WebDriver:GetWindowHandles') if h != active]
        while len(existing) > args.pages:
            handle = existing.pop()
            client.command('WebDriver:SwitchToWindow', {'handle': handle})
            client.command('WebDriver:CloseWindow')
        pages = PAGES if args.workload == 'heavy' else ('https://developer.mozilla.org/en-US/docs/Web/JavaScript', 'https://www.kernel.org/')
        for url in pages[:args.pages]:
            started = time.monotonic()
            page = {'url': url}
            evidence['pages'].append(page)
            try:
                handle = existing.pop(0) if existing else client.command('WebDriver:NewWindow', {'type': 'tab'})['handle']
                page['handle'] = handle
                client.command('WebDriver:SwitchToWindow', {'handle': handle})
                client.command('WebDriver:Navigate', {'url': url})
                page['result'] = client.command('WebDriver:ExecuteScript', {
                    'script': 'return {url:location.href,title:document.title,state:document.readyState,textLength:document.body?.textContent.length};', 'args': []})['value']
            except Exception as error:
                page['error'] = str(error)
            page['seconds'] = round(time.monotonic() - started, 3)
            output.write_text(json.dumps(evidence, indent=2) + '\n')
            print('Page attempt recorded: ' + url + ' (' + str(page['seconds']) + 's)')
    finally:
        output.write_text(json.dumps(evidence, indent=2) + '\n')
        client.sock.close()
    if any('error' in page for page in evidence['pages']):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
