"""Codex Desktop IPC bridge (port of desktop-ipc.cjs and desktop-route.cjs). Blocking; call from a worker thread."""
import json
import os
import re
import socket
import struct
import time
import uuid
from pathlib import Path
from urllib.parse import quote

THREAD = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


def desktop_url(thread):
    if not isinstance(thread, str) or not THREAD.match(thread):
        raise ValueError('Invalid Desktop thread')
    return 'codex://threads/' + quote(thread)


def _endpoint():
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'ipc' / 'ipc.sock'


class DesktopClient:
    def __init__(self, endpoint=None):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(str(endpoint or _endpoint()))
        except OSError:
            raise RuntimeError('Could not connect to Codex Desktop')
        self.buffer, self.client_id = b'', 'initializing-client'
        try:
            response = self.request('initialize', {'clientType': 'orbit-agent-pet'})
            if response.get('resultType') != 'success' or not (response.get('result') or {}).get('clientId'):
                raise RuntimeError
            self.client_id = response['result']['clientId']
        except (RuntimeError, OSError):
            self.close()
            raise RuntimeError('Desktop initialization failed')

    def _send(self, message):
        body = json.dumps(message).encode()
        self.sock.sendall(struct.pack('<I', len(body)) + body)

    def _frame(self, deadline):
        while True:
            if len(self.buffer) >= 4:
                size = struct.unpack('<I', self.buffer[:4])[0]
                if size > 8 * 1024 * 1024:
                    raise RuntimeError('Desktop connection closed')
                if len(self.buffer) >= size + 4:
                    frame, self.buffer = self.buffer[4:size + 4], self.buffer[size + 4:]
                    return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self.sock.settimeout(remaining)
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError('Desktop connection closed')
            self.buffer += chunk

    def request(self, method, params, timeout=5, **options):
        request_id = str(uuid.uuid4())
        version = 2 if method == 'thread-follower-start-turn' else 1 if method == 'thread-owner-discovery' else 0
        self._send({'type': 'request', 'requestId': request_id, 'sourceClientId': self.client_id, 'version': version,
                    'method': method, 'params': params, **options})
        deadline = time.monotonic() + timeout
        while True:
            try:
                frame = self._frame(deadline)
            except (TimeoutError, socket.timeout):
                raise RuntimeError('Desktop did not acknowledge submission. Check the thread before retrying.'
                                   if method == 'thread-follower-start-turn' else 'Desktop thread is not ready')
            try:
                message = json.loads(frame)
            except ValueError:
                continue
            if message.get('type') == 'client-discovery-request':
                self._send({'type': 'client-discovery-response', 'requestId': message.get('requestId'), 'response': {'canHandle': False}})
            elif message.get('type') == 'response' and message.get('requestId') == request_id:
                return message

    def close(self):
        self.sock.close()


def send_desktop_message(thread, prompt):
    client = DesktopClient()
    try:
        owner = None
        for attempt in range(8):
            response = client.request('thread-owner-discovery', {'hostId': 'local', 'conversationId': thread})
            if response.get('resultType') == 'success':
                if (response.get('result') or {}).get('supportsUntrustedAppInput') is not True or not response.get('handledByClientId'):
                    raise RuntimeError('This Desktop version cannot accept messages from Orbit')
                owner = response['handledByClientId']
                break
            if attempt == 7:
                raise RuntimeError('Open this thread in Codex Desktop')
            time.sleep(.35)
        response = client.request('thread-follower-start-turn', {
            'conversationId': thread,
            'turnStart': {'request': {'threadId': thread, 'clientUserMessageId': str(uuid.uuid4()),
                                      'input': [{'type': 'text', 'text': prompt, 'text_elements': []}]},
                          'context': {'inheritThreadSettings': True, 'useAppServerPermissionDefault': True}},
        }, timeout=30, targetClientId=owner, timeoutMs=30000)
        if response.get('resultType') != 'success':
            raise RuntimeError(response.get('error') or 'Desktop rejected the message')
        return response.get('result')
    finally:
        client.close()
