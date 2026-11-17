"""Revision 28: natural Hangul width in the Mii Contest '#' message boxes.

The channel draws '#' boxes at x = BMG INF1 attribute (+4, percent) x 0.01 x font width
(executable 0x8028c930; see docs/channels/mii-contest.md v22-v25). The US table condenses
long English lines (attribute histogram in build-v25: 90 x328, 80 x62, 70 x32, 60 x65,
50 x18, ...). Korean lines are far shorter, so the same attributes draw them narrow and
squashed: on the user's console (2026-10-29) '현재 출품할 수 있는 / 콘테스트가 없습니다.'
(message 923) is drawn at 70 %.

For every message below 100 % the attribute is raised to the largest value <= 100 at which
the widest Korean line is no wider than the widest English line was at the original
attribute (the width Nintendo fitted the box to), measured with the channel's fonts:
English with the US system font, Korean with this build's (v25-narrowed) font. It is never
lowered; messages whose lines carry runtime escapes keep a 5 % reserve.
"""
import math

CAP = 100
RESERVE = 0.95
HANGUL_NARROWED_ADVANCE = 20     # v25 narrow_hangul: CWDH (1,20,22) -> (1,18,20)


def _messages(bmg):
    inf = bmg.find(b'INF1')
    dat = bmg.find(b'DAT1')
    total = int.from_bytes(bmg[inf + 8:inf + 10], 'big')
    stride = int.from_bytes(bmg[inf + 10:inf + 12], 'big')
    out = []
    for i in range(total):
        at = inf + 16 + i * stride
        off = int.from_bytes(bmg[at:at + 4], 'big')
        width = int.from_bytes(bmg[at + 4:at + 6], 'big')
        s = dat + 8 + off
        lines, run, escaped = [], [], False
        while s + 1 < len(bmg):
            c = int.from_bytes(bmg[s:s + 2], 'big')
            if c == 0:
                break
            if c == 0x1a:
                n = bmg[s + 2]
                if n < 4:
                    raise ValueError(f'BMG escape length {n} in message {i}')
                escaped = True
                s += n
                continue
            if c == 0x0a:
                lines.append(''.join(run))
                run = []
            else:
                run.append(chr(c))
            s += 2
        lines.append(''.join(run))
        out.append((at + 4, width, lines, escaped))
    return out


def _px(metrics, line, hangul_advance=None):
    total = 0
    for ch in line:
        if hangul_advance and 0xac00 <= ord(ch) <= 0xd7a3:
            total += hangul_advance
        else:
            total += metrics.advance(ch)
    return total


def widen(korean_bmg, english_bmg, en_metrics, ko_metrics, hangul_advance=HANGUL_NARROWED_ADVANCE):
    """Return (new BMG bytes, record)."""
    ko = _messages(korean_bmg)
    en = _messages(english_bmg)
    if len(ko) != len(en):
        raise ValueError('Korean and English BMG message counts differ')
    data = bytearray(korean_bmg)
    raised, histogram = [], {}
    for index, ((attr_at, width, ko_lines, ko_esc), (_, en_width, en_lines, en_esc)) in enumerate(zip(ko, en)):
        if width != en_width:
            raise ValueError(f'message {index}: width attribute differs from the US table')
        if not 0 < width < CAP:
            continue
        ko_px = max(_px(ko_metrics, l, hangul_advance) for l in ko_lines)
        en_px = max(_px(en_metrics, l) for l in en_lines)
        if ko_px <= 0 or en_px <= 0:
            continue
        budget = en_px * width / 100.0
        if ko_esc or en_esc:
            budget *= RESERVE
        best = min(CAP, math.floor(budget * 100.0 / ko_px))
        if best > width:
            data[attr_at:attr_at + 2] = best.to_bytes(2, 'big')
            raised.append(index)
            histogram[f'{width}->{best}'] = histogram.get(f'{width}->{best}', 0) + 1
    return bytes(data), dict(rule='raise <100% INF1 widths to the English-fitted width, cap 100, never lower',
                             raised_messages=len(raised), changes=dict(sorted(histogram.items())),
                             hangul_advance=hangul_advance, reserve_for_escapes=RESERVE)
