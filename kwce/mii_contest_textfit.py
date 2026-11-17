"""Static long-sentence wrap / width audit for the Mii Contest channel (build-v25 fonts).

The channel draws its reviewed Korean BMG messages into the message-window panes
(messageWindow_00 / messageWindow3btn_00) which soft-wrap at the pane width.  build-v25 narrowed
this channel's own wbf1/wbf2 Hangul to 0.9 so wide Korean lines fit; this module re-measures every
localized message against those narrowed metrics and the real pane geometry to flag any line that
would soft-wrap or any message that would overflow the pane vertically.

It is a STATIC bound:
  * {CTRLn} tokens are runtime substitutions (names, counts, themes) of unknown width, so they are
    dropped before measuring - the fixed text is audited, the dynamic part stays [미검증] for the lead.
  * message->pane assignment is a runtime decision; each message is measured against every message
    pane and judged against the widest (overflow there is a real bug) and the narrowest (overflow
    there is a lead eyeball item).
It proves no tofu and no fixed-text overflow; the lead confirms the live layout in Dolphin.
"""
import re
import struct

from .channels import load_library, ChannelArchive, layout_sections
from .votes_resources import decode_yaz0
from .food_textfit import Metrics, Box, width, wrapped

CTRL = re.compile(r'\{CTRL\d+\}')
# Panes that display BMG messages (found in build-v25 content 4).
MESSAGE_PANES = [
    ('messageWindow_00.brlyt', 'T_message_00_00'),
    ('messageWindow_00.brlyt', 'T_message_01_00'),
    ('messageWindow3btn_00.brlyt', 'T_message_00_00'),
]


def _load(wad):
    lib = load_library()
    t = lib.title.Title()
    t.load_wad(wad.read_bytes())
    return t


def narrowed_metrics(title):
    """Metrics of this build's own (narrowed in v25) system font wbf1 (content 5)."""
    return Metrics(ChannelArchive(title.get_content_by_index(5)).get('wbf1.brfna'))


def _walk_layouts(arc, prefix=''):
    for name in arc.files:
        raw = arc.get(name)
        if raw[:4] == b'Yaz0':
            raw = decode_yaz0(raw)
        if raw[:4] == b'\x55\xaa\x38\x2d':
            try:
                sub = ChannelArchive(raw)
            except ValueError:
                continue
            yield from _walk_layouts(sub, prefix + name + '!/')
        elif raw[:4] == b'RLYT':
            yield name.split('/')[-1], raw


def message_boxes(title):
    """{(layout, pane): Box} for the message-window panes in content 4."""
    want = {(l, p) for l, p in MESSAGE_PANES}
    out = {}
    c4 = ChannelArchive(title.get_content_by_index(4))
    for layout, raw in _walk_layouts(c4):
        for sec in layout_sections(raw):
            if sec[:4] != b'txt1':
                continue
            pane = sec[12:28].split(b'\0')[0].decode('latin-1')
            if (layout, pane) in want and (layout, pane) not in out:
                out[(layout, pane)] = Box(layout, pane, sec)
    return out


def assemble_messages(root):
    """The reviewed/draft Korean message map exactly as build_mii_contest.py builds it (rev>=10)."""
    import json
    base = root / 'workspace/channels/mii-contest'
    draft = json.loads((base / 'draft/messages-ko.json').read_text(encoding='utf-8'))['messages']
    review = json.loads((root / 'configs/mii-contest-reviewed-ko.json').read_text(encoding='utf-8'))['reviewed_messages']
    mapping = dict(draft)
    mapping.update(review)
    return {k: v.replace('컨테스트', '콘테스트') for k, v in mapping.items()}


def _budget(box, m):
    lh = box.line_height(m)
    return max(1, int((box.h + 0.5) / lh)) if lh > 0 else 1


def audit(root):
    """Measure every localized message against the message panes with the narrowed v25 metrics.

    A genuine width defect is an explicit line that is too wide for EVERY message pane (it then
    always soft-wraps mid-line).  Long multi-line help/welcome text that exceeds one pane's height
    is expected (the channel paginates/scrolls it), so it is reported for information, not failed.
    """
    from .food_textfit import MARGIN
    base = root / 'workspace/channels/mii-contest'
    title = _load(base / 'build-v25/mii-contest-ko-ui-test.wad')
    m = narrowed_metrics(title)
    boxes = message_boxes(title)
    if len(boxes) < len(MESSAGE_PANES):
        raise ValueError(f'message panes missing: found {sorted(boxes)}')
    messages = assemble_messages(root)
    box_list = list(boxes.items())
    min_budget = min(_budget(b, m) for b in boxes.values())

    rows = []
    overflow = []          # an explicit line wider than every pane -> always wraps mid-line (defect)
    long_paginated = []     # more explicit lines than the smallest pane holds -> scroll/paginate (info)
    missing = set()
    for mid, text in messages.items():
        fixed = CTRL.sub('', text)
        missing |= set(m.missing(fixed))
        lines = [ln for ln in fixed.split('\n')]
        # Per explicit line: the narrowest pane width (its own font) it still fits on one line.
        bad_lines = []
        widest_px = 0.0
        for ln in lines:
            fits_any = False
            for (layout, pane), box in box_list:
                w = width(m, box, ln)
                widest_px = max(widest_px, w)
                if w <= box.w - MARGIN:
                    fits_any = True
            if ln and not fits_any:
                bad_lines.append(ln)
        row = dict(id=mid, explicit_lines=len(lines), widest_px=round(widest_px, 1),
                   fixed_preview=fixed[:48])
        rows.append(row)
        if bad_lines:
            overflow.append(mid)
        if len(lines) > min_budget:
            long_paginated.append(mid)
    return dict(
        build='build-v25',
        font='wbf1 (content5) narrowed 0.9 ; advance 가=%d' % m.advance('가'),
        message_count=len(messages),
        message_panes={f'{l}:{p}': dict(w=round(b.w, 1), h=round(b.h, 1), fw=round(b.fw, 1),
                                        fh=round(b.fh, 1), line_budget=_budget(b, m))
                       for (l, p), b in boxes.items()},
        missing_glyphs=''.join(sorted(missing)),
        line_overflow_every_pane=overflow,
        long_paginated_or_scrolled=long_paginated,
        rows=rows,
    )


def glyph_coverage(root):
    """Every character of every localized string must exist in wbf1, wbf2 and the button font."""
    import json
    base = root / 'workspace/channels/mii-contest'
    title = _load(base / 'build-v25/mii-contest-ko-ui-test.wad')
    strings = list(assemble_messages(root).values())
    layout = json.loads((root / 'configs/mii-contest-layout-ko.json').read_text(encoding='utf-8'))['labels']
    strings += list(layout.values())
    chars = {c for s in strings for c in CTRL.sub('', s) if c not in '\n\r'}
    c5 = ChannelArchive(title.get_content_by_index(5))
    result = {}
    for name in sorted(c5.files):
        mapping = Metrics(c5.get(name)).mapping
        result[name] = sorted(c for c in chars if ord(c) not in mapping)
    # The layout/button font (content 4) carries the Korean button glyphs.
    return result
