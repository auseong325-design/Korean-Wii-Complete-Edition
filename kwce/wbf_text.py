"""Render text with the Wii system font (RFNA wbf1/wbf2) into a coverage image.

Used for HOME Menu label textures that the System Menu ships as pre-rendered
I4 images (tx_*_KOR.tpl): new labels are drawn with the same font so they sit
beside the original ones. Glyphs come from the verified local 43K shared font;
no font bytes are written out except inside the generated textures.
"""
import struct
from . import cx_huffman
from .channel_font import font_data
from .channels import load_library
from .korean_font_narrow import _untile_i4


class WiiFontRenderer:
    def __init__(self, rfna):
        load_library()
        if rfna[:4] != b'RFNA':raise ValueError('Expected RFNA font')
        blocks, self.mapping, self.widths = font_data(b'RFNT' + rfna[4:])
        _, finf = blocks[b'FINF'];_, tglp = blocks[b'TGLP']
        self.height, self.width, self.ascent = finf[0x1c], finf[0x1d], finf[0x1e]
        self.default = struct.unpack_from('>H', finf, 0x0a)[0]
        self.cw, self.ch, self.baseline = tglp[8], tglp[9], tglp[10]
        sheets, fmt, self.cols, self.rows, self.sw, self.sh = struct.unpack_from('>6H', tglp, 16)
        if fmt != 0x8000:raise ValueError('Only compressed I4 RFNA sheets supported')
        pos = struct.unpack_from('>I', tglp, 28)[0];self.streams = []
        for _ in range(sheets):
            n = struct.unpack_from('>I', rfna, pos)[0];self.streams.append(rfna[pos + 4:pos + 4 + n]);pos += 4 + n
        self.cache = {}

    def _sheet(self, index):
        from PIL import Image
        if index not in self.cache:
            px = _untile_i4(cx_huffman.decompress(self.streams[index]), self.sw, self.sh)
            self.cache[index] = Image.frombytes('L', (self.sw, self.sh), bytes(px))
        return self.cache[index]

    def glyph(self, code):
        """(cell image, left, glyph width, advance) at the font's own size."""
        g = self.mapping.get(code)
        if g is None:g = self.mapping.get(self.default, 0)
        per = self.cols * self.rows;sheet = self._sheet(g // per);item = g % per
        x = (item % self.cols) * (self.cw + 1);y = (item // self.cols) * (self.ch + 1)
        left, gw, adv = self.widths[g]
        left = left - 256 if left > 127 else left
        return sheet.crop((x, y, x + gw, y + self.ch)), left, gw, adv

    def line_width(self, text, scale=1.0, spacing=0.0):
        w = 0.0
        for ch in text:w += self.glyph(ord(ch))[3] * scale + spacing
        return w - spacing if text else 0.0

    def render(self, text, size, canvas, centre=None, spacing=0.0, line_gap=0):
        """Draw `text` (\\n allowed) at pixel height `size` centred on `centre` (default: canvas centre).
        canvas: PIL 'L' image, coverage is max-combined. Returns the bounding box used."""
        from PIL import Image, ImageChops
        scale = size / self.height;lines = text.split('\n')
        line_h = self.ch * scale + line_gap;total_h = line_h * len(lines) - line_gap
        cx, cy = centre if centre else (canvas.size[0] / 2, canvas.size[1] / 2)
        top = cy - total_h / 2;box = [canvas.size[0], canvas.size[1], 0, 0]
        for row, line in enumerate(lines):
            pen = cx - self.line_width(line, scale, spacing) / 2;y0 = top + row * line_h
            for ch in line:
                cell, left, gw, adv = self.glyph(ord(ch))
                if gw and ch != ' ':
                    w = max(1, round(gw * scale));h = max(1, round(self.ch * scale))
                    img = cell.resize((w, h), Image.LANCZOS)
                    x = round(pen + left * scale);y = round(y0)
                    region = canvas.crop((x, y, x + w, y + h))
                    canvas.paste(ImageChops.lighter(region, img), (x, y))
                    box = [min(box[0], x), min(box[1], y), max(box[2], x + w), max(box[3], y + h)]
                pen += adv * scale + spacing
        return box
