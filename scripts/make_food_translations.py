"""Generate + validate configs/food-executable-v1-ko.json.

Each Japanese source must exist as a zero-terminated UTF-16BE (or Shift-JIS)
literal in the decompressed stock Food DOL and the Korean replacement must fit
the original zero-padded slot. Format tokens (%s %d %02d ...) and trailing
error-code digits are preserved. Protocol category tokens that WiiLink matches
against server XML (Meal/Pizza/Sushi/...) are deliberately NOT touched.
"""
import sys, re, json, hashlib, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce.wiiroom_formats import decompress_lz11

# Korean UI follows the project glossary: 확인/취소/예/아니요, Wii 메뉴,
# Wii 본체 저장 메모리, 오류 코드, WiiConnect24, "~해 주세요" polite style.
U16 = {
 # --- save data / NAND ---
 '出前チャンネルのシステムファイルが\n壊れています。チャンネル管理画面で\n出前チャンネルを消去した後、\nもう一度Wiiショッピングチャンネルから\n出前チャンネルをダウンロードしてください。\nそれでも同じメッセージが出るようであれば、\n任天堂サービスセンターに\nお問い合わせください。':
   '음식 배달 채널의 시스템 파일이\n손상됐습니다. 채널 관리 화면에서\n음식 배달 채널을 삭제한 뒤\n다시 Wii 쇼핑 채널에서\n음식 배달 채널을 받아 주세요.\n그래도 같은 메시지가 나오면\n닌텐도 서비스 센터로\n문의해 주세요.',
 'Wii本体保存メモリが壊れました。\nくわしくはWii本体の\n取扱説明書をお読みください。':
   'Wii 본체 저장 메모리가 손상됐습니다.\n자세한 내용은 Wii 본체\n설명서를 읽어 주세요.',
 'Wii本体保存メモリの\n書き込み/読み出しができませんでした。\nくわしくはWii本体の取扱説明書を\nお読みください。':
   'Wii 본체 저장 메모리에\n쓰기/읽기를 할 수 없습니다.\n자세한 내용은 Wii 본체 설명서를\n읽어 주세요.',
 'Wii本体保存メモリの\n書き込み/読み出し中にエラーが発生しました。\nくわしくはWii本体の取扱説明書を\nお読みください。':
   'Wii 본체 저장 메모리에\n쓰기/읽기 중 오류가 발생했습니다.\n자세한 내용은 Wii 본체 설명서를\n읽어 주세요.',
 '原因不明のエラーが発生しました。\n電源を切って\nもう一度お試しください。\nエラーコード:':
   '알 수 없는 오류가 발생했습니다.\n전원을 끄고\n다시 시도해 주세요.\n오류 코드:',
 '出前チャンネルの\nサービスは終了いたしました。\n今までご利用いただき\nありがとうございました。\nエラーコード:332197':
   '음식 배달 채널의\n서비스가 종료되었습니다.\n그동안 이용해 주셔서\n감사합니다.\n오류 코드:332197',
 '出前チャンネルに\n更新があります！\nWiiショッピングチャンネルで\n受信をやり直してください。\nエラーコード:332196':
   '음식 배달 채널에\n업데이트가 있습니다!\nWii 쇼핑 채널에서\n다시 받아 주세요.\n오류 코드:332196',
 'インターネットに接続できません。\nWii本体設定のインターネット設定を\nご確認ください。\nエラーコード:':
   '인터넷에 연결할 수 없습니다.\nWii 본체 설정의 인터넷 설정을\n확인해 주세요.\n오류 코드:',
 'インターネットの設定を確認するか\nしばらく待ってから\nもう一度お試しください。\nエラーコード:':
   '인터넷 설정을 확인하거나\n잠시 기다린 뒤\n다시 시도해 주세요.\n오류 코드:',
 # --- WiiConnect24 ---
 'Wii本体保存メモリに問題があるため、\nWiiConnect24を使用できません。\nエラーコード:':
   'Wii 본체 저장 메모리 문제로\nWiiConnect24를 사용할 수 없습니다.\n오류 코드:',
 'エラーが発生したため、\nWiiConnect24の機能を使用できません。\nリセットしてやり直してください。\nエラーコード:':
   '오류가 발생하여\nWiiConnect24 기능을 쓸 수 없습니다.\n리셋하고 다시 시도해 주세요.\n오류 코드:',
 'WiiConnect24のサービスが\n一時的にご利用できません。\nしばらく経ってからもう一度お試しください。\nエラーコード:':
   'WiiConnect24 서비스를\n잠시 이용할 수 없습니다.\n잠시 후 다시 시도해 주세요.\n오류 코드:',
 'ネットワーク機能の利用が制限されています。\nWiiオプションのペアレンタルコントロールの\n設定を確認してください。\nエラーコード:':
   '네트워크 기능 이용이 제한되어 있습니다.\nWii 옵션의 이용 제한 설정을\n확인해 주세요.\n오류 코드:',
 # --- address / personal data (from Set Personal Data) ---
 'Wii本体に住所情報の設定ができません。\nWii本体の更新を行ってください。':
   'Wii 본체에 주소 정보를 설정할 수 없습니다.\nWii 본체를 업데이트해 주세요.',
 'Wii本体の住所情報設定に更新があります。\n「出前チャンネル」を利用する為には\nWii本体の更新を行ってください。':
   'Wii 본체 주소 정보 설정에 업데이트가 있습니다.\n음식 배달 채널을 이용하려면\nWii 본체를 업데이트해 주세요.',
 'Wii本体の住所情報は\n暗証番号保護されています。\n\n4桁の暗証番号を入力してください。':
   'Wii 본체 주소 정보는\n비밀번호로 보호돼 있습니다.\n\n4자리 비밀번호를 입력해 주세요.',
 '暗証番号が違います。\n住所情報を表示することができません。':
   '비밀번호가 다릅니다.\n주소 정보를 표시할 수 없습니다.',
 'Wii本体の住所情報を登録･編集します。\nよろしいですか？':
   'Wii 본체 주소 정보를 등록·편집합니다.\n계속할까요?',
 '住所情報の設定へ移動して\n「自宅住所」を変更してください。':
   '주소 정보 설정으로 이동해\n자택 주소를 변경해 주세요.',
 '住所情報に変更があった\n可能性があります。':
   '주소 정보가 변경됐을\n수 있습니다.',
 # --- search / region ---
 '今から\n注文ができるお店をさがします。\nあてはまるお住まいの地域を選んでください。':
   '지금부터\n주문 가능한 가게를 찾습니다.\n해당하는 거주 지역을 선택해 주세요.',
 ' しばらくお待ちください。\n(時間がかかる場合があります)':
   ' 잠시 기다려 주세요.\n(시간이 걸릴 수 있습니다)',
 'お客様のご住所へ出前配達ができる\nお店の検索が終了しました。':
   '고객님 주소로 배달 가능한\n가게 검색이 끝났습니다.',
 # --- save / load ---
 '出前チャンネルの\nセーブデータを作成します。\n2ブロックの空き容量が\n必要になります。':
   '음식 배달 채널의\n저장 데이터를 만듭니다.\n2블록의 빈 용량이\n필요합니다.',
 'セーブデータが壊れているため\n修復します。':
   '저장 데이터가 손상되어\n복구합니다.',
 'ロード中です。\n電源ボタンやリセットボタンに\nさわらないでください。':
   '불러오는 중입니다.\n전원·리셋 버튼을\n누르지 말아 주세요.',
 'セーブ中です。\n電源ボタンやリセットボタンに\nさわらないでください。':
   '저장하는 중입니다.\n전원·리셋 버튼을\n누르지 말아 주세요.',
 'セーブデータが壊れています。\nセーブデータを作り直します。':
   '저장 데이터가 손상됐습니다.\n다시 만듭니다.',
 # --- navigation / confirmations ---
 'Wiiメニューへ戻りますか？': 'Wii 메뉴로 돌아갈까요?',
 '出前チャンネルを\nご利用いただくにあたり\n利用規約･プライバシーポリシーに\n同意していただく必要があります。':
   '음식 배달 채널을\n이용하시려면\n이용약관·개인정보 방침에\n동의하셔야 합니다.',
 '出前チャンネルをご利用いただけません。\nWiiメニューへ戻りますか？':
   '음식 배달 채널을 이용할 수 없습니다.\nWii 메뉴로 돌아갈까요?',
 '注文きろくがありません。\nトップ画面に戻ります。':
   '주문 기록이 없습니다.\n첫 화면으로 돌아갑니다.',
 'ペアレンタルコントロールにより\n制限されています。':
   '이용 제한 설정으로\n제한되어 있습니다.',
 '暗証番号が違います。': '비밀번호가 다릅니다.',
 '暗証番号が違います。\nWiiメニューへ戻ります。':
   '비밀번호가 다릅니다.\nWii 메뉴로 돌아갑니다.',
 '準備をしています。\nしばらくお待ちください。':
   '준비 중입니다.\n잠시 기다려 주세요.',
 'このページを表示することが\nできませんでした。\nエラーコード:':
   '이 페이지를 표시할 수\n없습니다.\n오류 코드:',
 # --- cart / order list (browse side; NOT order submission) ---
 '注文リストの内容は消えます。\nよろしいですか？':
   '주문 목록 내용이 삭제됩니다.\n계속할까요?',
 '注文リストより\nこの商品を取り消します。\nよろしいですか？':
   '주문 목록에서\n이 상품을 취소합니다.\n계속할까요?',
 'メニュー画面へ戻ります。\n注文リストの内容は消えます。\nよろしいですか？':
   '메뉴 화면으로 돌아갑니다.\n주문 목록 내용이 삭제됩니다.\n계속할까요?',
 'これ以上注文を追加することが\nできません。\n一度注文を完了してください。':
   '더 이상 주문을 추가할 수\n없습니다.\n먼저 주문을 완료해 주세요.',
 # --- generic server/network errors ---
 '通信エラーが発生しました。\n注文は完了していない場合がございます。\nエラーコード:':
   '통신 오류가 발생했습니다.\n주문이 완료되지 않았을 수 있습니다.\n오류 코드:',
 'サーバーでエラーが発生しました。\nしばらく待ってから\nもう一度お試しください。\nエラーコード:':
   '서버에서 오류가 발생했습니다.\n잠시 기다린 뒤\n다시 시도해 주세요.\n오류 코드:',
 '受信に失敗しました。\nエラーコード:':
   '받기에 실패했습니다.\n오류 코드:',
 '現在メンテナンス中です。\n大変申し訳ありませんが\nしばらくお待ちください。\nエラーコード:':
   '현재 점검 중입니다.\n대단히 죄송하지만\n잠시 기다려 주세요.\n오류 코드:',
}
# Shift-JIS path strings CANNOT carry Hangul (Shift-JIS has no Korean code
# points and the channel's JIS->Unicode tables contain no Hangul), so these
# stay Japanese. Localizing them would require replacing the SJIS decoder +
# tables, which is out of scope. Left empty deliberately; see docs.
SJIS = {}

