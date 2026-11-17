"""Strict guards and task normalization for capability-zero News replay."""
import hashlib
import json
import struct
from pathlib import Path
from urllib.parse import urlsplit

NEWS_TITLE = (0x00010002, 0x48414745)
NEWS_URL = b'http://news.wiilink.ca/v2/1/136/news.bin'
NEWS_US_URL = b'http://news.wiilink.ca/v2/1/049/news.bin'


def validate_news_tasks(data):
    if len(data) != 0xf800 or data[:8] != bytes.fromhex('5763446c00000001'):
        raise ValueError('Invalid download list')
    count = 0
    for i in range(120):
        e = data[2048 + 512*i:2560 + 512*i]
        if not int.from_bytes(e[12:16], 'big'):
            continue
        flags = int.from_bytes(e[4:8], 'big')
        url = e[180:416].split(b'\0')[0]
        parsed = urlsplit(url.decode('ascii'))
        if (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                and parsed.port == 9 and flags & 32):
            continue
        if (set(struct.unpack_from('>II', e, 8)) != set(NEWS_TITLE)
                or url not in (NEWS_URL, NEWS_US_URL) or flags & (8 | 32)):
            raise ValueError('Unexpected active download task')
        count += 1
    if count != 1:
        raise ValueError('Expected exactly one public News task')
    return count


def normalize_news_tasks(data):
    """Disable non-News jobs recreated by the menu; never repair a News job."""
    if len(data)!=0xf800 or data[:8]!=bytes.fromhex('5763446c00000001'):
        raise ValueError('Invalid download list')
    out=bytearray(data);changed=0
    for i in range(120):
        at=2048+512*i;row=data[at:at+512]
        if not int.from_bytes(row[12:16],'big')or set(struct.unpack_from('>II',row,8))==set(NEWS_TITLE):continue
        struct.pack_into('>I',out,at+4,int.from_bytes(row[4:8],'big')|32)
        url=f'http://127.0.0.1:9/phase0-disabled/task-{i}'.encode('ascii')
        out[at+180:at+416]=url+bytes(236-len(url))
        changed+=out[at:at+512]!=row
    validate_news_tasks(out)
    return bytes(out),changed


def validate_feed(root):
    root = Path(root).resolve()
    meta = json.loads((root / 'feed-manifest.json').read_text(encoding='utf-8'))
    if meta.get('channel') != 'news' or meta.get('host') != 'news.wiilink.ca':
        raise ValueError('Wrong local feed identity')
    rows = meta['files']
    expected = {f'news.wiilink.ca/v2/1/136/news.bin.{h:02d}' for h in range(24)}
    if meta.get('alternate_country') == 49:
        expected |= {f'news.wiilink.ca/v2/1/049/news.bin.{h:02d}' for h in range(24)}
    if len(rows) != len(expected) or {r['path'] for r in rows} != expected:
        raise ValueError('Expected all 24 News replay files')
    for row in rows:
        p = root / row['path']
        if p.is_symlink() or p.is_junction() or not p.resolve().is_relative_to(root):
            raise ValueError('Indirect feed path refused')
        raw = p.read_bytes()
        if (not 320 < len(raw) <= 8*1024*1024 or len(raw) != row['size']
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError('Local feed hash/size mismatch')
    return len(rows)


def patch_text():
    # The patched host maps only to the capability-zero local feed server.
    return ('[WC24Patch]\n$Main\nnews.wiilink.ca:127.0.0.2:1\n\n'
            '[WC24Patch_Enabled]\n$Main\n')


def validate_location_glyphs(root, available):
    from .channels import load_library
    from .news_data import strings
    load_library()
    from libWiiPy.archive import decompress_lz77
    required = set()
    for p in (Path(root) / 'news.wiilink.ca/v2/1').glob('*/news.bin.*'):
        for kind, _, _, text in strings(decompress_lz77(p.read_bytes()[320:])):
            if kind == 'location':
                required.update(text)
    if required - set(available):
        raise ValueError('Replay needs additional location glyphs; build before launch')
    return len(required)
