"""Text/display fixes found in the 2026-11-16 online Dolphin review (docs/reference/ONLINE_DOLPHIN_REVIEW_2026_11_16.md).

Each fix derives a new build from its parent WAD and changes only the named file inside one content:
  forecast  v108 <- v107  content 9 weather_layout set_area1 textT??1: shorter title (period no longer wraps)
  news      v30  <- v29   content 9 fonts without '간' get it ('0시간 54분 전' lost '간')
  nintendo  v19  <- v18   content 5 BMGs: 'Wii 게시판' -> 'Wii 알림판' (Korean Wii menu term)
  food      hardware-v16 <- v15  content 1 (LZ11 exe) 'Wii 게시판' -> 'Wii 알림판'; content 2 welcome subject '이 채널은'
  wiiroom   v69  <- v68   content 2 msg/message.lex: 'Wii 게시판' -> 'Wii 알림판'
  mii-contest v33 <- v32  content 4 Basic_*.szs message 335: page break between the two bullets
"""
import hashlib, struct
from pathlib import Path

from .channels import ChannelArchive, layout_sections, rebuild_layout, replace_textbox, textbox, compress_lz10, load_library
from . import kirbytv_u8

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / 'workspace/channels/forecast/references/NotoSansKR.ttf'
OLD_BOARD, NEW_BOARD = 'Wii 게시판', 'Wii 알림판'


def sha(b): return hashlib.sha256(b).hexdigest()


def _lz77():
    load_library(); from libWiiPy.archive import decompress_lz77
    return decompress_lz77


def _replace_u16(data, old, new, expected=None):
    a, b = old.encode('utf-16-be'), new.encode('utf-16-be')
    if len(a) != len(b): raise ValueError('Same-length replacement required')
    out = bytearray(data); hits = []; at = data.find(a)
    while at >= 0:
        if at % 2 == 0: hits.append(at)
        at = data.find(a, at + 1)
    if not hits or (expected is not None and len(hits) != expected): raise ValueError(f'{old!r}: {len(hits)} hits')
    for at in hits: out[at:at + len(b)] = b
    return bytes(out), len(hits)


def forecast(contents):
    c9 = ChannelArchive(contents[9]); lz = _lz77()
    inner = ChannelArchive(lz(c9.get('weather_layout.arc.LZ')))
    path = 'arc/blyt/set_area1.brlyt'; sections = layout_sections(inner.get(path)); n = 0
    new = '현재 위치와 가까운 지역을 선택해 주세요.'
    for i, s in enumerate(sections):
        e = textbox(s)
        if e and e[0].startswith('textT') and e[0].endswith('1') and e[1] == '현재 위치와 가장 가까운 지역을 선택해 주세요.':
            sections[i] = replace_textbox(s, new); n += 1
    if n != 7: raise ValueError('Forecast set_area1 panes differ')
    inner = ChannelArchive(inner.replace(path, rebuild_layout(inner.get(path), sections)))
    data = inner.compact(); packed = compress_lz10(data)
    if lz(packed) != data: raise ValueError('LZ10 roundtrip')
    return {9: ChannelArchive(c9.replace('weather_layout.arc.LZ', packed)).compact()}, dict(panes=n, text=new)


def news(contents):
    from .channel_font import extend_font, font_data
    c9 = ChannelArchive(contents[9]); lz = _lz77(); fonts = []
    for path in sorted(p for p in c9.files if p.endswith('.brfnt.LZ')):
        raw = lz(c9.get(path)); _, mapping, _ = font_data(raw)
        if ord('시') in mapping and ord('분') in mapping and ord('간') not in mapping:
            data, record = extend_font(raw, '간', FONT); packed = compress_lz10(data)
            if lz(packed) != data: raise ValueError('LZ10 roundtrip')
            c9 = ChannelArchive(c9.replace(path, packed)); fonts.append(path)
    if 'font_news_date.brfnt.LZ' not in fonts: raise ValueError('News date font not extended')
    return {9: c9.compact()}, dict(added='간', fonts=fonts)


def nintendo(contents):
    out, n = _replace_u16(contents[5], OLD_BOARD, NEW_BOARD, expected=9)
    return {5: out}, dict(replaced=n, files='message/promotion_message_{UE,UF,US}.bmg (in place, same length)')


