"""Static text fit for Food BRLYT textboxes and dialog strings (Korean wbf1 metrics).

nw4r's TextWriter advances each character by its CWDH charWidth scaled by
fontSize.width / FINF.width and adds charSpace between characters; the channel
wraps at the textbox width, so a Korean line wider than its box breaks
mid-word and the spilled line overlaps the pane below (real-Wii video 14:54:
first welcome page title). Line height = linefeed * fontSize.height /
FINF.height + lineSpace. A Korean string fits when every explicit line is
narrower than the box (no wrap) and it uses no more lines than the Japanese
did in the same pane with the stock Japanese font.
"""
import struct

from .channels import ChannelArchive, layout_sections, textbox

MARGIN = 2.0       # layout units kept free at the right edge (float rounding, outline)
MIN_SCALE = 0.80   # narrowest horizontal font scale accepted when a line is squeezed


class Metrics:
    def __init__(self, rfna):
        from .channel_font import font_data
        if rfna[:4] not in (b'RFNA', b'RFNT'):
            raise ValueError('Expected an RFNA/RFNT font')
        blocks, self.mapping, self.widths = font_data(b'RFNT' + rfna[4:])
        _, finf = blocks[b'FINF']
        self.linefeed = struct.unpack_from('>b', finf, 0x09)[0]
        self.alter = struct.unpack_from('>H', finf, 0x0a)[0]
        self.default_advance = struct.unpack_from('>b', finf, 0x0e)[0]
        self.height, self.width = finf[0x1c], finf[0x1d]

    def advance(self, ch):
        g = self.mapping.get(ord(ch))
        if g is None:                       # drawn with the alternate glyph (blank in the Korean font)
            g = self.alter
        return self.widths[g][2] if g < len(self.widths) else self.default_advance

    def missing(self, text):
        return sorted({c for c in text if c not in '\n\r' and ord(c) not in self.mapping})


class Box:
    """Geometry of one txt1 pane (pane size at 0x44, font size/char space/line space at 0x64)."""
    def __init__(self, name, pane, section):
        self.name, self.pane = name, pane
        self.w, self.h = struct.unpack_from('>ff', section, 0x44)
        self.fw, self.fh, self.cs, self.ls = struct.unpack_from('>ffff', section, 0x64)
        self.position, self.align = section[0x54], section[0x55]

    def line_height(self, m):
        return m.linefeed * self.fh / m.height + self.ls


def width(m, box, line, fw=None):
    if not line:
        return 0.0
    return sum(m.advance(c) for c in line) * (fw or box.fw) / m.width + box.cs * (len(line) - 1)


def wrapped(m, box, text, fw=None):
    """Lines after the writer's character wrap at the box width."""
    out = []
    for line in text.split('\n'):
        run = ''
        for c in line:
            if run and width(m, box, run + c, fw) > box.w:
                out.append(run); run = c
            else:
                run += c
        out.append(run)
    return out


def fit(m, mj, box, ja, ko, fw=None):
    """Fit report of Korean `ko` replacing Japanese `ja` in `box` (m: Korean font, mj: stock font)."""
    lines = ko.split('\n'); widths = [width(m, box, line, fw) for line in lines]
    budget = len(wrapped(mj, box, ja))
    return dict(pane=box.pane, box=[round(box.w, 1), round(box.h, 1)], font=[round(box.fw, 2), round(box.fh, 2)],
                scale=round((fw or box.fw) / box.fw, 3), widest=round(max(widths), 1),
                lines=len(lines), budget=budget, missing=''.join(m.missing(ko)),
                ok=not m.missing(ko) and max(widths) <= box.w - MARGIN and len(wrapped(m, box, ko, fw)) <= budget)


def fit_scale(m, box, ko):
    """Horizontal font scale (<=1) that makes every explicit line narrower than box.w - MARGIN."""
    limit = box.w - MARGIN; worst = max(ko.split('\n'), key=lambda l: width(m, box, l))
    full = width(m, box, worst)
    if full <= limit:
        return 1.0
    spaces = box.cs * max(len(worst) - 1, 0)
    return max(0.0, (limit - spaces) / (full - spaces))


def boxes(layout, panes=None):
    """{pane: (Box, current text, section index)} for the txt1 panes of one raw RLYT."""
    out = {}
    for i, sec in enumerate(layout_sections(layout)):
        tb = textbox(sec)
        if tb and (panes is None or tb[0] in panes):
            out[tb[0]] = (Box('', tb[0], sec), tb[1], i)
    return out


def set_font_width(section, fw):
    out = bytearray(section); struct.pack_into('>f', out, 0x64, fw)
    return bytes(out)


def korean_metrics():
    from .channel_korean_font import korean_shared_fonts
    return Metrics(ChannelArchive(korean_shared_fonts()[0]).get('wbf1.brfna'))


def stock_metrics(content3):
    """Metrics of the stock Japanese wbf1 (title content 3) for the Japanese line budget."""
    return Metrics(ChannelArchive(content3).get('wbf1.brfna'))



DIALOG_BOXES = (('DtestDialog.arc', 'Dialog/blyt/W_dialog_layout.brlyt', 'DwT_win_txt_00'),
                ('DtestDialog.arc', 'Dialog/blyt/dialogue_layout.brlyt', 'dic_T_msg00'))


def dialog_boxes(content2):
    """The two message panes executable dialog strings are drawn in (stock content 2)."""
    outer = ChannelArchive(content2); out = []
    for arc, layout, pane in DIALOG_BOXES:
        out.append(boxes(ChannelArchive(outer.get('Dtest/' + arc)).get(layout), {pane})[pane][0])
    return out


def dialog_fit(m, mj, panes, ja, ko):
    """Executable message rule: in every message pane where all Japanese lines fit, every Korean
    line fits too (no wrap), and the Korean has no more lines than the Japanese."""
    bad = []
    for box in panes:
        if max(width(mj, box, line) for line in ja.split('\n')) <= box.w:
            worst = max(width(m, box, line) for line in ko.split('\n'))
            if worst > box.w - MARGIN:
                bad.append((box.pane, round(worst, 1), round(box.w, 1)))
    if len(ko.split('\n')) > len(ja.split('\n')):
        bad.append(('lines', len(ko.split('\n')), len(ja.split('\n'))))
    return bad
