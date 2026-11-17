"""Source37 integrated menu: actual patched branches and original SDK worker.

Device I/O, OS scheduling, allocation and SHA/cache calls are modeled. UI
access must not do I/O, settings cancellation preserves original shutdown,
and all three immutable resources are validated before publication.
"""
import hashlib
from pathlib import Path
import unittest

from kwce.dvd_integrated_hook import patch, REGIONS, DEBUG_GUARDS, sites
from kwce.gc_native import patch_gc_native
from kwce.ppc_patch import sections, to_file
from test_dvd_native_sd_ownership import OwnershipMachine
from test_dvd_native_sd_service import ServiceMachine, MESSAGE
from test_dvd_native_settings_boundary import SettingsMachine

ROOT=Path(__file__).resolve().parents[1]


def inputs(player=51,module=10):
    import json
    folder=ROOT/f'workspace/experiments/dvd-native-module-v{module}'
    record=json.loads((folder/'manifest.json').read_text())
    # Forwarder modules keep only the small loader resident; it is the payload.
    payload=(folder/'forwarder.dol' if record.get('kind')=='forwarder' else
             ROOT/f'workspace/channels/dvd-player/build-v{player}/boot.dol')
    return [Path(ROOT/p).read_bytes() for p in (
        payload,
        f'workspace/experiments/dvd-native-module-v{module}/player.ash',
        'workspace/experiments/dvd-native-banner-v2/menu.arc',
        'workspace/experiments/dvd-native-icon-v1/icon.arc')]


class IntegratedMachine(SettingsMachine):
    def __init__(self, built, payloads):
        # Reuse fixture helpers but install the entire real patched DOL.
        # None of service-v1's code or simulated-only callback patches is used.
        OwnershipMachine.__init__(self,({n:b'' for n in ('native','banner','bannerio','payload')},{}))
        menu,self.record=built
        for _,off,addr,size in sections(menu):self.u.mem_write(addr,menu[off:off+size])
        self.symbols=self.record['symbols'];self.payloads=list(payloads)
        self.put(0x81089014,0x80305000);self.put(0x81089030,0x80304000)
        self.put(0x80304010,0x80306000);self.put(0x8030601c,0x94000000)
        self.put(self.SCENE+0x60,13);self.put(0x8108906c,0x8030b000)
        self.put(0x810890b0,self.BS2);self.put(self.BS2+4,7)
        self.u.mem_write(self.BS2+0x0c,b'\1')
        self.thread='main';self.locks={};self.files={};self.allocations={}
        self.freed=[];self.io=[];self.sha={};self.published=[];self.fault=None
        self.pause=False;self.paused=False;self.at_wait=False;self.pause_idle=False
        self.reject_submit=False;self.next_alloc=0x90600000
        self.free_bytes=0x1400000;self.start_count=0
        self.device_states=[56];self.ticks=self.retraces=self.abort_calls=0
        self.retrace_limit=8;self.boundary=None
        self.extra_hook=self.service_hook

    def service_hook(self,uc,addr):
        R=self.R;arg=lambda n:uc.reg_read(getattr(R,'UC_PPC_REG_'+str(n)));ret=0
        if addr==0x8133F624:
            # The original factory's physical thread creation is mocked. All
            # service entry/call sites and worker run/BoardSD code are actual.
            self.start_count+=1
            assert not self.queue
            self.put(self.CDB+0x18,self.WORK)
            self.put(self.WORK+0x214D0,0);self.put(self.SD_STATE,0)
        elif addr==0x815D03BC:ret=self.free_bytes
        elif addr==0x815D0A08:
            assert arg(4)==32
            if arg(5)==0x80305000:
                if self.fault!='context-alloc':ret=0x90300000
            else:
                assert arg(5)==0x80304000
                if self.fault!='alloc':ret=0x90600000
            if ret:
                assert ret not in self.allocations or ret in self.freed
                self.allocations[ret]=arg(3)
                if ret in self.freed:self.freed.remove(ret)
        elif addr==0x815C0DA4:
            self.check_io()
            path=bytes(uc.mem_read(arg(3),24)).split(b'\0')[0]
            names=[b'A:/kwce/dvd/boot.ash',b'A:/kwce/dvd/menu.arc',b'A:/kwce/dvd/icon.arc']
            assert path in names;index=names.index(path);self.io.append(('open',index))
            if self.fault!=('open',index):
                ret=0x80510000+index*32;self.files[ret]=[index,0]
        elif addr==0x815066EC:
            assert arg(3) in self.allocations and arg(4)==self.record['bundle_size']
            self.published.append(arg(3))
        elif addr==0x815067A4:
            assert self.published and arg(3)==0x90600000+self.record['offsets'][1]-65536
        else:return super().service_hook(uc,addr)
        uc.reg_write(R.UC_PPC_REG_3,ret)
        uc.reg_write(R.UC_PPC_REG_PC,uc.reg_read(R.UC_PPC_REG_LR));return True

    def invoke(self,name,arg=0):
        self.thread='main';u=self.u;R=self.R
        u.reg_write(R.UC_PPC_REG_1,0x817C0000)
        u.reg_write(R.UC_PPC_REG_LR,0x80001000);u.reg_write(R.UC_PPC_REG_3,arg)
        u.emu_start(self.symbols[name],0x80001000,count=500000)
        assert u.reg_read(R.UC_PPC_REG_PC)==0x80001000
        assert not any(self.locks.values())
        return u.reg_read(R.UC_PPC_REG_3)

    def start(self):
        self.invoke('kwce_start_sd',self.CDB)
        self.put(self.SD_STATE,5)

    def board(self):self.invoke('kwce_board_update',self.BOARD)

    def status(self):
        p=self.get(self.symbols['service'])
        return self.get(p+40) if p not in (0,0xffffffff) else None

    def resource(self,index):return self.invoke('kwce_resource',index)

    def cancel_scene(self):self.original(0x8138E4A0)


