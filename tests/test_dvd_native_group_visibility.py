"""Run the actual PPC layout helper with stock-hidden grouped panes."""
import struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'workspace/private/unicorn-2.1.1'))
from kwce.dvd_native_hook import compile_hook,CAVE,BANNER,ORIGINAL,BANNER_IO

class NativeGroupVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=(ROOT/'workspace/channels/dvd-player/build-v43/boot.dol').read_bytes()
        cls.blobs,cls.symbols=compile_hook(p,source=ROOT/'homebrew/kwce-disc-menu/native-v4')
    def run_helper(self,missing_gc=False):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_LR,UC_PPC_REG_PC
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000)
        for name,addr in [('native',CAVE),('banner',BANNER),('payload',ORIGINAL+32),('bannerio',BANNER_IO)]:u.mem_write(addr,self.blobs[name])
        word=lambda p,v:u.mem_write(p,struct.pack('>I',v))
        layout=0x80200000;groups=0x80201000;dvd=0x80202000;gc=0x80203000;word(layout+0x18,groups)
        panes=[]
        for index,group in enumerate((dvd,gc)):
            end=group+0x10;nodes=[0x80300000+index*0x100+i*0x10 for i in range(3)]
            word(end,nodes[0]);word(group+0xc,len(nodes))
            for i,node in enumerate(nodes):
                pane=0x80400000+index*0x1000+i*0x100;panes.append(pane)
                word(node,nodes[i+1] if i+1<len(nodes) else end);word(node+8,pane);u.mem_write(pane+0xcf,b'\x02')
        def hook(uc,addr,size,_):
            if addr!=0x814F8BF4:return
            name=bytes(uc.mem_read(uc.reg_read(UC_PPC_REG_4),6)).split(b'\0')[0]
            uc.reg_write(UC_PPC_REG_3,dvd if name==b'G_DVD' else 0 if missing_gc else gc)
            uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        for reg,value in ((UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,layout),(UC_PPC_REG_LR,0x80001000)):u.reg_write(reg,value)
        u.emu_start(self.symbols['kwce_prepare_discs'],0x80001000,count=100000)
        return u.reg_read(UC_PPC_REG_3),[bytes(u.mem_read(p+0xcf,1))[0]for p in panes]
    def test_both_groups_become_visible_without_losing_other_bits(self):
        result,flags=self.run_helper();self.assertEqual(result,0x80202000);self.assertEqual(flags,[3]*6)
    def test_missing_gc_group_does_not_touch_other_panes(self):
        result,flags=self.run_helper(True);self.assertEqual(result,0x80202000);self.assertEqual(flags,[3,3,3,2,2,2])
