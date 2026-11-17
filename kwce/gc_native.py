"""Exact-43K local GC menu prototype; no real console installation support.

Restores the Wii/GC save selection and correct child return animations/states.
The source-level behavior comes from the pinned wii-ipl SettingSelect source.
"""
import hashlib,struct
from .patches import MENU_SHA1,gc_detection_prototype

def dol_offset(data,address):
    for i in range(18):
        off,addr,size=[struct.unpack_from('>I',data,p+4*i)[0] for p in (0,0x48,0x90)]
        if addr<=address<addr+size:
            if off+address-addr+4>len(data):raise ValueError('DOL section out of bounds')
            return off+address-addr
    raise ValueError('Unmapped DOL address')

def patch_gc_native(data,japanese_cards=False,japanese_comments=False):
    if japanese_comments and not japanese_cards:raise ValueError('Japanese comments require Japanese test cards')
    if hashlib.sha1(data).hexdigest()!=MENU_SHA1:raise ValueError('Only original 43K DOL supported')
    result=bytearray(data);changes=[]
    def replace(address,value,expected=None,call=False,label=''):
        off=dol_offset(data,address);old=struct.unpack_from('>I',data,off)[0]
        if expected is not None and old!=expected:raise ValueError('Instruction guard mismatch')
        if call and old&0xfc000003!=0x48000001:raise ValueError('Expected direct call')
        struct.pack_into('>I',result,off,value);changes.append(dict(address=hex(address),purpose=label))
    # Savedata now opens third-level Wii/GC choice instead of a Wii child.
    replace(0x814089b0,0x38000000,0x3800000d,label='clear direct child scene selection')
    replace(0x814089d0,0x60000000,call=True,label='skip direct Wii memory child creation')
    replace(0x814089e8,0x60000000,call=True,label='keep settings back button visible')
    # Return from Wii saves to third-level Wii/GC selection, not second level.
    replace(0x81408310,0x3bc00022,0x3bc00014,label='Wii back animation')
    replace(0x81408314,0x3ba00023,0x3ba00015,label='GC in animation')
    replace(0x81408430,0x38000008,0x38000005,label='return Wii/GC children to third-level state')
    # Preserve the adjacent channel child return at 0x81408404 (state 5).
    if result[dol_offset(data,0x81408404):dol_offset(data,0x81408404)+4]!=data[dol_offset(data,0x81408404):dol_offset(data,0x81408404)+4]:raise ValueError('Channel return changed')
    gc,detail=gc_detection_prototype(data)
    off=detail['file_offset'];result[off:off+4]=gc[off:off+4]
    changes.append(dict(address=detail['address'],purpose='experimental GC fallback acceptance'))
    if japanese_cards:
        a=0x815375ac;off=dol_offset(data,a);w=struct.unpack_from('>I',data,off)[0]
        d=w&0x3fffffc;d=d-(1<<26) if d&(1<<25) else d
        if w&0xfc000003!=0x48000001 or a+d!=0x81508bf8:raise ValueError('CARDInit font call guard mismatch')
        replace(a,0x38600001,call=True,label='CARD encoding Shift-JIS for Japanese GC test cards')
    if japanese_comments:
        # 43K removes the Japanese ENC map but retains PrFILE2 CP932 support.
        a=0x813cd634;off=dol_offset(data,a);w=struct.unpack_from('>I',data,off)[0]
        d=w&0x3fffffc;d=d-(1<<26) if d&(1<<25) else d
        if w&0xfc000003!=0x48000001 or a+d!=0x81363390:raise ValueError('GC comment converter call guard mismatch')
        from pathlib import Path
        from .gc_comment import build_decoder,ADDRESS
        blob,decoder=build_decoder(Path(__file__).resolve().parents[1])
        start=dol_offset(data,ADDRESS)
        # The original ENC map flag load is followed by bne past its -2
        # return. Exact 43K hash above guards the whole disabled function.
        check=dol_offset(data,0x81545864)
        if struct.unpack_from('>III',data,check)!=(0x2c000000,0x4082000c,0x3860fffe):raise ValueError('Disabled Japanese ENC map guard mismatch')
        result[start:start+len(blob)]=blob
        replace(a,0x48000001|((ADDRESS-a)&0x3fffffc),call=True,label='bounded CP932 decoding of Japanese GC card comments')
    record=dict(instructions_changed=len(changes),changes=changes,disc_execution_verified=False,memory_card_UI_verified=False)
    if japanese_comments:record['comment_adapter']=decoder
    return bytes(result),record