def food(contents):
    from .wiiroom_formats import decompress_lz11, reencode_lz11_same_size
    exe = decompress_lz11(contents[1]); edited, n = _replace_u16(exe, OLD_BOARD, NEW_BOARD, expected=1)
    c1 = reencode_lz11_same_size(contents[1], edited)
    c2 = ChannelArchive(contents[2]); arc = ChannelArchive(c2.get('Dtest/DtestWelcome.arc'))
    path = 'Welcome/blyt/welcome_layout.brlyt'; sections = layout_sections(arc.get(path)); m = 0
    for i, s in enumerate(sections):
        e = textbox(s)
        if e and e[0] == 'weT_08_txt_00' and e[1].startswith('채널은\n'):
            sections[i] = replace_textbox(s, '이 ' + e[1]); m += 1
    if m != 1: raise ValueError('Food welcome pane differs')
    arc_data = kirbytv_u8.edit(arc_bytes := c2.get('Dtest/DtestWelcome.arc'), replace={path: rebuild_layout(arc.get(path), sections)})
    c2_data = kirbytv_u8.edit(contents[2], replace={'Dtest/DtestWelcome.arc': arc_data})
    return {1: c1, 2: c2_data}, dict(executable_replaced=n, welcome='이 채널은', lz11_same_raw_size=True)


def wiiroom(contents):
    lz = _lz77(); c2 = contents[2]; a = ChannelArchive(c2)
    raw = lz(a.get('msg/message.lex')); edited, n = _replace_u16(raw, OLD_BOARD, NEW_BOARD, expected=1)
    packed = compress_lz10(edited)
    if lz(packed) != edited: raise ValueError('LZ10 roundtrip')
    return {2: kirbytv_u8.edit(c2, replace={'msg/message.lex': packed})}, dict(replaced=n)


MII_OLD = '공개됩니다.\n\n● 개인정보나'
MII_NEW = '공개됩니다.\n\n\n● 개인정보나'   # page 1 = 7 lines: the second bullet starts page 2


def _bmg_replace(data, old, new):
    from .votes_resources import bmg_sections, bmg_message
    sections = bmg_sections(data); inf = bytearray(next(s for s in sections if s[:4] == b'INF1')); dat = next(s for s in sections if s[:4] == b'DAT1')
    count = int.from_bytes(inf[8:10], 'big'); stride = int.from_bytes(inf[10:12], 'big')
    payload = bytearray(b'\0\0'); hits = 0; seen = {}
    a, b = old.encode('utf-16-be'), new.encode('utf-16-be')
    for i in range(count):
        at = 16 + i * stride; offset = int.from_bytes(inf[at:at + 4], 'big')
        if offset == 0 and i: inf[at:at + 4] = bytes(4); continue
        msg = bmg_message(dat, 8 + offset)
        k = msg.find(a)
        if k >= 0 and k % 2 == 0: msg = msg[:k] + b + msg[k + len(a):]; hits += 1
        if offset in seen: inf[at:at + 4] = seen[offset].to_bytes(4, 'big'); continue
        seen[offset] = len(payload); inf[at:at + 4] = len(payload).to_bytes(4, 'big'); payload.extend(msg + b'\0\0')
    rebuilt = bytearray(b'DAT1' + bytes(4) + payload); rebuilt.extend(bytes(-len(rebuilt) % 32)); rebuilt[4:8] = len(rebuilt).to_bytes(4, 'big')
    out = bytearray(data[:32] + b''.join(bytes(inf) if s[:4] == b'INF1' else bytes(rebuilt) if s[:4] == b'DAT1' else s for s in sections))
    out[8:12] = len(out).to_bytes(4, 'big'); bmg_sections(out)
    return bytes(out), hits


def mii_contest(contents):
    from .votes_resources import decode_yaz0, encode_yaz0
    c4 = contents[4]; a = ChannelArchive(c4); replace = {}
    for path in sorted(p for p in a.files if '/Message/Bmg/Basic_' in p):
        raw = decode_yaz0(a.get(path)); new, hits = _bmg_replace(raw, MII_OLD, MII_NEW)
        if hits != 1: raise ValueError(f'{path}: {hits} hits')
        packed = encode_yaz0(new)
        if decode_yaz0(packed) != new: raise ValueError('Yaz0 roundtrip')
        replace[path] = packed
    if len(replace) != 10: raise ValueError('Expected 10 Basic BMGs')
    return {4: kirbytv_u8.edit(c4, replace=replace)}, dict(bmgs=len(replace), message=335)


STEPS = {
    'forecast': ('build-v107', 'build-v108', forecast),
    'news': ('build-v29', 'build-v30', news),
    'nintendo': ('build-v18', 'build-v19', nintendo),
    'food': ('hardware-v15', 'hardware-v16', food),
    'wiiroom': ('build-v68', 'build-v69', wiiroom),
    'mii-contest': ('build-v32', 'build-v33', mii_contest),
}
