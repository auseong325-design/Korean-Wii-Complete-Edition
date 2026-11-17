"""Write configs/food-executable-v6-ko.json: the v4 table plus the remaining Japanese dialogs.

  .venv\\Scripts\\python.exe scripts\\make_food_translations_v6.py [--check]

Added (static audit of build-v4, wave 2): the "no home address registered" guide
the real Wii showed before address setting (Japanese with blank kanji; the
Dolphin profile never reaches it because its fictional pd.dat is seeded), the
phone-number checks, the WiiConnect24 update notice, "no shop delivers today",
the two-hour timeout and the two shop-request prompts. Every source is a whole
zero-terminated UTF-16BE literal of the WiiLink Demae_1_Japan DOL; every target
fits its zero-padded slot, keeps format tokens, uses only Korean wbf1 glyphs
and fits the message panes (kwce.food_textfit.dialog_fit). --check only
verifies that the written file equals what this script would write.
"""
import argparse, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, sha256
from kwce import bspatch, food_textfit as tf
import make_food_translations_v3 as gen

V4 = ROOT / 'configs/food-executable-v4-ko.json'
OUT = ROOT / 'configs/food-executable-v6-ko.json'
NEW = {
 'Wii本体に自宅住所情報が\n登録されていません。\n住所情報の設定へ移動して\n「自宅住所」を登録してください。\n\n※出前チャンネルでは\n「その他の住所」はご利用になれません。':
   'Wii 본체에 자택 주소가\n등록돼 있지 않습니다.\n주소 설정에서\n「자택 주소」를 등록해 주세요.\n\n※이 채널에서는 「그 밖의 주소」를\n쓸 수 없습니다.',
 'Wii本体に自宅住所情報が\n登録されていません。\n住所情報の設定へ移動して\n「自宅住所」を登録してください。':
   'Wii 본체에 자택 주소가\n등록돼 있지 않습니다.\n주소 설정에서\n「자택 주소」를 등록해 주세요.',
 '電話番号が正確でない可能性があり\nこのままではご利用いただけません。\n住所情報の設定へ移動して\n電話番号を確認してください。':
   '전화번호가 정확하지 않을 수 있어\n이대로는 이용할 수 없습니다.\n주소 설정에서\n전화번호를 확인해 주세요.',
 '入力された電話番号が\n正確でない可能性があります。\n(市外局番から入力してください)':
   '입력한 전화번호가\n정확하지 않을 수 있습니다.\n(지역 번호부터 입력해 주세요)',
 'WiiConnect24の機能を使用するためには、\n本体の更新が必要です。くわしくは、\n本体の取扱説明書をお読みください。\nエラーコード:':
   'WiiConnect24 기능을 사용하려면\n본체 업데이트가 필요합니다.\n본체 설명서를 읽어 주세요.\n오류 코드:',
 '当日配達できるお店がみつかりませんでした。\n「明日以降の予約」にてお店がある場合が\nございますので、ご確認ください。\nまた「お店のリクエスト」にて\nお近くで出前していただけるお店を\nご紹介いただくことが可能です。\nよろしければご利用ください。':
   '오늘 배달 가능한 가게가 없습니다.\n「내일 이후 예약」에는 가게가 있을 수\n있으니 확인해 주세요.\n또 「가게 요청」으로\n근처에서 배달해 주는 가게를\n소개받을 수 있습니다.\n괜찮으시면 이용해 주세요.',
 '２時間以上操作されなかった可能性が\nございます。\nもう一度お試しください。\nエラーコード:':
   '2시간 이상 조작하지 않았을 수\n있습니다.\n다시 시도해 주세요.\n오류 코드:',
 'お店の名前を入力してください。': '가게 이름을 입력해 주세요.',
 'お店の電話番号を入力してください。': '가게 전화번호를 입력해 주세요.',
}
TOKEN = re.compile(r'%[-+0-9.*]*[a-zA-Z]')


def build():
    v4 = json.loads(V4.read_text(encoding='utf-8'))
    lib = load_library(); title = lib.title.Title()
    title.load_wad((ROOT / 'workspace/channels/food/originals/food-japan-v512.wad').read_bytes())
    wl = bspatch.apply(title.get_content_by_index(1), gen.PATCH.read_bytes())
    if sha256(wl) != v4['source_sha256']:
        raise SystemExit('WiiLink executable differs from the v4 table source')
    glyphs = gen.korean_font_map(); m = tf.korean_metrics(); mj = tf.stock_metrics(title.get_content_by_index(3))
    panes = tf.dialog_boxes(title.get_content_by_index(2))
    overlap = set(NEW) & set(v4['utf16'])
    if overlap:
        raise SystemExit('v6 additions already in the v4 table')
    for src, tgt in NEW.items():
        slots = gen.literal_slots(wl, src)
        if not slots:
            raise SystemExit('Not a whole literal: ' + repr(src[:16]))
        if any(len(tgt.encode('utf-16-be')) + 2 > e - s for s, e in slots):
            raise SystemExit('Korean exceeds its slot: ' + repr(tgt[:16]))
        if TOKEN.findall(src) != TOKEN.findall(tgt):
            raise SystemExit('Format tokens differ: ' + repr(src[:16]))
        missing = [c for c in tgt if c != '\n' and ord(c) not in glyphs]
        if missing:
            raise SystemExit('Glyphs missing from Korean wbf1: ' + ''.join(missing))
        bad = tf.dialog_fit(m, mj, panes, src, tgt)
        if bad:
            raise SystemExit('Korean dialog line does not fit %r: %r' % (tgt[:16], bad))
    table = dict(v4['utf16']); table.update(NEW)
    return dict(source=v4['source'], source_sha256=v4['source_sha256'],
                note=v4['note'] + ' v6 adds the no-home-address guide (real-Wii video), phone checks, WC24 update, '
                     'no-shop-today, two-hour timeout and shop-request prompts (scripts/make_food_translations_v6.py).',
                utf16=table)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    text = json.dumps(build(), ensure_ascii=False, indent=1) + '\n'
    if args.check:
        if OUT.read_text(encoding='utf-8') != text:
            raise SystemExit('configs/food-executable-v6-ko.json differs from the generator')
        print('PASS: v6 executable table matches its generator'); return
    if OUT.exists():
        raise SystemExit('Existing v6 table preserved; use --check')
    OUT.write_text(text, encoding='utf-8')
    print('Wrote', OUT.name, 'with', len(json.loads(text)['utf16']), 'strings (+%d)' % len(NEW))


if __name__ == '__main__':
    main()