class IntegratedTests(unittest.TestCase):
    player = 51
    module = 10
    @classmethod
    def setUpClass(cls):
        cls.original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        cls.assets=inputs(cls.player,cls.module)
        cls.base=patch_gc_native(cls.original,japanese_cards=True,japanese_comments=True)[0]
        cls.built=patch(cls.base,*cls.assets)

    def machine(self):return IntegratedMachine(self.built,self.assets[1:])

    def test_three_assets_read_only_in_worker_then_normal_cdb_handoff(self):
        m=self.machine();m.start();m.board()
        self.assertEqual(m.queue,[MESSAGE]);self.assertEqual(m.io,[])
        self.assertEqual(m.invoke('kwce_module_available'),0)
        self.assertEqual(m.invoke('kwce_load_icon'),0)
        m.worker();self.assertEqual(m.status(),3)
        self.assertEqual([x[1] for x in m.io if x[0]=='open'],[0,1,2])
        self.assertEqual(m.published,[0x90600000]);self.assertEqual(m.files,{})
        for i,data in enumerate(m.payloads):
            ptr=m.resource(i)
            self.assertEqual(bytes(m.u.mem_read(ptr,len(data))),data)
        before=list(m.io)
        for _ in range(20):
            self.assertEqual(m.invoke('kwce_module_available'),1)
            self.assertEqual(m.invoke('kwce_load_icon'),m.resource(2))
        self.assertEqual(m.io,before)
        m.board();self.assertEqual(m.queue,[5]);m.worker();m.board()
        self.assertTrue(m.owned())
        self.assertEqual(m.events,['fa-unmount','fa-detach','cdb-mount'])

    def test_actual_board_entry_cancels_inflight_before_original_shutdown(self):
        m=self.machine();m.start();m.board();context=m.worker(pause=True)
        self.assertEqual(m.status(),2);m.cancel_scene()
        self.assertEqual(m.get(m.SCENE+0x60),13)
        self.assertEqual(m.freed,[]);m.resume(context)
        self.assertEqual(m.status(),4);self.assertEqual(m.resource(0),0)
        self.assertEqual(m.freed,[0x90600000]);self.assertEqual(m.files,{})
        m.cancel_scene();self.assertEqual(m.queue,[1])
        context=m.original(0x8138E94C)
        self.assertEqual(m.boundary,'worker-wait')
        m.terminate_worker();m.finish_destroy(context)
        self.assertEqual(m.get(m.CDB+0x18),0)

    def test_ready_bundle_freed_after_drain_then_reloaded_on_board_recreation(self):
        m=self.machine();m.start();m.board();m.worker();m.board();m.worker();m.board()
        pointers=[m.resource(i) for i in range(3)]
        for _ in range(4):
            m.put(m.SCENE+0x60,13);m.cancel_scene()
            context=m.original(0x8138E94C);m.terminate_worker();m.finish_destroy(context)
            self.assertEqual(m.resource(0),0);self.assertIn(0x90600000,m.freed)
            m.original(0x813F0044);self.assertEqual(m.boundary,'settings-resources')
            m.start();m.put(m.BOARD,0);m.board()
            self.assertEqual(m.queue,[MESSAGE]);m.worker();m.board();m.worker();m.board()
            self.assertEqual([m.resource(i) for i in range(3)],pointers)
        self.assertEqual(len([x for x in m.io if x[0]=='open']),15)
        self.assertEqual(m.freed,[])
        self.assertEqual(len(m.allocations),2)

    def test_failed_batch_retries_only_after_new_board_worker(self):
        m=self.machine();m.start();m.fault=('open',2);m.board();m.worker()
        self.assertEqual(m.status(),4);self.assertEqual(m.resource(0),0)
        m.board();self.assertEqual(m.queue,[5]);m.worker();m.board()
        m.cancel_scene();ctx=m.original(0x8138E94C);m.terminate_worker();m.finish_destroy(ctx)
        m.fault=None;m.start();m.put(m.BOARD,0);m.board();m.worker()
        self.assertEqual(m.status(),3);self.assertEqual(m.resource(2),0x90600000+m.record['offsets'][2])

    def test_corruption_short_files_missing_close_and_allocation_fail_closed(self):
        for fault in ('alloc',('open',0),('open',1),('open',2),('short',0),('short',2),('close',1),'hash','tail'):
            with self.subTest(fault=fault):
                m=self.machine();m.start();m.fault=fault
                if fault=='hash':m.payloads[0]=b'X'+m.payloads[0][1:]
                if fault=='tail':m.payloads[2]+=b'X'
                m.board();m.worker()
                self.assertEqual(m.status(),4);self.assertEqual(m.resource(0),0)
                self.assertEqual(m.files,{});self.assertEqual(m.published,[])
                self.assertEqual(m.freed,[] if fault=='alloc' else [0x90600000])
                m.board();self.assertEqual(m.queue,[5])

    def test_memory_headroom_and_context_allocation_preserve_stock_behavior(self):
        m=self.machine();m.start();m.free_bytes=m.record['bundle_size']+0x100000-1
        m.board();m.worker();self.assertEqual(m.status(),4)
        self.assertEqual(m.io,[]);self.assertEqual(len(m.allocations),1)
        m=self.machine();m.fault='context-alloc';m.start();m.board()
        self.assertEqual(m.queue,[5]);self.assertEqual(m.resource(0),0)

    def test_cancel_queued_and_submission_failure_do_not_strand_worker(self):
        m=self.machine();m.start();m.board();m.cancel_scene();m.worker()
        self.assertEqual(m.status(),4);self.assertEqual(m.io,[])
        m.cancel_scene();self.assertEqual(m.queue,[1])
        m=self.machine();m.start();m.reject_submit=True;m.board()
        self.assertEqual(m.status(),4);self.assertEqual(m.queue,[5])

    def test_integrated_archive_borrow_and_sdk_owned_banner_copies(self):
        from test_dvd_native_sdk_lifecycle import SDKMachine
        from kwce.priiloader_hacks import _runs
        m=SDKMachine();data,meta=self.built
        for lo,hi in _runs(self.original,data):
            # Convert file position back to guest VA, without overwriting the
            # SDK globals initialized by SDKMachine.
            for _,off,addr,size in sections(data):
                if off<=lo<hi<=off+size:m.u.mem_write(addr+lo-off,data[lo:hi]);break
            else:self.fail('Patch outside section')
        control,image=0x90300000,0x90400000
        m.put(meta['symbols']['service'],control);m.put(control+40,3);m.put(control+36,image)
        m.put(0x81089030,m.root)
        for i,blob in enumerate(self.assets[1:]):m.u.mem_write(image+meta['offsets'][i],blob)
        before=m.run(0x815D03BC,m.root,32)
        relocated=None
        for _ in range(4):
            borrowed=m.run(meta['symbols']['kwce_load_icon'])
            self.assertEqual(borrowed,image+meta['offsets'][2])
            m.run(0x813B12D8,m.obj,borrowed);self.assertTrue(m.get(m.obj+0x40))
            current=bytes(m.u.mem_read(borrowed,len(self.assets[3])))
            if relocated is not None:self.assertEqual(current,relocated)
            relocated=current
            m.run(0x813B13B8,m.obj)
            layout=m.run(meta['symbols']['kwce_load_banner']);self.assertTrue(layout)
            file=m.get(layout+4);owned=m.get(file+0xa0)
            self.assertNotEqual(owned,image+meta['offsets'][1])
            self.assertEqual(bytes(m.u.mem_read(owned,len(self.assets[2]))),self.assets[2])
            m.run(0x8133BB18,layout,1)
            self.assertEqual(m.run(0x815D03BC,m.root,32),before)
        # SDK archive binding relocates internal icon pointers in-place once.
        # The buffer must remain alive, but its bytes are not immutable.
        self.assertNotEqual(relocated,self.assets[3])
        self.assertEqual(bytes(m.u.mem_read(image,len(self.assets[1]))),self.assets[1])
        self.assertEqual(bytes(m.u.mem_read(image+meta['offsets'][1],len(self.assets[2]))),self.assets[2])

    def test_cave_external_references_are_guarded_vtables_or_private_jump_tables(self):
        import struct
        lo,hi=0x813bd48c,0x813bf6a8
        tables=[(0x81624bc0,0x81624bf4),(0x81624e3c,0x81624f88),(0x81625114,0x81625260)]
        guarded={*DEBUG_GUARDS,0x813bd5c8,0x813bd5c4,0x813bdd80,0x813bdd88,0x813bdd90}
        for index,off,addr,size in sections(self.original):
            for k in range(0,size-3,4):
                pc=addr+k;v=struct.unpack_from('>I',self.original,off+k)[0]
                if lo<=pc<hi:continue
                if index<7 and v>>26==18:
                    delta=v&0x3fffffc
                    if delta&0x2000000:delta-=0x4000000
                    target=(delta if v&2 else pc+delta)&0xffffffff
                    self.assertFalse(lo<=target<hi)
                if lo<=v<hi:
                    self.assertTrue(v in guarded or any(a<=pc<b for a,b in tables))
        # Original source Manager::destroyScene recursively destroys children
        # before Board, which owns the cached archives. Shared base fadein stays.
        for a in (0x813bdd80,0x813bdd88,0x813bdd90):
            at=to_file(self.original,a)
            self.assertEqual(self.built[0][at:at+8],self.original[at:at+8])

    def test_gc_preserved_attach_original_and_all_mutations_in_reviewed_ranges(self):
        data,meta=self.built
        ranges=[(to_file(data,0x813BD48C),to_file(data,0x813BF6A8-4)+4)]
        ranges +=[(to_file(data,a),to_file(data,a)+4) for a in sites(self.original)]
        changes=[i for i,(a,b) in enumerate(zip(self.base,data)) if a!=b]
        self.assertTrue(changes)
        self.assertTrue(all(any(lo<=i<hi for lo,hi in ranges) for i in changes))
        at=to_file(data,0x8135E820);self.assertEqual(data[at:at+4],self.original[at:at+4])
        for address,guard in DEBUG_GUARDS.items():
            at=to_file(data,address);self.assertEqual(data[at:at+len(guard)],guard)


class IntegratedTracePlayerTests(IntegratedTests):
    player = 53
    module = 12


class IntegratedFailureReturnTests(IntegratedTests):
    player = 54
    module = 13


class IntegratedDvdVideoPermissionTests(IntegratedTests):
    player = 55
    module = 14


class IntegratedExactReadTests(IntegratedTests):
    player = 56
    module = 15


class IntegratedFirstReadTests(IntegratedTests):
    player = 57
    module = 16


class IntegratedDvdDisableClearTests(IntegratedTests):
    player = 58
    module = 17


class IntegratedForwarderTests(IntegratedTests):
    player = 64
    module = 22


if __name__=='__main__':unittest.main()
