# -*- coding: utf-8 -*-
"""Generate configs/photoprints-messages-v8-ko.json: v1 Korean text re-broken so
each line fits its textbox (lead's v6 review: PD_Dialog_Update wrapped mid-word).

Rules (static, nw4r TextWriter metrics, Hangul advance from the built font):
  * a pane may use as many lines as the Japanese original occupied there
    (box height is NOT trusted: PD_Dialog_Update TextA is 3 lines tall but a
    second pane sits under its first line);
  * an overflowing line is first split at spaces; if that needs more lines than
    the budget, the paragraph is re-wrapped at spaces; if it still does not fit,
    the text is left for the build's horizontal fit (>= MIN_SCALE) or overridden.
Translator overrides are applied first. Debug-only layouts are reported only.
Writes the config (create-once) and a report under workspace/channels/photoprints.
"""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from kwce.channels import load_library,ChannelArchive
from kwce import photoprints_textfit as tf

SOURCE=ROOT/'configs/photoprints-messages-v1-ko.json'
TARGET=ROOT/'configs/photoprints-messages-v8-ko.json'
REPORT=ROOT/'workspace/channels/photoprints/textfit-v8-report.json'
DEBUG_LAYOUTS=tf.DEBUG_LAYOUTS               # developer front end, not shown to users
LAYOUT_ARCHIVES=['layout.arc.LZ','cursor.arc.LZ']
# Later table revisions = v8 rules + these decisions (each table is create-once).
REVISION_OVERRIDES={
    8:{},
    # Lead's v8/v9 review: '100엔$'. The 2nd %ls is the server's priceUnit, which the
    # pinned WiiLink cam-server (and our mirroring local feed) send as '$'. Korean
    # shows yen only; the trailing argument is ignored by the format call.
    10:{'%ls円%ls':'%ls엔'},
}
PLACEHOLDER=r'%[-+ #0-9.*]*(?:ls|l?[dsuxXf])'
REVISION=int(sys.argv[sys.argv.index('--revision')+1]) if '--revision' in sys.argv else 8
if REVISION not in REVISION_OVERRIDES:raise SystemExit('Unknown message table revision')
TARGET=ROOT/f'configs/photoprints-messages-v{REVISION}-ko.json'
REPORT=ROOT/f'workspace/channels/photoprints/textfit-v{REVISION}-report.json'

# Translator decisions where a shorter wording reads better than squeezing.
OVERRIDES={
    '上':'상','下':'하','左':'좌','右':'우',                       # one-kanji direction buttons
    'もどる':'뒤로','進む':'진행',                                  # two-cell buttons
    'Nicosは使用しない※表示ＯＦＦ':'Nicos 미사용\n※표시 OFF',        # hidden option label
    '確認へ':'확인','注文へ':'주문','同意しません':'동의 안 함','住所情報設定':'주소 설정',   # button labels
    'Wiiメニューへ':'Wii 메뉴로','Wii本体の更新へ':'본체 업데이트로',
    '○○○○を入力してください':'○○○○을(를)\n입력해 주세요',
    'セキュリティーコードとは、クレジットカードをインターネットで利用\nする際の不正対策のために用意された仕組みです。\nセキュリティーコードはカードのご利用明細などに表示されないため、\nインターネットでご利用される際の安全性が高まります。\nセキュリティーコードは、多くの場合、カード裏面の署名欄(表面の場合\nもあります。)に、カード番号の横に３桁の番号(ＡＭＥＸの場合、４桁\nの番号)で記載されています。\nなお、セキュリティーコードが記載されていないカードをご利用になる\n場合には、ご入力の必要はありません。\nまた、セキュリティーコードは、今回のご注文の安全性を確保するためだけに参照され、任天堂株式会社または、富士フイルム株式会社に保存されることは一切ありません。':
        '보안 코드는 신용카드를 인터넷에서 이용할 때\n부정 사용을 막기 위해 마련된 장치입니다.\n보안 코드는 카드 이용 명세 등에 표시되지 않으므로\n인터넷에서 이용하실 때 안전성이 높아집니다.\n보안 코드는 대부분 카드 뒷면 서명란(앞면인 경우도\n있습니다)의 카드 번호 옆에 3자리 번호(AMEX는 4자리)로\n적혀 있습니다.\n또한 보안 코드가 적혀 있지 않은 카드를 이용하시는\n경우에는 입력하실 필요가 없습니다.\n또한 보안 코드는 이번 주문의 안전성을 확보하기 위해서만\n참조되며, 닌텐도 주식회사 또는 후지필름 주식회사에\n저장되는 일은 일절 없습니다.',
    '前回の\n「%ls」\nのご注文内容をWii伝言板にお送りします。\nご確認ください。':
        '지난번\n「%ls」\n의 주문 내용을 Wii 알림판으로\n보냅니다. 확인해 주세요.',
}
# Single-line panes where squeezing would exceed MIN_SCALE or a rephrase is clearer.
SHORTER={
    'Wii本体に住所情報の設定ができません。':'Wii에 주소 정보를 설정할 수 없습니다.',          # lead's v6 capture
    'Wii本体に住所情報が登録されていません。':'Wii에 주소 정보가 등록되어 있지 않습니다.',
    '※配置されていない箇所があると注文に進めません！':'※배치되지 않은 부분이 있으면 주문할 수 없습니다!',
    '編集の途中でタイトル画面に戻りますか？':'편집 중 타이틀 화면으로 돌아가시겠습니까?',
    'フレームを変更をすると現在のページの\n写真配置情報が失われますが、続けますか？':'프레임을 바꾸면 현재 페이지의 사진 배치\n정보가 사라집니다. 계속하시겠습니까?',
    'Wii名刺引換番号入力画面':'Wii 명함 교환 번호 입력',
    'Wii本体の住所情報は、暗証番号で保護されています。\n４桁の番号を入力してください。':'Wii의 주소 정보는 비밀번호로 보호되어 있습니다.\n4자리 번호를 입력해 주세요.',
}


