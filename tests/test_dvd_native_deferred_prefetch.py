"""Actual PPC: thumbnails must not preload the player; explicit requests still validate it."""
import hashlib
import struct
from pathlib import Path
import unittest

from kwce.dvd_native_hook import compile_hook, CAVE, BANNER, BANNER_IO, ORIGINAL

ROOT = Path(__file__).resolve().parents[1]


class DeferredPrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player = (ROOT/'workspace/channels/dvd-player/build-v51/boot.dol').read_bytes()
        cls.module = (ROOT/'workspace/experiments/dvd-native-module-v10/player.ash').read_bytes()
        cls.compiled = {n: compile_hook(cls.player, cls.module,
                           source=ROOT/f'homebrew/kwce-disc-menu/native-v{n}') for n in (29,30)}

    def machine(self, revision):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
        from unicorn.ppc_const import UC_PPC_REG_1, UC_PPC_REG_3, UC_PPC_REG_LR
        u = Uc(UC_ARCH_PPC, UC_MODE_32|UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x1800000); u.mem_map(0x90000000, 0x4000000)
        blobs, sym = self.compiled[revision]
        for name, address in [('native',CAVE),('banner',BANNER),('bannerio',BANNER_IO),('payload',ORIGINAL+32)]:
            u.mem_write(address, blobs[name])
        def put(address,value): u.mem_write(address,struct.pack('>I',value))
        def run(name,arg):
            for r,v in [(UC_PPC_REG_1,0x807ff000),(UC_PPC_REG_3,arg),(UC_PPC_REG_LR,0x80001000)]:
                u.reg_write(r,v)
            u.emu_start(sym[name],0x80001000,count=1000000)
            self.assertEqual(u.reg_read(UC_PPC_REG_1),0x807ff000)
            return u.reg_read(UC_PPC_REG_3)
        return u, sym, put, run

    def test_thumbnail_skips_player_gate_but_keeps_icon_verification_path(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_3,UC_PPC_REG_PC,UC_PPC_REG_LR
        for revision in (29,30):
            for icon_ok in (False, True):
                u,sym,put,run = self.machine(revision)
                scene,obj=0x80200000,0x80210000
                put(0x810890b0,0x80300000);put(0x80300004,7)
                put(scene+0x90,obj);put(scene+0xa0,0x80220000);put(scene+0xa4,0x80230000)
                calls=[]
                def hook(uc,addr,size,_):
                    if addr==sym['kwce_module_available']:calls.append('player');uc.reg_write(UC_PPC_REG_3,1)
                    elif addr==sym['kwce_load_icon']:calls.append('icon');uc.reg_write(UC_PPC_REG_3,0x80500000 if icon_ok else 0)
                    elif addr==0x813B12D8:calls.append('create');put(obj+0x40,0x80510000)
                    elif addr==sym['kwce_disk_anim_visible']:calls.append('visible')
                    elif addr==0x813AC620:calls.append('insert')
                    elif addr==0x813AC288:calls.append('stock')
                    else:return
                    uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
                u.hook_add(UC_HOOK_CODE,hook)
                run('kwce_select_update',scene)
                self.assertEqual(calls.count('player'),1 if revision==29 else 0)
                self.assertEqual(calls.count('icon'),1)
                self.assertEqual(calls.count('create'),int(icon_ok))
                self.assertEqual(calls.count('stock'),int(not icon_ok))

    def test_explicit_module_request_still_checks_full_bytes_hash_and_reuses(self):
        from unicorn import UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_PC,UC_PPC_REG_LR
        for corrupt in (False, True):
            u,sym,put,run=self.machine(30)
            content=bytearray(self.module)
            if corrupt: content[-1]^=1
            image,heap=0x91000000,0x80500000
            put(0x81089084,0x80100000);put(0x80100018,0x80200000)
            u.mem_write(0x80201148,b'A');put(0x81089030,heap)
            put(heap+0x10,heap+0x100);put(heap+0x100+0x1c,0x93000000)
            position=0;digest=None;reads=[];freed=[];banners=[]
            def hook(uc,addr,size,_):
                nonlocal position,digest
                a=uc.reg_read(UC_PPC_REG_3);ret=0
                if addr==0x8135E38C:pass
                elif addr==0x8135E408:ret=5
                elif addr==0x815C0DA4:ret=0x80300000
                elif addr==0x815D0A08:ret=image
                elif addr==0x815C0E00:
                    requested=uc.reg_read(UC_PPC_REG_4)*uc.reg_read(UC_PPC_REG_5)
                    part=bytes(content[position:position+requested]);reads.append(requested)
                    if part:uc.mem_write(a,part)
                    position+=len(part);ret=len(part)
                elif addr==0x815C0D4C:pass
                elif addr==0x815D0B6C:freed.append(a)
                elif addr==0x8146CCCC:pass
                elif addr==0x8146CD1C:
                    digest=hashlib.sha1(bytes(uc.mem_read(uc.reg_read(UC_PPC_REG_4),uc.reg_read(UC_PPC_REG_5)))).digest()
                elif addr==0x8146CDD0:uc.mem_write(uc.reg_read(UC_PPC_REG_4),digest)
                elif addr in (0x815066EC,0x815067A4):pass
                elif addr==sym['kwce_prefetch_banner']:banners.append(1);ret=1
                else:return
                uc.reg_write(UC_PPC_REG_3,ret);uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
            u.hook_add(UC_HOOK_CODE,hook)
            self.assertEqual(run('kwce_module_available',0),int(not corrupt))
            self.assertEqual(reads,[len(self.module),1])
            self.assertEqual(freed,[image]if corrupt else[])
            self.assertEqual(banners,[]if corrupt else[1])
            if not corrupt:
                self.assertEqual(run('kwce_module_available',0),1)
                self.assertEqual(reads,[len(self.module),1])
                self.assertEqual(bytes(u.mem_read(image,len(self.module))),self.module)


if __name__=='__main__':unittest.main()
