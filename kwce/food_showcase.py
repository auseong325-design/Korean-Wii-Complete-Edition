"""Food channel showcase mode: order confirmation and shop requests complete on the console only.

Background (2026-11-16 online Dolphin trace, docs/channels/food.md): on the standard edition the
WiiLink demo service answers every catalogue/basket request, and the final order is a POST
`webApi_order_done` that carries member[Name1/2], member[Address1..6], member[TelNo], member[Mail],
member[PostNo] from the console's address data. `webApi_inquiry_done` ("가게 요청") is the other
POST. The user asked that orders never leave the console.

Patch (executable, content 1):
  * PostHTTPData (0x8002c6a8, `this`, action index in r4) now starts with a branch to a routine in a
    new text section. For action 0x18 (order_done) and 0x16 (inquiry_done) it does not touch the
    network: it fills the HTTP object exactly as the NHTTP completion callback does for a successful
    reply (body buffer +0x0c/+0x10, status +0x18 = 200, error +0x1c = 0, ssl +0x20 = 0, state +0x14 =
    0, done +0x24 = 1, retry +0x28 = 0) with an XML body in the WiiLink server's format. order_done's
    orderDay/hour come from the console clock (OSGetTime -> OSTicksToCalendarTime -> sprintf).
    Every other action runs the original code unchanged.
  * The routine lives in .text1 at 0x8010b308..0x8010b9bc, inside the MetroTRK debugger. TRK starts only
    when __start sees a debug monitor (InitMetroTRK 0x8010da98 / 0x8010db30); the boot loader clears
    those low-memory flags, so on a retail boot this span is never executed. A reachability pass over
    every branch, lis/addi pointer and data pointer into the TRK region, excluding only those two
    debugger entries, reaches no word of the span (docs/channels/food.md, 2026-11-16).
  * Rejected (kept for the record): a new DOL text section. The channel's boot loader (content 9)
    reads sections back to back and never runs code placed there (Dolphin: request never sent).
"""
import hashlib, struct
from .ppc_patch import assemble, to_file, write_code

POST = 0x8002c6a8
POST_FIRST = 0x9421f7b0          # stwu r1,-0x850(r1)
ARENA_SITES = (0x8019a054, 0x8019a0fc)
ARENA_LO = 0x804865c0
SECTION = 0x8010b308
SECTION_END = 0x8010b9bc
TRK_SPAN_SHA256 = '28494863ae3b2151bc9b8f8269b08667605207dd4497f1dbc2ea7a33f7dfbd12'

SYMBOLS = dict(post_resume=0x8002c6ac, mem_alloc=0x800229c0, mem_free=0x800229d4, memset=0x80004104,
               strcat=0x8010216c, sprintf=0x80101e30, os_get_time=0x801a3f70, ticks_to_cal=0x801a41bc)
ORDER_MESSAGE = 'Thank you! Your order has been placed. (KWCE showcase: kept on this Wii, not sent.)'
# Same shape as the live WiiLink reply recorded 2026-11-16 (every value is a CDATA section; the
# channel's XML reader takes text only from CDATA). orderDay/hour carry the console's local time.
XML_ORDER = ('<response>\n  <Message>\n    <contents><![CDATA[' + ORDER_MESSAGE + ']]></contents>\n  </Message>\n'
             '  <order_id><![CDATA[%d]]></order_id>\n  <orderDay><![CDATA[%s]]></orderDay>\n'
             '  <hashKey><![CDATA[KWCE-LOCAL]]></hashKey>\n  <hour><![CDATA[%s]]></hour>\n'
             '  <apiStatus>\n    <code><![CDATA[0]]></code>\n  </apiStatus>\n  <version><![CDATA[1]]></version>\n'
             '</response>')
XML_INQUIRY = ('<response>\n  <apiStatus>\n    <code><![CDATA[0]]></code>\n  </apiStatus>\n'
               '  <version><![CDATA[1]]></version>\n</response>')
DATE_FMT = '%04d%02d%02d%02d%02d'
BODY = 0x400