def font_metrics(messages,exec_rows):
    from kwce.photoprints_font import append_hangul_rfna
    from build_photoprints import hangul_used
    lib=load_library();t=lib.title.Title();t.load_wad((ROOT/'workspace/channels/photoprints/originals/digicam-japan-v1024.wad').read_bytes())
    c2=ChannelArchive(t.get_content_by_index(2));rodan=c2.get('font_rodan_28.brfna')
    font,_=append_hangul_rfna(rodan,''.join(sorted(hangul_used(messages,exec_rows))))
    return tf.Metrics(rodan),tf.Metrics(font),c2


def paragraphs(lines):
    groups=[]
    for line in lines:
        starts=not groups or not line or line.startswith(('※','・','(','（','「','【')) or not groups[-1][-1] or groups[-1][-1].endswith((')','）'))
        if line.startswith(tf.INDENT) and groups and groups[-1][0].startswith('※'):starts=False
        if starts:groups.append([line])
        else:groups[-1].append(line)
    return groups


def rewrap(m,box,text):
    out=[]
    for group in paragraphs(text.split('\n')):
        joined=group[0]
        for line in group[1:]:joined+=' '+line.lstrip(tf.INDENT)
        out.extend(tf._split(m,box,joined,box.w-tf.MARGIN) if joined else [''])
    return '\n'.join(out)


def budget(mj,box,jp):return tf.budget(mj,box,jp)


def fits(m,boxes,text):return all(not tf.overflow_lines(m,b,text) for b in boxes)


