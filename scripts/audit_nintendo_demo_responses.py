"""Read-only, anonymous check of three public Nintendo Channel demo responses.

The input catalog and WiiLink server-source snapshots are local research copies.
Downloads stay in memory, are capped at 12 MB, and are never saved or printed.
The output contains aggregate lengths and integrity checks, not URLs or content.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'workspace/private'
HOST = 'dol.n.wiinoma.com'
DNS = '167.235.229.36'  # WiiLink's publicly documented resolver
LIMIT = 12_000_000


def integrity(data):
    if len(data) < 332:
        raise ValueError('Response too short for a demo header')
    length, crc = struct.unpack_from('>II', data, 4)
    offset, payload_size = struct.unpack_from('>II', data, 20)
    valid_span = 332 <= length <= len(data)
    if valid_span:
        body = bytearray(data[:length])
        body[8:12] = bytes(4)
        crc_ok = (zlib.crc32(body) & 0xffffffff) == crc
    else:
        crc_ok = False
    return {'bytes_received': len(data), 'declared_bytes': length,
            'version': data[2], 'size_matches': length == len(data),
            'payload_in_declared_span': offset >= 332 and payload_size > 0 and offset + payload_size == length,
            'crc_matches_declared_span': crc_ok}


def public_dns_ipv4():
    transaction = os.urandom(2)
    labels = b''.join(bytes([len(x)]) + x.encode('ascii') for x in HOST.split('.'))
    request = transaction + b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + labels + b'\x00\x00\x01\x00\x01'
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(6)
        sock.sendto(request, (DNS, 53))
        response, _ = sock.recvfrom(4096)
    if len(response) < 12 or response[:2] != transaction or response[3] & 15:
        raise ValueError('Public DNS query failed')

    def skip_name(pos):
        while response[pos]:
            if response[pos] & 192 == 192:
                return pos + 2
            pos += 1 + response[pos]
        return pos + 1

    pos = skip_name(12) + 4
    for _ in range(struct.unpack_from('>H', response, 6)[0]):
        pos = skip_name(pos)
        kind, _, _, size = struct.unpack_from('>HHIH', response, pos)
        pos += 10
        if kind == 1 and size == 4:
            return socket.inet_ntoa(response[pos:pos + 4])
        pos += size
    raise ValueError('Public DNS returned no IPv4 address')


def inputs():
    base = PRIVATE / 'wiilink-nintendo-generator-20261101/constants/nc.bin'
    source = PRIVATE / 'wiilink-nintendo-web-20261101/channel_static/main.py'
    catalog = base.read_bytes()
    count, offset = struct.unpack_from('>II', catalog, 0x5d)
    if count < 2 or offset + count * 352 > len(catalog):
        raise ValueError('Unexpected public catalog layout')
    expected = ('advance wars', 'burnout')
    ids = []
    for i, title_prefix in enumerate(expected):
        start = offset + i * 352
        name = catalog[start + 4:start + 66].decode('utf-16-be').split('\0', 1)[0]
        if not name.lower().startswith(title_prefix):
            raise ValueError('Public catalog ordering changed')
        ids.append(struct.unpack_from('>I', catalog, start)[0])
    tetris = []
    for i in range(count):
        start = offset + i * 352
        title = catalog[start + 4:start + 66].decode('utf-16-be').split('\0', 1)[0]
        subtitle = catalog[start + 66:start + 128].decode('utf-16-be').split('\0', 1)[0]
        if 'tetris' in title.lower() and 'push' in (title + ' ' + subtitle).lower():
            tetris.append(struct.unpack_from('>I', catalog, start)[0])
    if len(tetris) != 1:
        raise ValueError('Expected public Tetris demo entry missing or ambiguous')
    ids.append(tetris[0])
    match = re.search(r'/6/([A-Za-z0-9]+)/list/', source.read_text(encoding='utf-8'))
    if not match:
        raise ValueError('Public source route unavailable')
    return ids, match.group(1)


def fetch(ip, token, country, demo_id):
    path = f'/f/248/49125/1h/entus.wapp.wii.com/6/{token}/dstrial/{country}/en/{demo_id}.bin'
    connection = http.client.HTTPConnection(ip, 80, timeout=30)
    try:
        connection.request('GET', path, headers={'Host': HOST, 'User-Agent': 'KWCE-compatibility-check'})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('Public demo returned a non-200 status')
        expected = int(response.getheader('Content-Length', '-1'))
        if not 0 <= expected <= LIMIT:
            raise ValueError('Public demo length missing or exceeds limit')
        data = response.read(LIMIT + 1)
        if len(data) != expected:
            raise ValueError('Incomplete or oversized public response')
        result = integrity(data)
        result['http_status'] = response.status
        result['transport_length_matches'] = True
        return result, hashlib.sha256(data).digest()
    finally:
        connection.close()


def main():
    ids, token = inputs()
    ip = public_dns_ipv4()
    first_kr, hash_kr = fetch(ip, token, 'KR', ids[0])
    first_us, hash_us = fetch(ip, token, 'US', ids[0])
    second_kr, _ = fetch(ip, token, 'KR', ids[1])
    tetris_kr, _ = fetch(ip, token, 'KR', ids[2])
    print(json.dumps({'first_demo_kr': first_kr, 'first_demo_us': first_us,
                      'first_demo_kr_us_identical': hash_kr == hash_us,
                      'second_demo_kr': second_kr,
                      'tetris_demo_kr': tetris_kr}, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, IndexError, struct.error, http.client.HTTPException):
        raise SystemExit('Public demo integrity check unavailable; no response content printed.') from None
