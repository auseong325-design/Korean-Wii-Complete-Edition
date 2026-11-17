"""Actual PPC icon loader with independent CPU/device views and mocked SDK I/O."""
import hashlib
from pathlib import Path
import struct
import unittest

from kwce.dvd_native_hook import compile_hook,CAVE,BANNER,BANNER_IO,ORIGINAL
from kwce import dvd_icon_cache_sd as candidate
from kwce.priiloader_legacy import parse

ROOT=Path(__file__).resolve().parents[1]


class IconCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.icon=(ROOT/'workspace/experiments/dvd-native-icon-v1/icon.arc').read_bytes()
        player=(ROOT/'workspace/channels/dvd-player/build-v51/boot.dol').read_bytes()
        module=(ROOT/'workspace/experiments/dvd-native-module-v10/player.ash').read_bytes()
        cls.compiled={n:compile_hook(player,module,source=ROOT/f'homebrew/kwce-disc-menu/native-v{n}')for n in(30,31)}

    def execute(self,revision,kind='good'):
        from unicorn import Uc,UC_ARCH_PPC,UC_MODE_32,UC_MODE_BIG_ENDIAN,UC_HOOK_CODE
        from unicorn.ppc_const import UC_PPC_REG_1,UC_PPC_REG_3,UC_PPC_REG_4,UC_PPC_REG_5,UC_PPC_REG_PC,UC_PPC_REG_LR
        u=Uc(UC_ARCH_PPC,UC_MODE_32|UC_MODE_BIG_ENDIAN);u.mem_map(0x80000000,0x1800000);u.mem_map(0x90000000,0x4000000)
        blobs,sym=self.compiled[revision]
        for n,a in [('native',CAVE),('banner',BANNER),('bannerio',BANNER_IO),('payload',ORIGINAL+32)]:u.mem_write(a,blobs[n])
        def put(a,v):u.mem_write(a,struct.pack('>I',v))
        image,heap=0x91000000,0x80500000
        put(0x81089084,0x80100000);put(0x80100018,0x80200000);u.mem_write(0x80201148,b'A');put(0x81089030,heap)
        content=bytearray(self.icon)
        if kind=='hash':content[-1]^=1
        if kind=='short':content=content[:-1]
        if kind=='extra':content+=b'X'
        position=0;digest=None;closed=[];freed=[];stores=[];reads=[];opens=[]
        # The model deliberately does not make CPU writes visible to GX.
        # It checks publication, not the behavior of an actual GPU or a hang.
        device_view=bytes(len(self.icon))
        def hook(uc,addr,size,_):
            nonlocal position,digest,device_view
            a=uc.reg_read(UC_PPC_REG_3);ret=0
            if addr==0x8135E38C:pass
            elif addr==0x8135E408:ret=5
            elif addr==0x815C0DA4:opens.append(1);ret=0 if kind=='missing'else 0x80300000
            elif addr==0x815D0A08:ret=0 if kind=='heap'else image
            elif addr==0x815C0E00:
                n=uc.reg_read(UC_PPC_REG_4)*uc.reg_read(UC_PPC_REG_5);reads.append(n)
                part=bytes(content[position:position+n])
                if part:uc.mem_write(a,part)
                position+=len(part);ret=len(part)
            elif addr==0x815C0D4C:closed.append(a)
            elif addr==0x815D0B6C:freed.append(a)
            elif addr==0x8146CCCC:pass
            elif addr==0x8146CD1C:digest=hashlib.sha1(bytes(uc.mem_read(uc.reg_read(UC_PPC_REG_4),uc.reg_read(UC_PPC_REG_5)))).digest()
            elif addr==0x8146CDD0:uc.mem_write(uc.reg_read(UC_PPC_REG_4),digest)
            elif addr==0x8150671C:
                length=uc.reg_read(UC_PPC_REG_4)
                self.assertEqual((a,length),(image,len(self.icon)))
                self.assertEqual(a%32,0);self.assertEqual(length%32,0)
                self.assertEqual(len(closed),1);self.assertEqual(digest,hashlib.sha1(self.icon).digest())
                self.assertEqual(int.from_bytes(uc.mem_read(sym['icon_data'],4),'big'),0)
                stores.append((a,length));device_view=bytes(uc.mem_read(a,length))
            else:return
            uc.reg_write(UC_PPC_REG_3,ret);uc.reg_write(UC_PPC_REG_PC,uc.reg_read(UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE,hook)
        def run():
            u.reg_write(UC_PPC_REG_1,0x807ff000);u.reg_write(UC_PPC_REG_LR,0x80001000)
            u.emu_start(sym['kwce_load_icon'],0x80001000,count=1000000)
            self.assertEqual(u.reg_read(UC_PPC_REG_1),0x807ff000)
            return u.reg_read(UC_PPC_REG_3)
        result=run()
        if kind=='good':
            self.assertEqual(result,image);self.assertEqual(bytes(u.mem_read(image,len(self.icon))),self.icon)
            self.assertEqual(reads,[len(self.icon),1]);before=(len(reads),len(stores),len(opens))
            self.assertEqual(run(),image);self.assertEqual((len(reads),len(stores),len(opens)),before)
        else:
            self.assertEqual(result,0);self.assertFalse(stores)
            self.assertEqual(freed,[]if kind in('missing','heap')else[image])
        return stores,device_view

    def test_old_loader_leaves_device_view_stale(self):
        stores,visible=self.execute(30);self.assertFalse(stores);self.assertNotEqual(visible,self.icon)

    def test_new_loader_publishes_validated_bytes_once_before_exposing_pointer(self):
        stores,visible=self.execute(31);self.assertEqual(len(stores),1);self.assertEqual(visible,self.icon)

    def test_failed_validation_or_allocation_never_publishes(self):
        for kind in('missing','heap','short','extra','hash'):
            with self.subTest(kind=kind):self.execute(31,kind)

    def test_sd_upgrade_preserves_gc_and_other_blocks(self):
        package=ROOT/'workspace/hardware/kwce-dvd-icon-cache-v1';_,files=candidate.sd_files(package);self.assertEqual(len(files),5)
        for rel in candidate.TARGETS:
            old=(package/'expected'/rel).read_bytes();new=(package/rel).read_bytes()
            self.assertEqual([e['name']for e in parse(old)],[e['name']for e in parse(new)])
            for a,b in zip(old.split(b'['),new.split(b'[')):
                if not a.startswith(b'KWCE DVD: disc channel DVD player]'):self.assertEqual(a,b)
        wrong=(ROOT/'workspace/hardware/kwce-dvd-deferred-prefetch-v1/apps/Priiloader/hacks_hash.ini').read_bytes()
        with self.assertRaisesRegex(ValueError,'native59'):candidate.upgrade_definition(wrong)


if __name__=='__main__':unittest.main()
