"""Synthetic-only PPC execution of the pinned local 43K CARD code; no physical I/O."""
from pathlib import Path
import sys,struct,re,hashlib,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.gc_native import patch_gc_native,dol_offset
from kwce.patches import MENU_SHA1
from kwce.gc_fixture import card_header,checksum
from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_13,UC_PPC_REG_LR,UC_PPC_REG_PC
original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes();assert hashlib.sha1(original).hexdigest()==MENU_SHA1
symbols={m[0]:int(m[1],16) for m in re.findall(r'^([^ =]+) = \.\w+:0x([0-9A-Fa-f]+);',(ROOT/'external/wii-ipl/config/43K/symbols.txt').read_text(),re.M)}
getter=symbols['__CARDGetFontEncode'];w=struct.unpack_from('>I',original,dol_offset(original,getter))[0];disp=w&65535;disp=disp-65536 if disp&32768 else disp
assert w>>26==40 and ((w>>16)&31)==13
sda=symbols['__CARDEncode']-disp
RETURN=0x80003000;HEADER=0x80010000;SRAM=0x80014000;STACK=0x80030000

def run(font,patched,encoding,corrupt=False,candidate=False,slot=0,header_data=None):
 data=patch_gc_native(original,japanese_cards=patched)[0]
 if candidate:
  from kwce.gc_card_encoding import patch_card_encodings
  data=patch_card_encodings(data)[0]
 u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
 for i in range(18):
  off,addr,size=[struct.unpack_from('>I',data,p+4*i)[0] for p in (0,0x48,0x90)]
  if size:u.mem_write(addr,data[off:off+size])
 u.mem_write(symbols['__CARDBlock'],bytes(0x230))
 u.reg_write(UC_PPC_REG_13,sda)
 noops={symbols[x] for x in ['OSRegisterVersion','DSPInit','OSInitThreadQueue','OSCreateAlarm','__CARDSetDiskID','OSRegisterShutdownFunction','__OSUnlockSramEx']}
 def hook(uc,addr,size,_):
  if addr in noops or addr==0x81508bf8 or addr==symbols['__OSLockSramEx']:
   uc.reg_write(UC_PPC_REG_3, font if addr==0x81508bf8 else SRAM if addr==symbols['__OSLockSramEx'] else 0)
   uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 def call(addr,arg=0):
  u.reg_write(UC_PPC_REG_1,STACK);u.reg_write(UC_PPC_REG_3,arg);u.reg_write(UC_PPC_REG_LR,RETURN)
  u.emu_start(addr,RETURN,count=100000)
  assert u.reg_read(UC_PPC_REG_PC)==RETURN,'PPC did not return'
  n=u.reg_read(UC_PPC_REG_3);return n-2**32 if n&2**31 else n
 call(symbols['CARDInit']);expected=call(getter)
 h=bytearray(card_header(encoding) if header_data is None else header_data)
 assert len(h)==8192
 card=symbols['__CARDBlock']+slot*0x118;u.mem_write(card+8,bytes(h[0x22:0x24]));u.mem_write(card+0x80,struct.pack('>I',HEADER))
 # Derive a volatile matching test flash response from this header. Never
 # print/store flash bytes or console/card identifiers. No physical I/O.
 def signed64(v):
  v&=(1<<64)-1
  return v-(1<<64) if v&(1<<63) else v
 rand=int.from_bytes(h[12:20],'big',signed=True);flash=bytearray(12)
 for i in range(12):
  rand=signed64(rand*1103515245+12345)>>16
  flash[i]=(h[i]-(rand&255))&255
  rand=(signed64(rand*1103515245+12345)>>16)&0x7fff
 u.mem_write(SRAM+slot*12,bytes(flash))
 if corrupt:h[0x1fc]^=1
 u.mem_write(HEADER,bytes(h));before=bytes(u.mem_read(HEADER,8192))
 result=call(symbols['VerifyID'],card)
 assert bytes(u.mem_read(HEADER,8192))==before,'Card data changed'
 return dict(candidate=candidate,slot=slot,menu_patch=patched,system_font_encoding=font,card_encoding=encoding,menu_expected_encoding=expected,result=result,card_unchanged=True,corrupt_checksum=corrupt)
