"""Research-only endpoint-aware entity-body admission, not a memory bound.

No network calls on import. Existing endpoint methods, rule exceptions and
connection-only retry policy are inherited. Receive failures never retry.
urllib redirect/header buffering behavior is unchanged and not bounded here.
"""
import http.client
import json
import math
import socket
import time
import urllib.error
import urllib.request

from dfbench_client.game import GameClient as ParentClient, _safe_to_retry
from urllib.parse import urlsplit
from dfbench_client.errors import GameAPIError, GameUnavailable

MAX_BODY = 65536
FACT_BODY = 262144
KNOWN_QUERIES = frozenset(("stocks", "units", "jobs", "orders", "buildings", "zones",
                           "map", "manager_order_types", "workshop_types"))


def units_limit(method, path):
    """Post-inspection narrow policy; finite retained-corpus evidence only."""
    return FACT_BODY if method == "GET" and urlsplit(path).path == "/query/units" else MAX_BODY


def endpoint_limit(method, path):
    """Only exact read-only fact routes get the higher allowance.

    URL query parameters do not change the endpoint policy. No global mutation.
    """
    endpoint = urlsplit(path).path
    if method == "GET" and (endpoint == "/observe" or
                            endpoint in {"/query/" + q for q in KNOWN_QUERIES}):
        return FACT_BODY
    return MAX_BODY


MAX_DEPTH = 64
CHUNK = 8192


class ResponseAdmissionError(GameAPIError):
    """A response cannot certify an action; effects may already have happened."""


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite JSON number')


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('nonfinite JSON number')
    return number


def parse(raw, status, limit=MAX_BODY):
    try:
        if type(raw) is not bytes or len(raw) > limit:
            raise ValueError('entity byte limit')
        text = raw.decode('utf-8')
        depth = 0
        quoted = escaped = False
        for ch in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif ch == 92:
                    escaped = True
                elif ch == 34:
                    quoted = False
            elif ch == 34:
                quoted = True
            elif ch in (91, 123):
                depth += 1
                if depth > MAX_DEPTH:
                    raise ValueError('container depth limit')
            elif ch in (93, 125):
                depth -= 1
                if depth < 0:
                    raise ValueError('unmatched container')
        value = json.loads(text, object_pairs_hook=unique,
                           parse_constant=reject_constant, parse_float=finite)
        if not isinstance(value, dict):
            raise ValueError('response must be an object')
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ResponseAdmissionError('invalid or over-limit response JSON', status) from error


def read_body(source, status, limit=MAX_BODY):
    """Finite positive reads, including a sentinel; reject short declared bodies.

    Bounds returned entity bytes under compliant read(n), not buffers owned by
    urllib/the source. No decompression. Unknown-length EOF is the delimiter.
    """
    try:
        headers = getattr(source, 'headers', None)
        declared = None
        if headers is not None:
            encoding = headers.get('Content-Encoding', '').strip().lower()
            if encoding not in ('', 'identity'):
                raise ValueError('unsupported content encoding')
            # Chunk framing is handled by HTTPResponse, not counted as entity data.
            transfer = headers.get('Transfer-Encoding', '').strip().lower()
            if transfer not in ('', 'chunked'):
                raise ValueError('unsupported transfer encoding')
            length = headers.get('Content-Length')
            if not transfer and length is not None:
                if not length or any(ch not in '0123456789' for ch in length):
                    raise ValueError('invalid content length')
                declared = int(length)
                if declared > limit:
                    raise ValueError('declared body over limit')
        chunks = []
        total = 0
        while True:
            size = min(CHUNK, limit + 1 - total)
            piece = source.read(size)
            if type(piece) is not bytes or len(piece) > size:
                raise ValueError('invalid finite read result')
            if not piece:
                break
            chunks.append(piece)
            total += len(piece)
            if total > limit:
                raise ValueError('entity byte limit')
        if declared is not None and total != declared:
            raise ValueError('incomplete or inconsistent declared body')
        return b''.join(chunks)
    except (ValueError, OSError, http.client.HTTPException) as error:
        raise ResponseAdmissionError('response body receive/admission failed; do not replay action', status) from error


class GameClient(ParentClient):
    def __init__(self, *args, body_policy=endpoint_limit, **kwargs):
        super().__init__(*args, **kwargs)
        self.body_policy = body_policy

    def _request(self, method, path, body=None, timeout=None, accept_error_body=False, retries=None):
        limit = self.body_policy(method, path)
        if type(limit) is not int or not 1 <= limit <= FACT_BODY:
            raise ValueError("body policy must return 1..262144 bytes")
        url = self.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        retries = self.retries if retries is None else retries
        attempt = 0
        while True:
            t0 = time.time()
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                resp = urllib.request.urlopen(req, timeout=timeout or self.timeout)
            except urllib.error.HTTPError as error:
                # An answered HTTP error is not a failed connection. Its body read
                # must not escape cleanup or enter connection retry handling.
                status = error.code
                try:
                    raw = read_body(error, status, limit)
                finally:
                    error.close()
            except (urllib.error.URLError, ConnectionError, socket.timeout, http.client.HTTPException, OSError) as error:
                if attempt < retries and _safe_to_retry(method, error):
                    attempt += 1
                    time.sleep(min(self.backoff_s * 2 ** (attempt - 1), 30.0))
                    continue
                raise GameUnavailable(f'{method} {path}: {error}') from error
            else:
                with resp:
                    status = resp.status
                    raw = read_body(resp, status, limit)
            parsed = parse(raw, status, limit)
            if self.log:
                self.log({'t': t0, 'method': method, 'path': path, 'status': status,
                          'latency_s': round(time.time() - t0, 3), 'request': body,
                          'response': parsed})
            if status >= 400:
                if accept_error_body and ('error_code' in parsed or 'ok' in parsed):
                    parsed.setdefault('ok', False)
                else:
                    raise GameAPIError(f"{method} {path}: HTTP {status}: {parsed.get('error') or parsed}", status, parsed)
            if 'tick' in parsed or 'day' in parsed:
                self.last = {k: parsed.get(k) for k in ('day', 'tick', 'days_left', 'game_over', 'hands_off_in_days')
                             if k in parsed}
            return parsed