def _asciz(label, text):
    raw = text.encode('ascii') + b'\0'
    return f'{label}:\n  .byte ' + ','.join(str(b) for b in raw) + '\n  .balign 4\n'


SOURCE = f'''
cave:
    cmpwi r4, 0x18
    beq fake
    cmpwi r4, 0x16
    beq fake
    stwu r1, -0x850(r1)
    b post_resume
fake:
    stwu r1, -0x60(r1)
    mflr r0
    stw r0, 0x64(r1)
    stmw r28, 0x50(r1)
    mr r31, r3
    mr r30, r4
    lwz r3, 0xc(r31)
    cmpwi r3, 0
    beq 1f
    bl mem_free
    li r0, 0
    stw r0, 0xc(r31)
1:  li r3, {BODY + 2}
    bl mem_alloc
    cmpwi r3, 0
    beq fail
    stw r3, 0xc(r31)
    mr r29, r3
    li r0, {BODY}
    stw r0, 0x10(r31)
    li r4, 0
    li r5, {BODY + 2}
    bl memset
    cmpwi r30, 0x18
    bne inquiry
    bl os_get_time
    addi r5, r1, 0x10
    bl ticks_to_cal
    addi r3, r1, 0x38
    lis r4, fmt_date@ha
    addi r4, r4, fmt_date@l
    lwz r5, 0x24(r1)
    lwz r6, 0x20(r1)
    addi r6, r6, 1
    lwz r7, 0x1c(r1)
    lwz r8, 0x18(r1)
    lwz r9, 0x14(r1)
    crclr 6
    bl sprintf
    lwz r5, 0x1c(r1)
    mulli r5, r5, 10000
    lwz r0, 0x18(r1)
    mulli r0, r0, 100
    add r5, r5, r0
    lwz r0, 0x14(r1)
    add r5, r5, r0
    mr r3, r29
    lis r4, xml_order@ha
    addi r4, r4, xml_order@l
    addi r6, r1, 0x38
    addi r7, r1, 0x38
    crclr 6
    bl sprintf
    b done
inquiry:
    mr r3, r29
    lis r4, xml_inquiry@ha
    addi r4, r4, xml_inquiry@l
    bl strcat
done:
    li r0, 0
    stw r0, 0x14(r31)
    stw r0, 0x1c(r31)
    stw r0, 0x20(r31)
    stw r0, 0x28(r31)
    li r0, 200
    stw r0, 0x18(r31)
    li r0, 1
    stw r0, 0x24(r31)
    li r3, 1
    b out
fail:
    li r3, 0
out:
    lmw r28, 0x50(r1)
    lwz r0, 0x64(r1)
    mtlr r0
    addi r1, r1, 0x60
    blr
    .balign 4
{_asciz('fmt_date', DATE_FMT)}{_asciz('xml_order', XML_ORDER)}{_asciz('xml_inquiry', XML_INQUIRY)}
'''


def _insert_text_section(dol, address, code):
    """Add a text section and lay every section out back to back (loader reads them sequentially)."""
    off = list(struct.unpack_from('>18I', dol, 0)); addr = list(struct.unpack_from('>18I', dol, 0x48))
    size = list(struct.unpack_from('>18I', dol, 0x90))
    pos = 0x100
    for i in range(18):
        if size[i]:
            if off[i] != pos: raise ValueError('DOL is not sequential')
            pos += size[i]
    if pos != len(dol): raise ValueError('DOL has trailing data')
    slot = next(i for i in range(7) if size[i] == 0)
    if any(size[i] for i in range(slot, 7)): raise ValueError('Text slots not contiguous')
    for i in range(18):
        if size[i] and not (address + len(code) <= addr[i] or addr[i] + size[i] <= address): raise ValueError('Section overlap')
    blob = code + bytes((-len(code)) % 32)
    bodies = [bytes(dol[off[i]:off[i] + size[i]]) if size[i] else b'' for i in range(18)]
    bodies[slot] = blob; addr[slot] = address; size[slot] = len(blob)
    out = bytearray(dol[:0x100]); pos = 0x100
    for i in range(18):
        off[i] = pos if size[i] else 0; out += bodies[i]; pos += size[i]
    struct.pack_into('>18I', out, 0, *off); struct.pack_into('>18I', out, 0x48, *addr); struct.pack_into('>18I', out, 0x90, *size)
    return out, slot


