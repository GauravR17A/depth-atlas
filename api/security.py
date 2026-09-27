"""Bounded, process-local guards for the public, account-free science API.

These limits are not a distributed firewall. Proxy deployments must also impose
edge limits. No request bodies, raw client addresses or durable histories live
in this module.
"""
import asyncio
import hmac
import ipaddress
import math
import secrets
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

STARTUP_SCRIPT_HASH = "sha256-QczEk0LgQo7mnv86G+X4OYzXemr96gAeome7cOABO7Y="
SWAGGER_SCRIPT_HASH = "sha256-TsjSCX4yUK50HmnZXTe4FVW3iPTz1cIqzuXQu1ozcFU="
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' '" + STARTUP_SCRIPT_HASH + "'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "font-src 'self' data:; connect-src 'self'; worker-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
DOCS_CONTENT_SECURITY_POLICY = CONTENT_SECURITY_POLICY.replace(
    "script-src 'self' '" + STARTUP_SCRIPT_HASH + "'",
    "script-src 'self' https://cdn.jsdelivr.net '" + SWAGGER_SCRIPT_HASH + "'",
).replace("style-src 'self'", "style-src 'self' https://cdn.jsdelivr.net").replace(
    "img-src 'self'", "img-src 'self' https://fastapi.tiangolo.com"
)
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Frame-Options': 'DENY',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
    'Content-Security-Policy': CONTENT_SECURITY_POLICY,
}


@dataclass(frozen=True)
class ApiLimits:
    requests_per_minute: int = 360
    request_burst: int = 360
    calculations_per_minute: int = 60
    calculation_burst: int = 60
    concurrent_requests: int = 24
    concurrent_calculations: int = 4
    clients: int = 2048
    idle_seconds: float = 600
    body_timeout_seconds: float = 15


class Admission:
    """Thread-safe bounded token buckets; failed requests consume admission."""
    def __init__(self, limits: ApiLimits, clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self._entries = {}
        self._salt = secrets.token_bytes(32)
        self._lock = threading.Lock()

    def take(self, client: str, calculation: bool) -> int:
        now, limits = self.clock(), self.limits
        key = hmac.digest(self._salt, client.encode(), 'sha256')
        with self._lock:
            self._entries = {k: v for k, v in self._entries.items() if now-v[0] < limits.idle_seconds}
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= limits.clients:
                    return 10
                entry = (now, float(limits.request_burst), float(limits.calculation_burst))
            elapsed = max(0, now-entry[0])
            reads = min(limits.request_burst, entry[1]+elapsed*limits.requests_per_minute/60)
            writes = min(limits.calculation_burst, entry[2]+elapsed*limits.calculations_per_minute/60)
            waits = [max(0, (1-reads)*60/limits.requests_per_minute)]
            if calculation:
                waits.append(max(0, (1-writes)*60/limits.calculations_per_minute))
            retry = math.ceil(max(waits))
            self._entries[key] = (now, reads if retry else reads-1, writes if retry or not calculation else writes-1)
            return retry


def client_identity(scope, headers, vercel: bool) -> str:
    # Vercel overwrites this header at its edge. Never trust it on a direct host.
    value = headers.get('x-vercel-forwarded-for', '') if vercel else ''
    if value:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            pass
    client = scope.get('client')
    return str(client[0]) if client else 'unknown'


def body_limit(path: str) -> int:
    if path in {'/api/instruments/import', '/api/instruments/inspect'}:
        return 2_000_000
    if path == '/api/wider/replay':
        return 4_500_000
    if path.startswith('/api/investigations/') or '/evidence/imported/' in path or path.endswith('/features/support'):
        return 3_000_000
    return 65_536


class ApiGuard:
    def __init__(self, app, limits: ApiLimits | None = None, vercel: bool = False):
        self.app, self.limits, self.vercel = app, limits or ApiLimits(), vercel
        self.admission = Admission(self.limits)
        self.requests = threading.BoundedSemaphore(self.limits.concurrent_requests)
        self.calculations = threading.BoundedSemaphore(self.limits.concurrent_calculations)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, send)
        path = scope['path'].rstrip('/')
        raw_headers = scope.get('headers', [])
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k, v in raw_headers}
        calculation = scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}

        async def reject(status, code, message, retry=None):
            envelope = {'error': {'code': code, 'message': message,
                         'request_id': scope.get('state', {}).get('request_id', 'unavailable')}}
            response = JSONResponse(envelope, status_code=status,
                                    headers={'Retry-After': str(retry)} if retry else {})
            await response(scope, receive, send)

        if sum(len(k)+len(v) for k, v in raw_headers) > 32_768 or len(scope.get('query_string', b'')) > 8192:
            return await reject(431, 'request_headers', 'This request has too much header or URL data.')
        if calculation:
            origin = headers.get('origin')
            try:
                origin_mismatch = origin and urlsplit(origin).netloc.lower() != headers.get('host', '').lower()
            except ValueError:
                origin_mismatch = True
            if headers.get('sec-fetch-site') == 'cross-site' or origin_mismatch:
                return await reject(403, 'request_origin', 'Open the app on this website to send this request.')
        retry = self.admission.take(client_identity(scope, headers, self.vercel), calculation)
        if retry:
            return await reject(429, 'rate_limited', 'Too many requests. Wait briefly and try again.', retry)
        acquired = self.requests.acquire(blocking=False)
        acquired_calculation = calculation and acquired and self.calculations.acquire(blocking=False)
        if not acquired or (calculation and not acquired_calculation):
            if acquired:
                self.requests.release()
            return await reject(429, 'service_busy', 'The service is busy. Wait briefly and try again.', 2)
        try:
            limit = body_limit(path)
            lengths = [v for k, v in raw_headers if k.lower() == b'content-length']
            if len(lengths) > 1 or (lengths and (len(lengths[0]) > 10 or not lengths[0].isdigit())):
                return await reject(400, 'invalid_request', 'The request length is invalid.')
            if lengths and int(lengths[0]) > limit:
                return await reject(413, 'file_limits', 'This request exceeds its byte limit.')
            if headers.get('content-encoding', 'identity').lower() != 'identity':
                return await reject(422, 'unsupported_format', 'Compressed request bodies are not supported.')
            # Read before Pydantic/JSON parsing, including requests without a length.
            # The endpoint receives the same bytes and the original disconnect.
            body = bytearray()
            deadline = time.monotonic()+self.limits.body_timeout_seconds
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    return await reject(408, 'request_timeout', 'The upload did not finish in time. Try a smaller request or a faster connection.')
                try:
                    event = await asyncio.wait_for(receive(), remaining)
                except asyncio.TimeoutError:
                    return await reject(408, 'request_timeout', 'The upload did not finish in time. Try a smaller request or a faster connection.')
                if event['type'] == 'http.disconnect':
                    return
                chunk = event.get('body', b'')
                if len(body)+len(chunk) > limit:
                    return await reject(413, 'file_limits', 'This request exceeds its byte limit.')
                body.extend(chunk)
                if not event.get('more_body', False):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            await self.app(scope, bounded_receive, send)
        finally:
            if acquired_calculation:
                self.calculations.release()
            self.requests.release()
