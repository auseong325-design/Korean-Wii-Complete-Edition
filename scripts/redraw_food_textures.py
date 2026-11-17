"""Redraw Korean into the text-bearing Food label textures listed in
configs/food-textures-v1-ko.json. Stages modified archives under
workspace/private/food-textures-staged/ and renders a before/after proof sheet.
Does NOT modify any build (build-v1 is create-once and already tested);
integrating redrawn content 2 into a build-v2 is a follow-up pending Dolphin
placement verification. Only text-only label textures are touched.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce.tpl import decode
from kwce.food_texture import redraw_label, korean_font_renderer, unwrap

CFG = ROOT / 'configs/food-textures-v1-ko.json'
STAGE = ROOT / 'workspace/private/food-textures-staged'
SHEET = ROOT / 'workspace/private/food-textures-proof.png'


def main():
    cfg = json.loads(CFG.read_text(encoding='utf-8'))
    lib = load_library(); t = lib.title.Title()
    t.load_wad((ROOT / 'workspace/channels/food/originals/food-japan-v512.wad').read_bytes())
    a2 = ChannelArchive(t.get_content_by_index(2))
    renderer = korean_font_renderer()
    STAGE.mkdir(parents=True, exist_ok=True)
    pairs = []; record = {}
    for arc, labels in cfg['labels'].items():
        name = 'Dtest/' + arc
        inner = ChannelArchive(a2.get(name)); done = []
        for tpl, spec in labels.items():
            raw = inner.get(tpl)
            if raw[:4] != bytes.fromhex('0020af30'):
                continue  # only raw TPLs handled here
            before = decode(raw, 0).convert('RGBA')
            new, meta = redraw_label(raw, spec['ko'], renderer)
            inner = ChannelArchive(inner.replace(tpl, new))
            after = decode(new, 0).convert('RGBA')
            pairs.append((tpl.split('/')[-1], spec['ko'], before, after))
            done.append(dict(tpl=tpl, ko=spec['ko'], **meta))
        (STAGE / arc).write_bytes(inner.compact()); record[arc] = done
    (STAGE / 'staged.json').write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
    # proof sheet: before | after rows
    from PIL import Image, ImageDraw, ImageFont
    cw, ch = 220, 48; rows = len(pairs)
    sheet = Image.new('RGB', (cw * 2 + 10, ch * rows + 4), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype('arial.ttf', 10)
    except Exception:
        font = ImageFont.load_default()
    def tile(img):
        c = Image.new('RGBA', (cw, ch), (255, 255, 255, 255))
        dd = ImageDraw.Draw(c)
        for y in range(0, ch, 8):
            for x in range(0, cw, 8):
                if (x // 8 + y // 8) % 2:
                    dd.rectangle([x, y, x + 7, y + 7], fill=(210, 210, 210, 255))
        im = img.copy(); im.thumbnail((cw - 4, ch - 4)); c.alpha_composite(im, ((cw - im.width) // 2, (ch - im.height) // 2))
        return c.convert('RGB')
    for i, (nm, ko, b, a) in enumerate(pairs):
        sheet.paste(tile(b), (0, ch * i)); sheet.paste(tile(a), (cw + 10, ch * i))
        d.text((2, ch * i + 1), nm[:22], fill=(255, 220, 0), font=font)
    sheet.save(SHEET)
    print('staged archives', len(record), 'redrawn labels', len(pairs), 'proof', SHEET.name)


if __name__ == '__main__':
    main()