def main():
    src=json.loads(SOURCE.read_text(encoding='utf-8'));messages=dict(src['messages'])
    exec_rows=json.loads((ROOT/'configs/photoprints-executable-v1-ko.json').read_text(encoding='utf-8'))['rows']
    unknown=[k for k in list(OVERRIDES)+list(SHORTER)+list(REVISION_OVERRIDES[REVISION]) if k not in messages]
    if unknown:raise ValueError('Override keys not in the v1 table: '+repr([k[:20] for k in unknown]))
    messages.update(OVERRIDES);messages.update(REVISION_OVERRIDES[REVISION])
    mj,_,c2=font_metrics(messages,exec_rows)
    load_library();from libWiiPy.archive import decompress_lz77
    boxes={}
    for arc in LAYOUT_ARCHIVES:
        for k,v in tf.boxes_by_text(decompress_lz77(c2.get(arc)),set(messages)).items():boxes.setdefault(k,[]).extend(v)
    # Metrics for the Korean font built from the final strings (overrides may add syllables).
    final=dict(messages);final.update(SHORTER)
    _,m,_=font_metrics(final,exec_rows)
    report=[];changed={};violations=[]
    for jp,ko in sorted(messages.items()):
        live=[b for b in boxes.get(jp,[]) if b.file.split('/')[-1] not in DEBUG_LAYOUTS]
        if not live:continue
        if jp in SHORTER:ko=SHORTER[jp]
        jp_tail=len(jp)-len(jp.rstrip('\n'))
        if len(ko)-len(ko.rstrip('\n'))>jp_tail:ko=ko.rstrip('\n')+'\n'*jp_tail   # v1 added empty lines
        allowed=min(budget(mj,b,jp) for b in live)
        narrow=min(live,key=lambda b:b.w)
        action='fits';new=ko
        if not fits(m,live,ko):
            split=tf.reflow(m,live,ko)
            if fits(m,live,split) and len(split.split('\n'))<=allowed:new,action=split,'split'
            else:
                wrapped=rewrap(m,narrow,ko)
                if fits(m,live,wrapped) and len(wrapped.split('\n'))<=allowed:new,action=wrapped,'rewrap'
                else:action='compress'
        scale=min(tf.fit_scale(m,b,new) for b in live)
        if len(new.split('\n'))>allowed:violations.append(f'lines {len(new.splitlines())}>{allowed}: {live[0].file.split("/")[-1]}:{live[0].pane} {new!r}')
        if scale<tf.MIN_SCALE:violations.append(f'scale {scale:.3f}<{tf.MIN_SCALE}: {live[0].file.split("/")[-1]}:{live[0].pane} {new!r}')
        if new!=src['messages'].get(jp):changed[jp]=new
        if action!='fits' or jp in OVERRIDES or jp in SHORTER:
            report.append(dict(jp=jp,v1=src['messages'].get(jp),v8=new,action=action,allowed_lines=allowed,
                lines=len(new.split('\n')),min_scale=round(scale,3),panes=[f"{b.file.split('/')[-1]}:{b.pane}" for b in live]))
        messages[jp]=new
    for jp,ko in messages.items():
        if m.unmapped(ko):raise ValueError('Unmapped glyphs in '+repr(ko))
        # printf safety: Korean may drop trailing arguments but never add/reorder any.
        a,b=re.findall(PLACEHOLDER,jp),re.findall(PLACEHOLDER,ko)
        if b!=a[:len(b)]:violations.append(f'format arguments {b} are not a prefix of {a}: {ko!r}')
    if violations:
        for v in violations:print('VIOLATION',v)
        raise SystemExit(f'{len(violations)} text-fit violations; fix overrides first')
    notes={8:'v1 text re-broken/shortened to fit each textbox (static nw4r metrics); remaining overflow is fitted horizontally by the build.',
           10:'v8 rules plus: price label drops the server priceUnit suffix (WiiLink sends "$").'}
    out=dict(channel='photoprints',source_content2_sha256=src['source_content2_sha256'],derived_from='photoprints-messages-v1-ko.json',
        revision=REVISION,note=notes[REVISION],count=len(messages),messages=messages) if REVISION!=8 else \
        dict(channel='photoprints',source_content2_sha256=src['source_content2_sha256'],derived_from='photoprints-messages-v1-ko.json',
        note=notes[8],count=len(messages),messages=messages)
    raw=json.dumps(out,ensure_ascii=False,indent=1)
    write='--write' in sys.argv
    if write and TARGET.exists() and TARGET.read_text(encoding='utf-8')!=raw:raise SystemExit(f'Existing v{REVISION} messages preserved; snapshot a new revision instead')
    if write:
        TARGET.write_text(raw,encoding='utf-8')
        REPORT.write_text(json.dumps(dict(changed=len(changed),entries=report,config_sha256=hashlib.sha256(raw.encode('utf-8')).hexdigest()),ensure_ascii=False,indent=1),encoding='utf-8')
    counts={};[counts.__setitem__(r['action'],counts.get(r['action'],0)+1) for r in report]
    print(f'v{REVISION} messages:',len(messages),'changed vs v1:',len(changed),'actions:',counts)
    for r in report:
        if r['action'] in('split','rewrap') or r['jp'] in OVERRIDES or r['jp'] in SHORTER or r['min_scale']<0.9:
            print(f"[{r['action']}] budget {r['allowed_lines']} lines {r['lines']} scale {r['min_scale']} {r['panes'][0]}\n   {r['v8']!r}")
    low=[r for r in report if r['min_scale']<tf.MIN_SCALE]
    print('below MIN_SCALE',tf.MIN_SCALE,':',len(low),[(r['panes'][0],r['min_scale']) for r in low])
if __name__=='__main__':main()
