"""PPC-level tests of the menu-only DVD icon lifecycle."""
import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'workspace/private/unicorn-2.1.1'))
from kwce.dvd_native_hook import compile_hook,CAVE,BANNER,BANNER_IO,ORIGINAL
class AnimatedIconVisibilityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  p=(ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes();cls.blobs,cls.sym=compile_hook(p,source=ROOT/'homebrew/kwce-disc-menu/native-v15')
 def test_icon_lifetime_and_disc_changes(self):
  from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
  from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_LR,UC_PPC_REG_PC
  u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
  for n,a in [('native',CAVE),('banner',BANNER),('bannerio',BANNER_IO),('payload',ORIGINAL+32)]:u.mem_write(a,self.blobs[n])
  put=lambda a,v:u.mem_write(a,struct.pack('>I',v));get=lambda a:int.from_bytes(u.mem_read(a,4),'big')
  scene=0x80200000;obj=0x80210000;fade=0x80220000;inanim=0x80230000;outanim=0x80240000;root=0x80520000;put(0x810890b0,0x80300000);put(scene+0x90,obj);put(scene+0x8c,fade);put(scene+0xa0,inanim);put(scene+0xa4,outanim);put(fade+4,0x41e00000)
  put(self.sym['icon_owner'],0xffffffff);put(self.sym['icon_layout'],0xffffffff);put(self.sym['cached_disc'],1)
  calls=[];available=[True];icon_ok=[True]
  def hook(uc,addr,size,_):
   if addr==self.sym['kwce_module_available']:calls.append('available');uc.reg_write(UC_PPC_REG_3,int(available[0]))
   elif addr==self.sym['kwce_load_icon']:calls.append('load');uc.reg_write(UC_PPC_REG_3,0x80500000 if icon_ok[0] else 0)
   elif addr==0x813B12D8:calls.append('create');put(obj+0x40,0x80510000);put(0x80510000+0x14,root)
   elif addr==0x813B13B8:calls.append('destroy');put(obj+0x40,0)
   elif addr==0x813AC620:calls.append('insert');put(fade+0x14,1);put(inanim+0x14,1)
   elif addr==0x813AC680:calls.append('eject');put(fade+0x14,1);put(outanim+0x14,1)
   elif addr in (0x813B1408,0x813B1464):calls.append('update_name')
   elif addr==self.sym['kwce_disk_anim_visible']:calls.append('disc_visible' if uc.reg_read(UC_PPC_REG_4) else 'disc_hidden')
   elif addr==0x813AC288:calls.append('stock')
   else:return
   uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  def run(drive):
   put(0x80300004,drive)
   for reg,val in ((UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,scene),(UC_PPC_REG_LR,0x80001000)):u.reg_write(reg,val)
   u.emu_start(self.sym['kwce_select_update'],0x80001000,count=100000)
  run(7);self.assertEqual(calls.count('create'),1);self.assertIn('insert',calls)
  self.assertEqual(u.mem_read(root+0xcf,1)[0]&1,0)
  # The fade controller can complete while the disk is still moving.
  put(fade+0x14,0)
  for _ in range(8):run(7)
  self.assertEqual(calls.count('create'),1);self.assertNotIn('disc_hidden',calls)
  self.assertEqual(u.mem_read(root+0xcf,1)[0]&1,0)
  put(inanim+0x14,0);run(7)
  self.assertEqual(calls.count('create'),1);self.assertIn('disc_hidden',calls)
  self.assertEqual(u.mem_read(root+0xcf,1)[0]&1,1)
  run(1);self.assertIn('eject',calls);self.assertNotIn('destroy',calls)
  self.assertEqual(get(self.sym['cached_disc']),0);self.assertNotEqual(get(obj+0x40),0)
  put(fade+0x14,0);run(1);self.assertNotIn('destroy',calls)
  put(outanim+0x14,0);run(1);self.assertEqual(calls.count('destroy'),1);self.assertEqual(get(obj+0x40),0)
  count=calls.count('create');run(5);run(6);self.assertEqual(calls.count('create'),count)
  available[0]=False;run(7);self.assertEqual(calls.count('create'),count)
  available[0]=True;icon_ok[0]=False;run(7);self.assertEqual(calls.count('create'),count)
  # Ejection during the insertion must not briefly expose the DVD icon.
  icon_ok[0]=True;run(7);self.assertEqual(u.mem_read(root+0xcf,1)[0]&1,0)
  run(1);self.assertEqual(u.mem_read(root+0xcf,1)[0]&1,0)
  put(fade+0x14,0);put(outanim+0x14,0);run(1)
  self.assertEqual(get(obj+0x40),0)