# Tighter forms for strings whose first-pass Korean overran the fixed slot.
OVERRIDE = {
 'Wii本体保存メモリが壊れました。\nくわしくはWii本体の\n取扱説明書をお読みください。':
   'Wii 본체 저장 메모리가 손상됐습니다.\nWii 본체 설명서를\n읽어 주세요.',
 'Wii本体保存メモリの\n書き込み/読み出し中にエラーが発生しました。\nくわしくはWii本体の取扱説明書を\nお読みください。':
   'Wii 본체 저장 메모리에\n쓰기/읽기 중 오류가 발생했습니다.\n내용은 Wii 본체 설명서를\n읽어 주세요.',
 'Wii本体保存メモリに問題があるため、\nWiiConnect24を使用できません。\nエラーコード:':
   'Wii 본체 저장 메모리 문제로\nWiiConnect24를 쓸 수 없습니다.\n오류 코드:',
 'Wii本体に住所情報の設定ができません。\nWii本体の更新を行ってください。':
   'Wii 본체에 주소를 설정할 수 없어\nWii 본체를 업데이트하세요.',
 'Wii本体の住所情報設定に更新があります。\n「出前チャンネル」を利用する為には\nWii本体の更新を行ってください。':
   'Wii 본체 주소 설정에 업데이트가 있습니다.\n음식 배달 채널 이용에는\nWii 본체를 업데이트하세요.',
 'Wii本体の住所情報は\n暗証番号保護されています。\n\n4桁の暗証番号を入力してください。':
   'Wii 본체 주소 정보는\n비밀번호로 보호됩니다.\n\n4자리 비밀번호를 입력하세요.',
 '暗証番号が違います。\n住所情報を表示することができません。':
   '비밀번호가 다릅니다.\n주소를 표시할 수 없습니다.',
 'Wii本体の住所情報を登録･編集します。\nよろしいですか？':
   'Wii 본체 주소를 등록·편집합니다.\n계속할까요?',
 '住所情報の設定へ移動して\n「自宅住所」を変更してください。':
   '주소 정보 설정으로 이동해\n자택 주소를 변경하세요.',
 '今から\n注文ができるお店をさがします。\nあてはまるお住まいの地域を選んでください。':
   '지금부터\n주문 가능한 가게를 찾습니다.\n해당하는 거주 지역을 선택하세요.',
 '出前チャンネルをご利用いただけません。\nWiiメニューへ戻りますか？':
   '음식 배달 채널을 쓸 수 없습니다.\nWii 메뉴로 돌아갈까요?',
 '注文きろくがありません。\nトップ画面に戻ります。':
   '주문 기록이 없습니다.\n첫 화면으로 갑니다.',
 '暗証番号が違います。\nWiiメニューへ戻ります。':
   '비밀번호가 다릅니다.\nWii 메뉴로 갑니다.',
 'メニュー画面へ戻ります。\n注文リストの内容は消えます。\nよろしいですか？':
   '메뉴 화면으로 갑니다.\n주문 목록 내용이 삭제됩니다.\n계속할까요?',
 '通信エラーが発生しました。\n注文は完了していない場合がございます。\nエラーコード:':
   '통신 오류가 발생했습니다.\n주문이 완료 안 됐을 수 있습니다.\n오류 코드:',
}
U16 = {**U16, **OVERRIDE}


