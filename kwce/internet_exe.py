"""Executable (content 1, LZ11 DOL) changes for the Korean Internet Channel.

* SCGetProductArea of this title reads its own copy of the SDK area table
  (code byte + 4-byte name per entry). The KOR entry is given the USA code, so
  a Korean console takes the USA paths of this browser: English QWERTY with the
  English prediction dictionaries shipped in the USA WAD, US default favorites
  and the help_A Operations Guide. Console settings are never read or written.
* The software keyboard reads labels from an 8-column UTF-16 table (keyboard
  modes JP, US, UK, FR, DE, IT, ES, NL); language 9 uses the US column. The US
  strings are replaced in place inside their own slots.
* Local test builds only: service/update URLs become http://127.0.0.2/...
  (same or shorter, zero padded). Hardware builds keep every URL.
"""
import hashlib
import re
import struct

from .ppc_patch import to_file
from .wiiroom_formats import decompress_lz11, reencode_lz11_same_size

USA_RAW_SHA256 = None  # pinned by the build config (raw DOL after LZ11)
AREA_TABLE = bytes.fromhex('004a504e00015553410002455552000341555300044252410005545'
                           '74e0005524f4300064b4f520007484b4700084153490009'
                           '4c544e000a534146000b43484e00ff')
KOR_ENTRY = 35  # 8th 5-byte entry: code byte then 'KOR\0'
USA = 1
KEYBOARD_TABLE_VA = 0x809aa4f0
KEYBOARD_TABLE_WORDS = 80
LOCAL_HOST = 'http://127.0.0.2'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patch_area(raw):
    at = raw.find(AREA_TABLE)
    if at < 0 or raw.find(AREA_TABLE, at + 1) >= 0:
        raise ValueError('Expected one SDK product-area table')
    if raw[at + KOR_ENTRY:at + KOR_ENTRY + 5] != b'\x06KOR\x00':
        raise ValueError('KOR area entry differs')
    out = bytearray(raw)
    out[at + KOR_ENTRY] = USA
    return bytes(out), dict(table_offset=hex(at), entry='KOR', original_code=6, new_code=USA,
                            scope='this title only (its own SDK copy)', console_settings_changed=False)


def _string_starts(raw):
    at = to_file(raw, KEYBOARD_TABLE_VA, 4 * KEYBOARD_TABLE_WORDS)
    words = struct.unpack_from(f'>{KEYBOARD_TABLE_WORDS}I', raw, at)
    if any(not KEYBOARD_TABLE_VA - 0x400 <= w < KEYBOARD_TABLE_VA for w in words):
        raise ValueError('Keyboard string table pointers differ')
    return sorted(set(words) | {KEYBOARD_TABLE_VA})


def patch_keyboard(raw, rows):
    """rows: [{'va': '0x...', 'en': ..., 'ko': ...}] for the US column."""
    starts = _string_starts(raw)
    out = bytearray(raw)
    done = []
    for row in rows:
        va = int(row['va'], 16)
        if va not in starts:
            raise ValueError(f'Keyboard string {row["en"]!r} is not a table entry')
        end_va = next(s for s in starts if s > va)
        at = to_file(raw, va, end_va - va)
        slot = raw[at:at + end_va - va]
        text = slot.decode('utf-16-be').split('\0')[0]
        if text != row['en']:
            raise ValueError(f'Keyboard string at {row["va"]} is {text!r}, expected {row["en"]!r}')
        data = row['ko'].encode('utf-16-be') + b'\0\0'
        if len(data) > len(slot):
            raise ValueError(f'Korean keyboard label exceeds its slot: {row["ko"]!r}')
        out[at:at + len(slot)] = data + bytes(len(slot) - len(data))
        done.append(dict(va=row['va'], en=row['en'], ko=row['ko'], slot_bytes=len(slot)))
    return bytes(out), done


def _local(url):
    m = re.match(r'https?://[^/]+(.*)$', url)
    return LOCAL_HOST + (m.group(1) or '')


def patch_local_urls(raw, urls, targets=None):
    """urls: [{'url': ..., 'encoding': 'ascii'|'utf-16-be', 'count': n}] -> loopback.

    targets: optional {original url: exact local URL}; such a target must not
    contain a format directive (formatter arguments are then ignored)."""
    out = bytearray(raw)
    records = []
    targets = targets or {}
    for row in urls:
        enc = row['encoding']
        old = row['url'].encode(enc)
        local = targets.get(row['url'], _local(row['url']))
        if row['url'] in targets and ('%' in local or not local.startswith(LOCAL_HOST + '/')):
            raise ValueError('Exact local target must be a plain loopback URL')
        new = local.encode(enc)
        term = b'\0' if enc == 'ascii' else b'\0\0'
        if len(new) > len(old):
            raise ValueError('Local URL is longer than the original')
        hits = [m.start() for m in re.finditer(re.escape(old + term), raw)]
        if enc != 'ascii':
            hits = [h for h in hits if h % 2 == 0]
        if len(hits) != row['count']:
            raise ValueError(f'{row["url"]} occurs {len(hits)} times, expected {row["count"]}')
        for h in hits:
            out[h:h + len(old)] = new + bytes(len(old) - len(new))
        records.append(dict(original=row['url'], local=local, encoding=enc, occurrences=len(hits)))
    return bytes(out), records


def patch_utf16_labels(raw, rows):
    """rows: [{'va', 'en', 'ko'}] UTF-16 keyboard labels outside the 8-column table
    (v6: dictionary language abbreviations); each stays inside its own slot."""
    from .ppc_patch import utf16_slots
    out, done = utf16_slots(raw, [(int(r['va'], 16), r['en'], r['ko']) for r in rows])
    return out, [dict(va=r['va'], en=r['en'], ko=r['ko']) for r in rows]


def build_executable(compressed, config, *, local, translate_keyboard=True, local_targets=None, keyboard_rows=None, utf16_rows=None):
    raw = decompress_lz11(compressed)
    if sha256(raw) != config['raw_sha256']:
        raise ValueError('USA Internet Channel executable differs from the pinned source')
    raw2, area = patch_area(raw)
    if translate_keyboard:
        raw2, keyboard = patch_keyboard(raw2, config['keyboard'] if keyboard_rows is None else keyboard_rows)
    else:
        keyboard = []
    record = dict(raw_sha256=config['raw_sha256'], raw_size=len(raw), area=area, keyboard=keyboard,
                  keyboard_translated=translate_keyboard)
    if utf16_rows:
        raw2, record['keyboard_labels'] = patch_utf16_labels(raw2, utf16_rows)
    if local:
        raw2, record['local_urls'] = patch_local_urls(raw2, config['local_urls'], local_targets)
    else:
        record['local_urls'] = []
    packed = reencode_lz11_same_size(compressed, raw2)
    if decompress_lz11(packed) != raw2:
        raise ValueError('Executable LZ11 roundtrip')
    record.update(edited_raw_sha256=sha256(raw2), compressed_size=len(packed), original_compressed_size=len(compressed))
    return packed, record
