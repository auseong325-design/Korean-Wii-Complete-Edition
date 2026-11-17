"""Photo Prints RC6 wave-2 fixes (build-v14 / hardware-v10).

content 2 (layout.arc.LZ, boot-safe resource):
  A. centre push-button captions whose text origin is Left (textPosition%3==0);
     the shorter Korean label otherwise sits left of the button centre.
  B. "OK" push-button captions -> "확인".
  C. tilde U+007E -> U+FF5E (the channel font draws U+007E tiny/raised; U+FF5E
     is the centred wave the Japanese original used), applied only where the
     wider glyph still fits the box.
  D. order-screen label panes: char spacing -> 0 (match "완성 예상").

content 1 (DOL, in-place UTF-16BE literals, re-encoded to the same raw size):
  E. board sender self-name "디지털카메라 프린트채널" -> "...프린트 채널" (spacing).
  F. card address format drops the Japanese postal mark "〒".
  G. untranslated error-dialog title "<error>" -> "오류".
Content 1 changes -> lead Dolphin verification required.
"""
import re
import struct

from .channels import (ChannelArchive, layout_sections, rebuild_layout,
                       replace_textbox, textbox)
from .wiiroom_formats import decompress_lz11, reencode_lz11_same_size

# ---------------------------------------------------------------------------
# content 1 (DOL)
# ---------------------------------------------------------------------------
DOL_LITERALS = [
    (0x802b4a80, "디지털카메라 프린트채널", "디지털카메라 프린트 채널"),
    (0x804a28ba, "〒%ls\n%ls%ls%ls%ls", "%ls\n%ls%ls%ls%ls"),
    (0x804a292a, "<error>", "오류"),
]
_TOK = lambda s: re.findall(r'%[-+ #0-9.*hlLzjt]*[a-zA-Z%]', s)


def _dol_ranges(dol):
    ranges = []
    for base, addr, size, cnt in ((0, 0x48, 0x90, 7), (0x1c, 0x64, 0xac, 11)):
        offs = struct.unpack_from(f'>{cnt}I', dol, base)
        adrs = struct.unpack_from(f'>{cnt}I', dol, addr)
        szs = struct.unpack_from(f'>{cnt}I', dol, size)
        ranges += [(o, a, s) for o, a, s in zip(offs, adrs, szs) if s]
    return ranges


def _va_to_off(dol, va):
    for o, a, s in _dol_ranges(dol):
        if a <= va < a + s:
            return o + (va - a)
    raise ValueError(f'VA {hex(va)} not mapped in DOL')


def patch_dol(dol):
    """Apply the fixed-slot UTF-16BE literal edits in place (zero-padded)."""
    out = bytearray(dol)
    applied = []
    for va, expect, new in DOL_LITERALS:
        at = _va_to_off(dol, va)
        end = at
        while out[end:end + 2] != b'\0\0':
            end += 2
        slot = end
        while out[slot:slot + 2] == b'\0\0' and slot - at < 4096:
            slot += 2
        cur = bytes(out[at:end]).decode('utf-16-be')
        if cur != expect:
            raise ValueError(f'DOL literal at {hex(va)} is {cur!r}, expected {expect!r}')
        if _TOK(expect) != _TOK(new):
            raise ValueError(f'Format-token mismatch at {hex(va)}')
        data = new.encode('utf-16-be') + b'\0\0'
        if len(data) > slot - at:
            raise ValueError(f'New literal at {hex(va)} needs {len(data)} > slot {slot - at}')
        out[at:slot] = data + bytes(slot - at - len(data))
        applied.append(dict(va=hex(va), before=expect, after=new,
                            slot_bytes=slot - at, used_bytes=len(data)))
    return bytes(out), applied


def patch_content1(content1):
    """content1 is the LZ11 stream; return (new LZ11 stream, record)."""
    dol = decompress_lz11(content1)
    new_dol, applied = patch_dol(dol)
    new_c1 = reencode_lz11_same_size(content1, new_dol)
    if decompress_lz11(new_c1) != new_dol:
        raise ValueError('content 1 LZ11 roundtrip failed')
    return new_c1, dict(dol_literals=applied, raw_size=len(dol))


# ---------------------------------------------------------------------------
# content 2 (layout.arc.LZ)
# ---------------------------------------------------------------------------
CAPTION_PREFIX = ('BtnTA', 'PshTA')
LABEL_PANES = {'itemName', 'unitPrice', 'totalCount', 'totalPrice',
               'fixAddPrice', 'fixTotalPrice', 'otodoke'}


def _set_byte(sec, off, value):
    b = bytearray(sec)
    b[off] = value
    return bytes(b)


def _set_f32(sec, off, value):
    b = bytearray(sec)
    struct.pack_into('>f', b, off, value)
    return bytes(b)


def patch_layout(layout_bytes, font):
    """Return (edited archive bytes, record). `font` = font_rodan_28.brfna."""
    from . import photoprints_textfit as tf
    metrics = tf.Metrics(font)
    archive = ChannelArchive(layout_bytes)
    rec = dict(centered=[], ok_to_confirm=[], tilde=[], tilde_skipped=[], charspace=[])
    for name in list(archive.files):
        if not name.endswith('.brlyt'):
            continue
        short = name.split('/')[-1]
        sections = layout_sections(archive.get(name))
        touched = False
        for i, sec in enumerate(sections):
            tb = textbox(sec)
            if tb is None:
                continue
            pane, txt = tb
            new = sec
            changed = False
            label = txt.strip()

            # (B) OK -> 확인 on push-button captions
            if label == 'OK' and pane.startswith('BtnTA'):
                new = replace_textbox(new, '확인')
                txt = '확인'
                label = '확인'
                changed = True
                rec['ok_to_confirm'].append(f'{short}:{pane}')

            # (C) tilde U+007E -> U+FF5E, only where it still fits the box
            if '\u007e' in txt:
                cand = txt.replace('\u007e', '\uff5e')
                trial = replace_textbox(new, cand)
                box = tf.Box(short, pane, trial)
                fw = struct.unpack_from('>f', trial, 100)[0]
                if not tf.overflow_lines(metrics, box, cand, fw=fw):
                    new = trial
                    txt = cand
                    changed = True
                    rec['tilde'].append(f'{short}:{pane}')
                else:
                    rec['tilde_skipped'].append(f'{short}:{pane}')

            # (A) centre Left-origin push-button captions (+ the 처음부터 panes)
            tp = new[84]
            if (pane.startswith(CAPTION_PREFIX) or txt.strip() == '처음부터') and tp % 3 == 0:
                new = _set_byte(new, 84, tp - tp % 3 + 1)
                changed = True
                rec['centered'].append(f'{short}:{pane}(tp{tp}->{tp - tp % 3 + 1})')

            # (D) order-screen label char spacing -> 0
            if pane in LABEL_PANES:
                cs = struct.unpack_from('>f', new, 108)[0]
                if cs > 0:
                    new = _set_f32(new, 108, 0.0)
                    changed = True
                    rec['charspace'].append(f'{short}:{pane}(cs{cs:.0f}->0)')

            if changed:
                sections[i] = new
                touched = True
        if touched:
            archive = ChannelArchive(archive.replace(name, rebuild_layout(archive.get(name), sections)))
    rec['summary'] = {k: len(v) for k, v in rec.items() if isinstance(v, list)}
    return archive.data, rec