def utf16_slots(dol):
    import collections
    out = {}
    for src, tgt in U16.items():
        needle = src.encode('utf-16-be') + b'\0\0'
        at = dol.find(needle)
        if at < 0 or at % 2:
            out[src] = ('missing', None); continue
        # slot = terminator + following zero padding
        end = at + len(src.encode('utf-16-be'))
        slot = end + 2
        while slot + 2 <= len(dol) and dol[slot:slot+2] == b'\0\0': slot += 2
        cap = slot - at
        if re.findall(r'%[-+0-9.*]*[a-zA-Z]', src) != re.findall(r'%[-+0-9.*]*[a-zA-Z]', tgt):
            out[src] = ('fmt-mismatch', None); continue
        need = len(tgt.encode('utf-16-be')) + 2
        out[src] = ('ok' if need <= cap else 'too-long', (need, cap))
    return out

def sjis_slots(dol):
    out = {}
    for src, tgt in SJIS.items():
        needle = src.encode('shift-jis') + b'\0'
        at = dol.find(needle)
        if at < 0: out[src] = ('missing', None); continue
        slot = at + len(src.encode('shift-jis')) + 1
        while slot < len(dol) and dol[slot] == 0: slot += 1
        cap = slot - at
        need = len(tgt.encode('shift-jis')) + 1
        out[src] = ('ok' if need <= cap else 'too-long', (need, cap))
    return out

