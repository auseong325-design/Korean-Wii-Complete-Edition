"""Korean time order for the USA Forecast v7 executable (content 1).

English builds hour, minute, a.m./p.m. and date as separate pieces. Korean
needs the meridiem before the hour, so the three builders are rewritten:
current-observation line (date, meridiem, time, suffix), the today/tomorrow
period labels and the large clock (meridiem now joins the time string).
"""
from .ppc_patch import assemble,to_file,write_code

SYMBOLS=dict(wcscpy=0x8016f588,wcslen=0x8016f56c,wcscat=0x8016f5a4,itoa=0x800362d8)
AM,PM=0x8019b720,0x8019b72c          # 'a.m.' / 'p.m.' (current line, periods)
SUFFIX=0x8019bbb4                     # English 'As of ' slot, reused for the suffix
HOUR_SUFFIX=0x8019b4b8                # ':00 '

OBSERVATION='''
  li r0,0
  sth r0,0x85c(r30)
  addi r3,r30,0x85c
  bl wcslen
  slwi r0,r3,1
  lwz r3,0x18(r1)
  add r4,r30,r0
  li r5,2
  addi r4,r4,0x85c
  addi r3,r3,1
  li r6,1
  bl itoa
  li r0,0x2f
  addi r4,r3,2
  sth r0,0(r3)
  li r5,2
  li r6,1
  lwz r3,0x14(r1)
  bl itoa
  addi r3,r30,0x85c
  addi r4,r13,-0x75d8
  bl wcscat
  lwz r0,0x10(r1)
  cmpwi r0,0xc
  bge 1f
  lwz r4,-0x7448(r13)
  b 2f
1:lwz r4,-0x7444(r13)
2:addi r3,r30,0x85c
  bl wcscat
  addi r3,r30,0x85c
  bl wcslen
  slwi r0,r3,1
  mr r3,r31
  add r4,r30,r0
  li r5,2
  addi r4,r4,0x85c
  li r6,0
  bl itoa
  li r0,0x3a
  addi r4,r3,2
  sth r0,0(r3)
  li r5,2
  li r6,1
  lwz r3,0xc(r1)
  bl itoa
  addi r3,r30,0x85c
  lis r4,SUFFIX@ha
  addi r4,r4,SUFFIX@l
  bl wcscat
'''

PERIODS='''
  cmpwi r23,0xc
  bge 1f
  lwz r4,-0x7448(r13)
  b 2f
1:lwz r4,-0x7444(r13)
2:addi r3,r28,0x7370
  bl wcscpy
  mulhw r0,r29,r23
  addi r3,r28,0x7370
  srawi r0,r0,1
  srwi r4,r0,31
  add r0,r0,r4
  mulli r0,r0,0xc
  subf r0,r0,r23
  slwi r0,r0,2
  lwzx r4,r30,r0
  bl wcscat
  addi r3,r28,0x7370
  addi r4,r31,-0x4b48
  bl wcscat
  addi r3,r28,0x7370
  addi r4,r13,-0x754c
  bl wcscat
  addi r23,r23,6
  mulhw r0,r29,r23
  srawi r0,r0,2
  srwi r4,r0,31
  add r0,r0,r4
  mulli r0,r0,0x18
  subf r23,r0,r23
  cmpwi r23,0xc
  bge 3f
  lwz r4,-0x7448(r13)
  b 4f
3:lwz r4,-0x7444(r13)
4:addi r3,r28,0x7370
  bl wcscat
  mulhw r0,r29,r23
  addi r3,r28,0x7370
  srawi r0,r0,1
  srwi r4,r0,31
  add r0,r0,r4
  mulli r0,r0,0xc
  subf r0,r0,r23
  slwi r0,r0,2
  lwzx r4,r30,r0
  bl wcscat
  addi r3,r28,0x7370
  addi r4,r31,-0x4b48
  bl wcscat
'''

