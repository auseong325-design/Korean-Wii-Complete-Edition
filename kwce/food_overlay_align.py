"""Food: keep overlay panes on the blank runs of translated sentences.

Several Food screens leave a run of spaces in a centred sentence and draw a separate pane
on top of it: the A button and heart pictures in the two product-panel help dialogs, the
waiting-time number, the check-mark button. The Japanese designers placed those panes at
the centre of the blank run. A Korean sentence has a different width before and after the
run, so the run moves while the pane stays (real console: the A button drawn over the next
letter, the minutes drawn over the unit). Each listed pane is moved horizontally by exactly
the distance its blank run moved: new x = old x + (Korean run centre - Japanese run centre),
both measured with the font each text is drawn in. Text, sizes and vertical positions are
not changed.
"""
import struct

from .channels import ChannelArchive, layout_sections, rebuild_layout, textbox
from . import food_textfit as ft

# (archive, layout, text pane) -> [(line index, run ordinal on that line, overlay pane)]
OVERLAYS = {
    ('DtestDialog.arc', 'Dialog/blyt/dialogue_layout.brlyt', 'dic_T_msgH_00'):
        [(1, 0, 'dic_P_iconH00_00'), (2, 0, 'dic_P_iconH00_01'), (3, 0, 'dic_P_iconH00_02')],
    ('DtestDialog.arc', 'Dialog/blyt/dialogue_layout.brlyt', 'dic_T_msgH_00a'):
        [(6, 0, 'dic_P_iconH00_03')],
    ('DtestDialog.arc', 'Dialog/blyt/dialogue_layout.brlyt', 'dic_T_msgH_01'):
        [(0, 0, 'dic_P_iconH01_00'), (1, 0, 'dic_P_iconH01_01'), (1, 1, 'dic_P_iconH01_02'), (3, 0, 'dic_P_iconH01_03')],
    ('DtestOrder.arc', 'Order/blyt/11_m_layout.brlyt', '11_T_Mname_00'):
        [(1, 0, '11_T_Iname_00')],
    ('DtestOrder.arc', 'Order/blyt/08_m_layout.brlyt', '08h_T_txt'):
        [(0, 0, '08h_T_OKtxt')],
}
# Overlay panes that are siblings of their text pane (same parent): their x is compared and moved
# relative to the text pane's own x. The others are children of the text pane.
SIBLINGS = {'11_T_Iname_00', '08h_T_OKtxt'}
MODEL_TOLERANCE = 6.0   # the stock pane must sit this close to the stock run centre, or the model is wrong


def runs(metrics, box, text):
    """{(line, ordinal): centre x of each run of 2+ spaces that has text after it}, centred lines."""
    out = {}
    for li, line in enumerate(text.split('\n')):
        total = ft.width(metrics, box, line); i = n = 0
        while i < len(line):
            if line[i] == ' ' and line[i + 1:i + 2] == ' ':
                j = i
                while j < len(line) and line[j] == ' ': j += 1
                if j < len(line):
                    before = ft.width(metrics, box, line[:i]) + (box.cs if i else 0)
                    out[(li, n)] = -total / 2 + before + ft.width(metrics, box, line[i:j]) / 2
                    n += 1
                i = j
            else:
                i += 1
    return out


def pane_index(sections):
    return {s[12:28].split(b'\0')[0].decode('ascii'): i for i, s in enumerate(sections)
            if s[:4] in (b'pan1', b'pic1', b'txt1', b'wnd1', b'bnd1')}


def plan(stock_layout, built_layout, text_pane, rows, stock_metrics, korean_metrics):
    """[(overlay pane, old x, new x, stock run centre, Korean run centre)] for one text pane."""
    stock, built = layout_sections(stock_layout), layout_sections(built_layout)
    si, bi = pane_index(stock), pane_index(built)
    sbox, bbox = ft.Box('', text_pane, stock[si[text_pane]]), ft.Box('', text_pane, built[bi[text_pane]])
    if (sbox.position, sbox.align) != (bbox.position, bbox.align): raise ValueError('Text alignment changed: ' + text_pane)
    ja = runs(stock_metrics, sbox, textbox(stock[si[text_pane]])[1])
    ko = runs(korean_metrics, bbox, textbox(built[bi[text_pane]])[1])
    out = []
    for line, ordinal, pane in rows:
        if (line, ordinal) not in ja or (line, ordinal) not in ko: raise ValueError(f'Blank run missing: {text_pane} line {line}')
        old = struct.unpack_from('>f', built[bi[pane]], 0x24)[0]
        if struct.unpack_from('>f', stock[si[pane]], 0x24)[0] != old: raise ValueError('Overlay pane already moved: ' + pane)
        base = struct.unpack_from('>f', built[bi[text_pane]], 0x24)[0] if pane in SIBLINGS else 0.0
        if struct.unpack_from('>f', stock[si[text_pane]], 0x24)[0] != struct.unpack_from('>f', built[bi[text_pane]], 0x24)[0]:
            raise ValueError('Text pane moved: ' + text_pane)
        if abs(old - base - ja[(line, ordinal)]) > MODEL_TOLERANCE:
            raise ValueError(f'{pane} is not at the stock blank run ({old - base:.1f} vs {ja[(line, ordinal)]:.1f})')
        out.append((pane, old, round(old + ko[(line, ordinal)] - ja[(line, ordinal)], 1), ja[(line, ordinal)], ko[(line, ordinal)]))
    return out


def align(content2, stock_content2, stock_metrics, korean_metrics):
    """Return (new content 2, record). content2: built Korean resources; stock_content2: original."""
    outer, stock_outer = ChannelArchive(content2), ChannelArchive(stock_content2)
    record = []; by_arc = {}
    for (arc, layout, text_pane), rows in OVERLAYS.items(): by_arc.setdefault(arc, {}).setdefault(layout, []).append((text_pane, rows))
    result = content2
    for arc, layouts in by_arc.items():
        name = next(n for n in outer.files if n.endswith('/' + arc) or n == arc)
        inner, stock_inner = ChannelArchive(outer.get(name)), ChannelArchive(stock_outer.get(name))
        packed = outer.get(name)
        for layout, panes in layouts.items():
            data = inner.get(layout); sections = layout_sections(data); index = pane_index(sections)
            for text_pane, rows in panes:
                for pane, old, new, ja, ko in plan(stock_inner.get(layout), data, text_pane, rows, stock_metrics, korean_metrics):
                    s = bytearray(sections[index[pane]]); struct.pack_into('>f', s, 0x24, new); sections[index[pane]] = bytes(s)
                    record.append(dict(layout=layout, text=text_pane, pane=pane, x=[old, new],
                                       stock_run=round(ja, 1), korean_run=round(ko, 1)))
            packed = ChannelArchive(packed).replace(layout, rebuild_layout(data, sections))
        result = ChannelArchive(result).replace(name, packed)
    return result, record