def main():
    lib = load_library(); t = lib.title.Title()
    t.load_wad((ROOT / 'workspace/channels/food/originals/food-japan-v512.wad').read_bytes())
    dol = decompress_lz11(t.get_content_by_index(1))
    sha = hashlib.sha256(dol).hexdigest()
    u = utf16_slots(dol); s = sjis_slots(dol)
    bad = {k: v for k, v in {**u, **s}.items() if v[0] != 'ok'}
    for k, v in bad.items():
        print('DROP', v[0], v[1], repr(k[:30]))
    cfg = dict(
        source='decompressed Food content 1 (LZ11)', source_sha256=sha,
        note='In-slot UTF-16BE/Shift-JIS replacement; protocol category tokens left intact; order-submission flow not localized here.',
        utf16={k: U16[k] for k in U16 if u[k][0] == 'ok'},
        sjis={k: SJIS[k] for k in SJIS if s[k][0] == 'ok'})
    out = ROOT / 'configs/food-executable-v1-ko.json'
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    report = dict(utf16_ok=len(cfg['utf16']), utf16_total=len(U16),
                  dropped={k: dict(reason=v[0], need_cap=v[1]) for k, v in {**u, **s}.items() if v[0] != 'ok'})
    (ROOT / 'workspace/private/food-exec-coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('wrote', out.name, 'utf16', len(cfg['utf16']), 'of', len(U16), 'sjis', len(cfg['sjis']), 'of', len(SJIS), 'sha', sha[:12])

if __name__ == '__main__':
    main()