# Clock string builder rewritten in place (same 28 instructions): writes the
# meridiem as three UTF-16 units, then the 12-hour value and the minutes.
# A separate code section in low memory crashed at boot, so none is added.
CLOCK='''
  lis r30,0x801f
  lis r31,0x801f
  addi r31,r31,0x6e58
  lwz r3,8(r31)
  li r4,-0x37fc
  cmpwi r3,0xc
  blt 1f
  li r4,-0x293c
  addi r3,r3,-0xc
1:cmpwi r3,0
  bne 2f
  li r3,0xc
2:sth r4,0x7372(r30)
  li r0,-0x39dc
  sth r0,0x7370(r30)
  li r0,0x20
  sth r0,0x7374(r30)
  addi r4,r30,0x7376
  li r5,2
  li r6,0
  bl itoa
  li r0,0x3a
  sth r0,0(r3)
  addi r4,r3,2
  lwz r3,4(r31)
  li r5,2
  li r6,1
  bl itoa
'''

NOP=b'\x60\x00\x00\x00'

def _string(dol,va,slot,text):
    at=to_file(dol,va,slot);encoded=text.encode('utf-16-be')+b'\0\0'
    if len(encoded)>slot:raise ValueError('Time string slot overflow')
    dol[at:at+slot]=encoded+bytes(slot-len(encoded))

