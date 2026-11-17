"""Write configs/food-executable-v7-ko.json: the v6 table with the lead's wave-2 review wording.

  .venv\\Scripts\\python.exe scripts\\make_food_translations_v7.py [--check]

Lead Dolphin review of build-v4 (2026-10-28): the operator name mixed
transliteration and translation ("유메노마치소조위원회(주)"). One form is used
everywhere from v7 on: 유메노마치소조이인카이(주) (transliterated name + the usual
Korean abbreviation of 주식회사). Same checks as v6 for every changed string.
"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, sha256
from kwce import bspatch, food_textfit as tf
import make_food_translations_v3 as gen
from make_food_translations_v6 import TOKEN

V6 = ROOT / 'configs/food-executable-v6-ko.json'
OUT = ROOT / 'configs/food-executable-v7-ko.json'
COMPANY = '유메노마치소조이인카이(주)'
REVISED = {
 'これよりお店のリクエストを\n“夢の街創造委員会(株)”へ送信します。\nよろしいですか？':
   '지금부터 가게 요청을\n“' + COMPANY + '”에\n보냅니다. 계속할까요?',
}


def build():
    v6 = json.loads(V6.read_text(encoding='utf-8'))
    lib = load_library(); title = lib.title.Title()
    title.load_wad((ROOT / 'workspace/channels/food/originals/food-japan-v512.wad').read_bytes())
    wl = bspatch.apply(title.get_content_by_index(1), gen.PATCH.read_bytes())
    if sha256(wl) != v6['source_sha256']:
        raise SystemExit('WiiLink executable differs from the v6 table source')
    glyphs = gen.korean_font_map(); m = tf.korean_metrics(); mj = tf.stock_metrics(title.get_content_by_index(3))
    panes = tf.dialog_boxes(title.get_content_by_index(2))
    for src, tgt in REVISED.items():
        if src not in v6['utf16']:
            raise SystemExit('Revised source not in the v6 table: ' + repr(src[:16]))
        if any(len(tgt.encode('utf-16-be')) + 2 > e - s for s, e in gen.literal_slots(wl, src)):
            raise SystemExit('Korean exceeds its slot: ' + repr(tgt[:16]))
        if TOKEN.findall(src) != TOKEN.findall(tgt) or [c for c in tgt if c != '\n' and ord(c) not in glyphs]:
            raise SystemExit('Format tokens or glyphs: ' + repr(tgt[:16]))
        if tf.dialog_fit(m, mj, panes, src, tgt):
            raise SystemExit('Korean dialog line does not fit: ' + repr(tgt[:16]))
    table = dict(v6['utf16']); table.update(REVISED)
    return dict(source=v6['source'], source_sha256=v6['source_sha256'],
                note=v6['note'] + ' v7: operator name in one form, ' + COMPANY + ' (scripts/make_food_translations_v7.py).',
                utf16=table)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1) + '\n'
    if args.check:
        if OUT.read_text(encoding='utf-8') != text:
            raise SystemExit('configs/food-executable-v7-ko.json differs from the generator')
        print('PASS: v7 executable table matches its generator'); return
    if OUT.exists():
        raise SystemExit('Existing v7 table preserved; use --check')
    OUT.write_text(text, encoding='utf-8')
    print('Wrote', OUT.name, 'with', len(json.loads(text)['utf16']), 'strings (%d revised)' % len(REVISED))


if __name__ == '__main__':
    main()
