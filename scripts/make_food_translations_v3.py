"""Generate + validate configs/food-executable-v3-ko.json (WiiLink-DOL based).

Revision 3 builds start from WiiLink's Demae_1_Japan executable for BOTH the
local and the hardware WAD (the local one only redirects food.wiilink24.com to
127.0.0.2). The table is v1's 45 strings plus the remaining visible dialog
strings and WiiLink's 16 replacement messages (DOL section 15, which WiiLink
points 16 dialogs at). Every source must be a whole zero-terminated UTF-16BE
literal (previous halfword 0) in the WiiLink DOL, every Korean target must fit
its zero-padded slot, keep format tokens, and use only glyphs present in the
Korean 43K wbf1 font (blank-text guard). Protocol category tokens (Meal, Pizza,
...) are not touched.
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive, sha256
from kwce import bspatch

PATCH = ROOT / 'workspace/channels/food/references/wiilink-patcher/bsdiff__demae__Demae_1_Japan.bsdiff'
V1 = ROOT / 'configs/food-executable-v1-ko.json'
OUT = ROOT / 'configs/food-executable-v3-ko.json'

GENERIC = '알 수 없는 오류가 발생했습니다.\n전원을 끄고\n다시 시도해 주세요.\n오류 코드:'
NEW = {
 # save banner title (WiiLink changed the stock '出前チャンネル' to this)
 '出前Food Channel': '음식 배달 채널',
 '注文できる時間がきめられています。': '주문 시간이 정해져 있습니다.',
 # save memory
 'Wii本体保存メモリの\n空き容量が異常です。\nくわしくはWii本体の\n取扱説明書をお読みください。':
   'Wii 본체 저장 메모리의\n빈 용량이 이상합니다.\nWii 본체 설명서를 읽어 주세요.',
 'Wii本体保存メモリの\n空きファイル数が異常です。\nくわしくはWii本体の\n取扱説明書をお読みください。':
   'Wii 본체 저장 메모리의\n빈 파일 수가 이상합니다.\nWii 본체 설명서를 읽어 주세요.',
 'Wii本体保存メモリの\n書き込み/読み出し中に\nエラーが発生しました。\nくわしくはWii本体の\n取扱説明書をお読みください。':
   'Wii 본체 저장 메모리에\n쓰기/읽기 중\n오류가 발생했습니다.\nWii 본체 설명서를 읽어 주세요.',
 'Wii本体保存メモリの空き容量が\n不足しています。\nWiiメニューのデータ管理画面で\nデータをSDカードに移動するか、\nデータを消去して2ブロックの\n空きブロックを用意してください。':
   'Wii 본체 저장 메모리의 빈 용량이\n부족합니다.\nWii 메뉴의 데이터 관리 화면에서\n데이터를 SD카드로 옮기거나\n데이터를 지워 2블록의\n빈 블록을 확보해 주세요.',
 'Wii本体保存メモリの空きファイル数が\n不足しています。\nWiiメニューのデータ管理画面で\nデータをSDカードに移動するか、\nデータを消去してください。':
   'Wii 본체 저장 메모리 빈 파일 수가\n부족합니다.\nWii 메뉴의 데이터 관리 화면에서\n데이터를 SD카드로 옮기거나\n데이터를 지워 주세요.',
 # WiiConnect24
 'WiiConnect24の設定がONになっていません。\nWiiオプションで設定を確認してください。\nくわしくは、\n本体の取扱説明書をお読みください。\nエラーコード:':
   'WiiConnect24 설정이 켜져 있지 않습니다.\nWii 옵션에서 설정을 확인해 주세요.\n자세한 내용은\n본체 설명서를 읽어 주세요.\n오류 코드:',
 'インターネットに接続できないため、\nWiiConnect24が使用できません。\nインターネットの設定から接続先を\nご確認ください。くわしくは、\n本体の取扱説明書をお読みください。\nエラーコード:':
   '인터넷에 연결할 수 없어\nWiiConnect24를 사용할 수 없습니다.\n인터넷 설정에서 연결 대상을\n확인해 주세요. 자세한 내용은\n본체 설명서를 읽어 주세요.\n오류 코드:',
 'WiiConnect24のサービスが一時的にご利用できません。\nしばらく経ってからもう一度お試しください。\nエラーコード:':
   'WiiConnect24 서비스를 잠시 이용할 수 없습니다.\n잠시 후 다시 시도해 주세요.\n오류 코드:',
 # coded errors
 **{f'原因不明のエラーが発生しました。\n電源を切って\nもう一度お試しください。\nエラーコード:{c}': GENERIC + c
    for c in ['339198', '334010', '334011', '334012', '334013', '334014', '334015', '334016']},
 'インターネットの設定を確認するか\nしばらく待ってから\nもう一度お試しください。\nエラーコード:339900':
   '인터넷 설정을 확인하거나\n잠시 기다린 뒤\n다시 시도해 주세요.\n오류 코드:339900',
 'このページを表示することが\nできませんでした。\nエラーコード:339194': '이 페이지를 표시할 수\n없습니다.\n오류 코드:339194',
 # PIN / address
 '暗証番号が違います。\n暗証番号を忘れた場合は\nWii本体の住所情報を\n消去する必要があります。':
   '비밀번호가 다릅니다.\n비밀번호를 잊었다면\nWii 본체 주소 정보를\n지워야 합니다.',
 '暗証番号を忘れた場合は\nWii本体の住所情報を\n消去する必要があります。\n\nWii本体の住所情報設定へ移動しますか？':
   '비밀번호를 잊었다면\nWii 본체 주소 정보를\n지워야 합니다.\n\nWii 본체 주소 설정으로 갈까요?',
 'Wii本体に登録されている\n住所情報が壊れています。\n住所情報の設定へ移動して\n住所情報を全消去してください。':
   'Wii 본체에 등록된\n주소 정보가 손상됐습니다.\n주소 설정으로 이동해\n주소 정보를 모두 지우세요.',
 '「氏名」に\n「ふりがな」が設定されていません。\n\n「出前チャンネル」を利用するためには\n「ふりがな」情報が必要となります。\n住所情報の設定へ移動して\n「ふりがな」を設定してください。':
   '「이름」의\n「읽는 법」이 없습니다.\n\n음식 배달 채널을 이용하려면\n「읽는 법」 정보가 필요합니다.\n주소 설정으로 이동해\n「읽는 법」을 설정해 주세요.',
 '申し訳ございません。\nお客様のご住所がサービス外のため、\n出前チャンネルをご利用いただけません。\n\nWiiメニューへ戻ります。':
   '죄송합니다.\n고객님 주소가 서비스 지역 밖이라\n음식 배달 채널을 이용할 수 없습니다.\n\nWii 메뉴로 갑니다.',
 'これより出前チャンネルにて\nお客様のご住所へ出前配達ができる\nお店を検索します。\n場合によりお住まいの地域を選択していただく\n必要があります。ご了承ください。':
   '지금부터 음식 배달 채널에서\n고객님 주소로 배달 가능한\n가게를 검색합니다.\n경우에 따라 거주 지역을\n선택해야 할 수 있습니다.',
 '前回ご利用時より。住所の設定が\n変更されています。\n\nお住まいの地域を再び選択して\nいただく必要がございます。':
   '지난번 이용 후 주소 설정이\n변경되었습니다.\n\n거주 지역을 다시\n선택해 주세요.',
 '暗証番号を入力してください': '비밀번호를 입력하세요',
 '地区名無し': '지역명 없음', '都道府県名無し': '시도명 없음', '市区町村郡名無し': '시군구명 없음',
 '町名・大字無し': '동명 없음', '丁目・小字無し': '번지 없음',
 # order list / request (UI text only; no ordering is implemented or served)
 '「商品内容」や「出前のとくてん」が　\n 変更されている場合がございます。\n\n注文リストの内容をよくご確認のうえ\nご利用ください。':
   '「상품 내용」이나 「배달 혜택」이\n변경되었을 수 있습니다.\n\n주문 목록 내용을 잘 확인한 뒤\n이용해 주세요.',
 '注文きろくのお店が見つからないため、\n注文リストをつくれませんでした。':
   '주문 기록의 가게가 없어\n주문 목록을 만들 수 없습니다.',
 'ペアレンタルコントロールの制限を\n一時的に解除しました。': '이용 제한 설정을\n일시적으로 해제했습니다.',
 'これよりお店のリクエストを\n“夢の街創造委員会(株)”へ送信します。\nよろしいですか？':
   '지금부터 가게 요청을\n“유메노마치소조위원회(주)”에\n보냅니다. 계속할까요?',
 'リクエストの内容は消えます。\nよろしいですか？': '요청 내용이 삭제됩니다.\n계속할까요?',
 'お店のリクエストを送信しました。\nトップ画面に戻ります。': '가게 요청을 보냈습니다.\n첫 화면으로 갑니다.',
 '出前チャンネルでは同じ商品を\n数量100以上注文できません。\n申し訳ございません。\n数量99以下でお願いします。':
   '같은 상품은\n100개 이상 주문할 수 없습니다.\n죄송합니다.\n99개 이하로 주문해 주세요.',
 '注文を送信します。\n料金は出前を届けに来た方に\n現金でお支払いください。':
   '주문을 보냅니다.\n요금은 배달 온 분께\n현금으로 내 주세요.',
 'トップ画面へ戻ります。\n注文リストの内容は消えます。\nよろしいですか？':
   '첫 화면으로 갑니다.\n주문 목록 내용이 삭제됩니다.\n계속할까요?',
 '注文数が多いため\n「注文きろく」をつくることが\nできませんでした。': '주문 수가 많아\n「주문 기록」을 만들 수\n없었습니다.',
 '本体メモリのエラーが発生したため\n「注文きろく」を\nつくることができませんでした。':
   '본체 메모리 오류로\n「주문 기록」을\n만들 수 없었습니다.',
 'エラーが発生したため\nWii伝言板へメッセージを\nはりつけられませんでした。':
   '오류가 발생해\nWii 게시판에 메시지를\n붙이지 못했습니다.',
 ' 注文中です。\n電源ボタンやリセットボタンに\nさわらないでください。':
   ' 주문하는 중입니다.\n전원·리셋 버튼을\n누르지 말아 주세요.',
 'サーバーでエラーが発生しました。\n注文は完了していない場合がございます。\nお手数ですが、下記の電話番号に\nお電話の上注文番号を伝えて、ご確認ください。\nエラーコード:':
   '서버에서 오류가 발생했습니다.\n주문이 완료되지 않았을 수 있습니다.\n번거로우시겠지만 아래 전화번호로\n주문 번호를 알려 확인해 주세요.\n오류 코드:',
 'エラーが発生しました。\n注文は完了していない場合がございます。\nお手数ですが、下記の電話番号に\nお電話の上注文番号を伝えて、ご確認ください。\nエラーコード:':
   '오류가 발생했습니다.\n주문이 완료되지 않았을 수 있습니다.\n번거로우시겠지만 아래 전화번호로\n주문 번호를 알려 확인해 주세요.\n오류 코드:',
 '申し訳ございません。\nご注文いただいている間に\n受付時間が終了いたしました。': '죄송합니다.\n주문하시는 동안\n접수 시간이 끝났습니다.',
 '申し訳ございません。\nご注文いただいている間に\nお店にトラブルが発生しました。': '죄송합니다.\n주문하시는 동안\n가게에 문제가 생겼습니다.',
 'ご注文のお店は、現在受付時間外です。\nお時間を改めてご注文をお願いします。':
   '주문하신 가게는 지금 접수 시간 외입니다.\n나중에 다시 주문해 주세요.',
 'ご注文のお店は、現在閉店中です。\nお時間を改めてご注文をお願いします。':
   '가게가 지금 영업 중이 아닙니다.\n나중에 다시 주문해 주세요.',
 '申し訳ございません。\nご注文いただいている間に\nうりきれた商品があります。\n注文内容を確認してください。':
   '죄송합니다.\n주문하시는 동안\n품절된 상품이 있습니다.\n주문 내용을 확인해 주세요.',
 # WiiLink section-15 messages (English) that 16 dialogs point to in the WiiLink DOL
 'Preparing.\nPlease wait.': '준비 중입니다.\n잠시 기다려 주세요.',
 'Please wait': '잠시 기다려 주세요',
 'Please agree to the Terms of Use.': '이용약관에 동의해 주세요.',
 '2 blocks of free space is required.': '2블록의 빈 용량이 필요합니다.',
 'Please select the area you reside in.': '거주 지역을 선택해 주세요.',
 'Region setup complete. Enjoy!': '지역 설정이 끝났습니다. 즐겨 주세요!',
 'Are you sure you want\nto send your request?': '가게 요청을\n보내시겠습니까?',
 'Your request has been submitted.': '요청을 보냈습니다.',
 'Go to Set Personal Data?': '주소 설정으로 이동할까요?',
 'There are no order records.': '주문 기록이 없습니다.',
 'Food Channel is unavailable.\nTo Wii Menu?': '음식 배달 채널을 이용할 수 없습니다.\nWii 메뉴로 갈까요?',
 'These are times you can place an order.': '주문 가능한 시간입니다.',
 'Submit your order. Please pay in cash.': '주문을 보냅니다. 현금으로 결제해 주세요.',
 'Ordering.\nDo not touch the power button.': '주문하는 중입니다.\n전원 버튼을 누르지 마세요.',
 'Return to Wii Menu?': 'Wii 메뉴로 갈까요?',
 'Would you like to remove this item?': '이 상품을 삭제할까요?',
}
FMT = r'%[-+0-9.*]*[a-zA-Z]'


def literal_slots(dol, src):
    """Every whole-literal occurrence of src: (start, slot_end)."""
    needle = src.encode('utf-16-be') + b'\0\0'; out = []; at = dol.find(needle)
    while at >= 0:
        if at % 2 == 0 and (at < 2 or dol[at - 2:at] == b'\0\0'):
            end = at + len(needle) - 2; slot = end + 2
            while slot + 2 <= len(dol) and dol[slot:slot + 2] == b'\0\0':
                slot += 2
            out.append((at, slot))
        at = dol.find(needle, at + 1)
    return out


def korean_font_map():
    from kwce.channel_korean_font import korean_shared_fonts
    from kwce.channel_font import font_data
    rfna = ChannelArchive(korean_shared_fonts()[0]).get('wbf1.brfna')
    return set(font_data(b'RFNT' + rfna[4:])[1])


def main():
    lib = load_library(); t = lib.title.Title()
    t.load_wad((ROOT / 'workspace/channels/food/originals/food-japan-v512.wad').read_bytes())
    wl = bspatch.apply(t.get_content_by_index(1), PATCH.read_bytes())
    table = dict(json.loads(V1.read_text(encoding='utf-8'))['utf16']); table.update(NEW)
    glyphs = korean_font_map(); ok = {}; report = {}
    for src, tgt in table.items():
        slots = literal_slots(wl, src)
        missing = sorted({c for c in tgt if c not in '\n' and ord(c) not in glyphs})
        need = len(tgt.encode('utf-16-be')) + 2
        if not slots:
            report[src] = 'not a whole literal in the WiiLink DOL'
        elif re.findall(FMT, src) != re.findall(FMT, tgt):
            report[src] = 'format tokens differ'
        elif missing:
            report[src] = 'glyphs missing from Korean wbf1: ' + ''.join(missing)
        elif any(need > end - start for start, end in slots):
            report[src] = f'too long: need {need} > slot {min(end - start for start, end in slots)}'
        else:
            ok[src] = tgt
    cfg = dict(source='WiiLink Demae_1_Japan executable (bspatch of content 1)', source_sha256=sha256(wl),
               note='Whole-literal in-slot UTF-16BE replacement; all targets use glyphs of the Korean 43K wbf1; '
                    'protocol category tokens untouched; no ordering implemented.', utf16=ok)
    OUT.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (ROOT / 'workspace/private/food-exec-v3-coverage.json').write_text(json.dumps(dict(ok=len(ok), total=len(table), dropped=report), ensure_ascii=False, indent=1), encoding='utf-8')
    print('wrote', OUT.name, 'ok', len(ok), 'of', len(table), 'dropped', len(report))

    # v4 = v3 strings + the area-confirm line shown under the chosen area name
    # ("\n\nこれで正しいですか？", a DOL literal at 0x80470a3e, runtime-set).
    V4_EXTRA = {'\n\nこれで正しいですか？': '\n\n이대로 맞습니까?'}
    v4 = dict(ok); v4_report = {}
    for src, tgt in V4_EXTRA.items():
        slots = literal_slots(wl, src)
        missing = sorted({c for c in tgt if c != '\n' and ord(c) not in glyphs})
        need = len(tgt.encode('utf-16-be')) + 2
        if not slots:
            v4_report[src] = 'not a whole literal'
        elif missing:
            v4_report[src] = 'glyphs missing: ' + ''.join(missing)
        elif any(need > end - start for start, end in slots):
            v4_report[src] = 'too long'
        else:
            v4[src] = tgt
    OUT4 = ROOT / 'configs/food-executable-v4-ko.json'
    OUT4.write_text(json.dumps(dict(source=cfg['source'], source_sha256=cfg['source_sha256'],
        note=cfg['note'] + ' v4 adds the area-confirm line.', utf16=v4), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('wrote', OUT4.name, 'ok', len(v4), 'dropped', len(v4_report), v4_report)


if __name__ == '__main__':
    main()
