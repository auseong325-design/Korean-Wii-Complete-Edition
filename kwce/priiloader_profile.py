"""Build the per-card KWCE disc profiles (gc-only.ini / gc-dvd.ini) on the PC, for any Priiloader.

Priiloader 0.8.2 turns a hash/patch token into the minimal big-endian bytes of its value (0x00474300
-> 47 43 00); Priiloader 0.10 keeps every hex pair (-> 00 47 43 00) [문헌: DacoTaco/priiloader
hacks.cpp]. neutral_fragment() re-splits each hash/patch line so that no token starts with a zero
byte and every token has an even number of hex digits: both parsers then read the same bytes, and
those bytes equal what 0.8.2 read from the original fragment (the hardware-tested behaviour).

build_profile() keeps every non-KWCE section of the card's own apps/priiloader/hacks_hash.ini
byte for byte (any Priiloader grammar), drops old KWCE disc sections and appends the neutral
fragment. With no card file the profile holds only the KWCE sections: on Priiloader 0.10 a fresh
install has no NAND hack list either, and its hacks menu needs this SD file anyway.
"""
import re

KWCE_SECTION = re.compile(r'^\[KWCE (?:GC|DVD):[^\]\n]*\]\n.*?(?=^\[|\Z)', re.M | re.S)
TOKEN = re.compile(r'0x[0-9a-fA-F]{1,8}')


def legacy_bytes(token):
    """Priiloader 0.8.2: value -> minimal big-endian bytes (0 -> nothing)."""
    if not TOKEN.fullmatch(token):
        raise ValueError('invalid token ' + token)
    n = int(token, 16)
    return n.to_bytes((n.bit_length() + 7) // 8, 'big')


def modern_bytes(token):
    """Priiloader 0.10: two hex digits per byte, an odd last digit is one byte."""
    if not token.startswith('0x') or not 4 <= len(token) <= 10:
        raise ValueError('invalid token ' + token)
    h = token[2:]
    return bytes(int(h[i:i + 2], 16) for i in range(0, len(h), 2))


def split_neutral(data):
    """Tokens of 1-4 bytes, none starting with 0x00, covering data exactly."""
    out, i = [], 0
    while i < len(data):
        if data[i] == 0:
            raise ValueError('a zero byte cannot start a token (run of zeros too long)')
        for n in (4, 3, 2, 1):
            if i + n <= len(data) and (i + n == len(data) or data[i + n] != 0):
                break
        else:
            raise ValueError('cannot split bytes neutrally')
        out.append('0x' + data[i:i + n].hex()); i += n
    return out


def neutral_fragment(text):
    """Same bytes under Priiloader 0.8.2 and 0.10; equal to what 0.8.2 read from text."""
    lines = []
    for line in text.replace('\r\n', '\n').split('\n'):
        key, eq, value = line.partition('=')
        if eq and key in ('hash', 'patch'):
            data = b''.join(legacy_bytes(t) for t in value.split(','))
            toks = split_neutral(data)
            assert b''.join(legacy_bytes(t) for t in toks) == data == b''.join(modern_bytes(t) for t in toks)
            line = key + '=' + ','.join(toks)
        lines.append(line)
    return '\n'.join(lines)


def build_profile(card, fragment):
    """card: bytes of the card's hacks_hash.ini or None. Returns the CRLF profile bytes."""
    new = neutral_fragment(fragment.decode('ascii')).strip('\n')
    names = re.findall(r'^\[([^\]\n]+)\]', new, re.M)
    if not names or any(not n.startswith(('KWCE GC:', 'KWCE DVD:')) for n in names):
        raise ValueError('a disc fragment may contain only KWCE disc sections')
    text = (card or b'').decode('latin1').replace('\r\n', '\n').lstrip('﻿ï»¿')
    text = text[text.find('['):] if '[' in text else ''   # the installer needs '[' first; drops a comment preamble
    text = KWCE_SECTION.sub('', text).rstrip('\n')
    return ((text + '\n' if text else '') + new + '\n').replace('\n', '\r\n').encode('latin1')


def other_sections(raw):
    """Non-KWCE sections of a profile, for the 'user hacks kept' check."""
    text = raw.decode('latin1').replace('\r\n', '\n')
    return KWCE_SECTION.sub('', text).rstrip('\n')