def patch(exe, parent_sha256):
    if hashlib.sha256(exe).hexdigest() != parent_sha256:
        raise ValueError('Food executable identity differs')
    if len(XML_ORDER) + 40 > BODY:
        raise ValueError('Order body exceeds buffer')
    dol = bytearray(exe)
    at = to_file(dol, POST)
    if struct.unpack_from('>I', dol, at)[0] != POST_FIRST:
        raise ValueError('PostHTTPData prologue differs')
    code = assemble(SOURCE, SECTION, SYMBOLS)
    if len(code) > SECTION_END - SECTION:
        raise ValueError('Showcase routine exceeds the TRK span')
    original_sha = write_code(dol, SECTION, code, SECTION_END, expected_sha256=TRK_SPAN_SHA256)
    slot = None
    branch = assemble('b cave', POST, {'cave': SECTION})
    dol[at:at + 4] = branch
    return bytes(dol), dict(hook=hex(POST), routine=hex(SECTION), span_end=hex(SECTION_END), bytes=len(code),
                            replaced_trk_sha256=original_sha, actions={'0x18': 'webApi_order_done', '0x16': 'webApi_inquiry_done'},
                            order_message=ORDER_MESSAGE, output_sha256=hashlib.sha256(dol).hexdigest())


# Shift-JIS strings cannot hold Hangul; the two order texts that showed blank kanji become ASCII.
SJIS_TEXT = {
    0x802d710c: ('通常の出前注文です (待ち時間 約%d分)', 'ASAP (about %d min)'),
    0x802d71b3: ('%02d:%02dに\r\n「%s」\r\nへ出前を注文しました。\r\n\r\nお届けは、\r\n\u3000待ち時間 約%3d分\r\n\r\n'
                 'くわしくは出前チャンネルの\r\n「注文きろく」をごらんください。',
                 '%02d:%02d  Order for\r\n"%s"\r\nkept on this Wii only\r\n(showcase: not sent).\r\n\r\n'
                 'Wait: about %3d min\r\n\r\nSee Order History.'),
}


def sjis_text(dol):
    import re
    out = bytearray(dol); rows = []
    for va, (old, new) in SJIS_TEXT.items():
        at = to_file(out, va); raw_old = old.encode('cp932')
        end = out.index(b'\0', at)
        if bytes(out[at:end]) != raw_old: raise ValueError(f'SJIS text at {va:#x} differs')
        fmt = lambda t: re.findall(r'%[-+ #0-9.]*[a-zA-Z]', t)
        if fmt(old) != fmt(new): raise ValueError('Format specifiers changed')
        raw_new = new.encode('ascii')
        if len(raw_new) > len(raw_old): raise ValueError('ASCII text exceeds slot')
        out[at:end] = raw_new + bytes(len(raw_old) - len(raw_new)); rows.append(hex(va))
    return bytes(out), rows


DIALOG_PANE = ('Dtest/DtestDialog.arc', 'Dialog/blyt/dialogue_layout.brlyt', 'dic_T_msgH_00a')


def dialog_quotes(content2):
    from .channels import ChannelArchive, layout_sections, rebuild_layout, replace_textbox, textbox
    from . import kirbytv_u8
    arc_path, lyt, pane = DIALOG_PANE
    c2 = ChannelArchive(content2); arc = ChannelArchive(c2.get(arc_path)); sections = layout_sections(arc.get(lyt)); n = 0
    for i, sec in enumerate(sections):
        e = textbox(sec)
        if e and e[0] == pane and '“가게 선택 화면”' in e[1]:
            sections[i] = replace_textbox(sec, e[1].replace('“가게 선택 화면”', '「가게 선택 화면」')); n += 1
    if n != 1: raise ValueError('Food dialog pane differs')
    arc_data = kirbytv_u8.edit(c2.get(arc_path), replace={lyt: rebuild_layout(arc.get(lyt), sections)})
    return kirbytv_u8.edit(content2, replace={arc_path: arc_data})