def korean_time(executable,parts=('observation','periods','clock'),clock_language_fallback=False,clock_font_fallback=False,clock_region_enabled=False,clock_display_enabled=False,clock_main_views_only=False,clock_active_view_only=False):
    dol=bytearray(executable);sym=dict(SYMBOLS,SUFFIX=SUFFIX)
    expected={}
    for name,source,start,end in[('observation',OBSERVATION,0x80023474,0x80023554),('periods',PERIODS,0x8002486c,0x80024944)]:
        if name not in parts:continue
        expected[name]=write_code(dol,start,assemble(source,start,sym),end)
    if 'clock' in parts:
        expected['clock']=write_code(dol,0x8003c7b4,assemble(CLOCK,0x8003c7b4,sym),0x8003c824)
        # The trailing small meridiem prints are no longer needed.
        for va in(0x8003c8fc,0x8003c910):
            at=to_file(dol,va)
            if dol[at]>>2!=0x12:raise ValueError('Expected bl at clock print site')
            dol[at:at+4]=NOP
        if clock_language_fallback:
            # Retained v27 diagnostic hypothesis for byte reproduction.
            # Runtime inspection later confirmed this title already uses
            # internal UI language 1; this is not the final visibility fix.
            expected['clock_language_dispatch']=write_code(dol,0x8003b9d8,
                assemble('li r0,1',0x8003b9d8,{}),0x8003b9dc,
                expected_sha256='58d35eee0c25d57b8c30b44425ffb939ee82ab325acae52d0ed664205285136c')
        if clock_font_fallback:
            # Retained v28 diagnostic; the final build preserves the
            # original internal language selection.
            for va in (0x8003b4b0,0x8003b4c4):
                expected[f'clock_font_dispatch_{va:x}']=write_code(dol,va,
                    assemble('li r0,1',va,{}),va+4,
                    expected_sha256='58d35eee0c25d57b8c30b44425ffb939ee82ab325acae52d0ed664205285136c')
        if clock_region_enabled:
            # USA initializes the shared clock suppression flag to 1. The
            # Korean edition enables the existing clock; r29 is the zero
            # register established in this constructor. Other transient
            # suppression (dialogs/HOME) and locale checks remain in place.
            expected['clock_region_visibility']=write_code(dol,0x8000d6f4,
                assemble('stb r29,-0x7378(r13)',0x8000d6f4,{}),0x8000d6f8,
                expected_sha256='3160d0e41880e40f4a964a7634c74ecbe1837abf4c7ed09a22d911218715471a')
        if clock_display_enabled:
            # v30..v61 reproduction only. Enabling all shared views causes
            # globe-header overlap; the final build uses the active callback.
            expected['clock_display_enabled']=write_code(dol,0x8003d02c,
                assemble('li r0,0',0x8003d02c,{}),0x8003d030,
                expected_sha256='f58141d293e1987577a5ad9919f794cf87d1357eccbc112780ae8ea137a3af7b')
        if clock_main_views_only:
            # USA skips the two clears performed on entry/return to the
            # ordinary forecast view. Clear there without changing the
            # original region-dependent control flow or r0/CR/LR values.
            # Reuse only the now-unused small-meridiem print setup, inside
            # the original clock function; no extra DOL section is added.
            cave=0x8003c8b8
            code='''
              b END
            first:
              bne 1f
              li r0,0
              stb r0,-0x7378(r13)
              li r0,1
              b ENTER_SKIP
            1:b ENTER_NEXT
            second:
              bne 2f
              li r0,0
              stb r0,-0x7378(r13)
              li r0,1
              b RETURN_SKIP
            2:b RETURN_NEXT
            '''
            expected['clock_main_view_trampolines']=write_code(dol,cave,
                assemble(code,cave,dict(END=0x8003c914,ENTER_SKIP=0x8000f49c,ENTER_NEXT=0x8000efa8,
                    RETURN_SKIP=0x8000f6ec,RETURN_NEXT=0x8000f6e4)),0x8003c914,
                expected_sha256='b2038d6b23b692cff421523d033c37143d45b1dafbd585ea6b87c5b65b846eb4')
            for va,dest,guard in[(0x8000efa4,cave+4,'6c755f9c8868413224fcf50bfa1c52f06b6d8610a1c96c600681c7a107f91a64'),
                                 (0x8000f6e0,cave+28,'a5905298a6fa50ae13877ce04ce3537d07314a23d12ce574736c394391fede76')]:
                expected[f'clock_main_view_{va:x}']=write_code(dol,va,assemble('b DEST',va,dict(DEST=dest)),va+4,expected_sha256=guard)
        if clock_active_view_only:
            # The main and globe UI share an outer frame. Gate the existing
            # fade function by the actual active callback of the guarded
            # weather root (0x8019a064): 0x8000ef08 is the forecast view.
            # Other root types retain their original suppression flag.
            # r0 and CR0 are overwritten by the original next instruction;
            # every other GPR and LR stays untouched.
            cave=0x8003c8b8
            code='''
              b END
            active:
              lwz r0,0(r3)
              xoris r0,r0,0x8019
              cmplwi r0,0xa064
              bne original
              lwz r0,0xc8(r3)
              xoris r0,r0,0x8000
              cmplwi r0,0xef08
              bne hidden
              li r0,0
              b CONTINUE
            hidden:
              li r0,1
              b CONTINUE
            original:
              lbz r0,-0x7378(r13)
              b CONTINUE
            '''
            expected['clock_active_view_code']=write_code(dol,cave,
                assemble(code,cave,dict(END=0x8003c914,CONTINUE=0x8003d030)),0x8003c914,
                expected_sha256='b2038d6b23b692cff421523d033c37143d45b1dafbd585ea6b87c5b65b846eb4')
            expected['clock_active_view_hook']=write_code(dol,0x8003d02c,
                assemble('b DEST',0x8003d02c,dict(DEST=cave+4)),0x8003d030,
                expected_sha256='f58141d293e1987577a5ad9919f794cf87d1357eccbc112780ae8ea137a3af7b')
    for va,slot,text in[(AM,12,'오전 '),(PM,10,'오후 '),(SUFFIX,20,' 기준'),(HOUR_SUFFIX,10,':00')]:
        _string(dol,va,slot,text)
    return bytes(dol),dict(order='date, meridiem, time, suffix; period labels and clock meridiem first',original_code_sha256=expected,clock='meridiem prefix written in the clock buffer; no extra DOL section',clock_language_fallback=clock_language_fallback,clock_font_fallback=clock_font_fallback,clock_region_enabled=clock_region_enabled,clock_display_enabled=clock_display_enabled,clock_main_views_only=clock_main_views_only,clock_active_view_only=clock_active_view_only)
