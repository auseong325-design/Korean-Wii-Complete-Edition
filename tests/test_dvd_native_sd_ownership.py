"""Execute original 43K BoardSD/SDVF state transitions with the injected loader.

Only OS scheduling/mutexes and physical FA/CDB operations are mocked. This
proves an ownership contract violation, not the physical console's hang.
No real SD or console data is used.
"""
from pathlib import Path
import struct
import unittest
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
from kwce.ppc_patch import sections, to_file
from kwce.dvd_native_hook import compile_hook, CAVE, BANNER, BANNER_IO, ORIGINAL

ROOT = Path(__file__).resolve().parents[1]


class OwnershipMachine:
    CDB = 0x80300000
    WORK = 0x90400000
    BOARD = 0x80301000
    SD_STATE = 0x8166CD10

    def __init__(self, compiled):
        from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
        from unicorn import ppc_const as R
        self.R = R
        self.u = u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN)
        u.mem_map(0x80000000, 0x1800000)
        u.mem_map(0x90000000, 0x4000000)
        dol = (ROOT / 'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        for _, off, addr, size in sections(dol):
            u.mem_write(addr, dol[off:off+size])
        blobs, self.sym = compiled
        for name, addr in [('native', CAVE), ('banner', BANNER), ('bannerio', BANNER_IO), ('payload', ORIGINAL+32)]:
            u.mem_write(addr, blobs[name])
        # Recover r13 from the exact pinned get_sd_state load, not a guessed ABI.
        at = to_file(dol, 0x8135E408)
        ins = next(Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN).disasm(dol[at:at+4], 0x8135E408))
        assert ins.mnemonic == 'lwz' and ins.op_str.endswith('(r13)')
        displacement = int(ins.op_str.split(', ')[1].split('(')[0], 0)
        u.reg_write(R.UC_PPC_REG_13, self.SD_STATE-displacement)
        self.put(0x81089084, self.CDB)
        self.put(self.CDB+0x18, self.WORK)
        self.put(self.WORK+0x21160+0x308, self.WORK+0x1160)
        self.put(self.WORK+0x1160, 0xDEADBABE)
        u.mem_write(self.WORK+0x1148, b'A')
        self.queue = []
        self.events = []
        self.at_wait = False

        def hook(uc, addr, size, _):
            if getattr(self, 'extra_hook', None) and self.extra_hook(uc, addr):
                return
            arg = lambda n: uc.reg_read(getattr(R, 'UC_PPC_REG_'+str(n)))
            ret = 0
            if addr in (0x8150A9C0, 0x8150AA9C, 0x81507458):
                pass  # OS mutex / diagnostic output
            elif addr == 0x81509E38:
                self.queue.append(arg(4)); ret = 1
            elif addr == 0x8135ECCC:  # scheduler: one work message at a time
                if not self.queue:
                    self.at_wait = True; uc.emu_stop(); return
                ret = self.queue.pop(0)
            elif addr == 0x815C11A0:
                self.events.append('fa-unmount')
            elif addr == 0x815C0C64:
                self.events.append('fa-detach')
            elif addr == 0x8133F63C:
                self.events.append('cdb-mount')
                uc.mem_write(self.CDB+0x14, b'\1'); self.put(self.CDB+0x10, 0); ret = 1
            elif addr == 0x8133F6AC:
                self.events.append('cdb-unmount'); uc.mem_write(self.CDB+0x14, b'\0'); ret = 1
            elif addr == 0x814625C8:
                ret = self.owned()
            elif addr in (0x815C0EE8, 0x815C1140, 0x815C0FE8):
                pass
            elif addr == 0x815C09E8:
                self.events.append('fa-attach-while-cdb-owned' if self.owned() else 'fa-attach')
            elif addr == 0x8135E97C:
                self.events.append('fa-mount')
            elif addr == 0x815C0DA4:
                self.events.append('fa-open-while-cdb-owned' if self.owned() else 'fa-open'); ret = 0x80500000
            elif addr == 0x815074E8:
                raise AssertionError('SDK halt in ownership fixture')
            else:
                return
            uc.reg_write(R.UC_PPC_REG_3, ret)
            uc.reg_write(R.UC_PPC_REG_PC, uc.reg_read(R.UC_PPC_REG_LR))
        u.hook_add(UC_HOOK_CODE, hook)

    def put(self, addr, value):
        self.u.mem_write(addr, struct.pack('>I', value))

    def get(self, addr):
        return int.from_bytes(self.u.mem_read(addr, 4), 'big')

    def owned(self):
        return bool(self.u.mem_read(self.CDB+0x14, 1)[0])

    def run(self, addr, arg=0, worker=False):
        R = self.R; u = self.u; self.at_wait = False
        u.reg_write(R.UC_PPC_REG_1, 0x817E0000)
        u.reg_write(R.UC_PPC_REG_LR, 0x80001000)
        u.reg_write(R.UC_PPC_REG_3, arg)
        u.emu_start(addr, 0x80001000, count=100000)
        assert self.at_wait if worker else u.reg_read(R.UC_PPC_REG_PC) == 0x80001000
        return u.reg_read(R.UC_PPC_REG_3)

    def transfer_to_cdb(self):
        # The real BoardSD schedules the real worker to transfer FA -> CDB.
        self.put(self.SD_STATE, 5)
        self.run(0x81395338, self.BOARD)
        assert self.queue == [5]
        self.run(0x8135E4D0, self.CDB+0x18, worker=True)
        self.run(0x81395338, self.BOARD)
        assert self.owned() and self.get(self.BOARD) == 2
        assert self.get(self.SD_STATE) == 0 and self.get(self.WORK+0x214D0) == 0


class SDOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        player = (ROOT/'workspace/channels/dvd-player/build-v51/boot.dol').read_bytes()
        module = (ROOT/'workspace/experiments/dvd-native-module-v10/player.ash').read_bytes()
        cls.compiled = {n: compile_hook(player, module, source=ROOT/f'homebrew/kwce-disc-menu/native-v{n}') for n in (31, 32, 33)}

    def test_legacy_loader_remounts_sd_already_owned_by_cdb(self):
        for revision in (31, 32):
            with self.subTest(revision=revision):
                m = OwnershipMachine(self.compiled[revision]); m.transfer_to_cdb()
                self.assertEqual(m.events, ['fa-unmount', 'fa-detach', 'cdb-mount'])
                self.assertEqual(m.run(m.sym['kwce_open'], 2), 0)
                self.assertEqual(m.queue, [2])
                m.run(0x8135E4D0, m.CDB+0x18, worker=True)
                self.assertIn('fa-attach-while-cdb-owned', m.events)
                # If the physical FA accepts that attach, the loader opens it.
                self.assertEqual(m.run(m.sym['kwce_open'], 2), 0x80500000)
                self.assertIn('fa-open-while-cdb-owned', m.events)


    def test_passive_reader_respects_original_cdb_transfer(self):
        m = OwnershipMachine(self.compiled[33]); m.transfer_to_cdb()
        before = list(m.events)
        for selector in (0, 1, 2):
            for _ in range(20):
                self.assertEqual(m.run(m.sym['kwce_open'], selector), 0)
        self.assertEqual(m.events, before)
        self.assertEqual(m.queue, [])
        self.assertTrue(m.owned())
        self.assertEqual(m.get(m.BOARD), 2)

    def test_passive_reader_never_initiates_mount_or_uses_busy_worker(self):
        for sd_state in range(6):
            for busy in (False, True):
                for cdb in (False, True):
                    with self.subTest(sd_state=sd_state, busy=busy, cdb=cdb):
                        m = OwnershipMachine(self.compiled[33])
                        m.put(m.SD_STATE, sd_state)
                        m.put(m.WORK+0x214D0, int(busy))
                        m.u.mem_write(m.CDB+0x14, bytes([cdb]))
                        expected = sd_state == 5 and not busy and not cdb
                        for selector in (0, 1, 2):
                            result = m.run(m.sym['kwce_open'], selector)
                            self.assertEqual(result, 0x80500000 if expected else 0)
                        self.assertEqual(m.events, ['fa-open']*3 if expected else [])
                        self.assertEqual(m.queue, [])

    def test_terminated_worker_and_missing_cdb_fail_closed(self):
        m = OwnershipMachine(self.compiled[33]); m.put(m.CDB+0x18, 0)
        self.assertEqual(m.run(m.sym['kwce_open'], 2), 0)
        m.put(0x81089084, 0)
        self.assertEqual(m.run(m.sym['kwce_open'], 2), 0)
        self.assertEqual(m.queue, []); self.assertEqual(m.events, [])

    def test_local_build_restores_global_sd_attach_call(self):
        original = (ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        old = (ROOT/'workspace/experiments/dvd-native-hook-v60/menu.dol').read_bytes()
        new = (ROOT/'workspace/experiments/dvd-native-hook-v62/menu.dol').read_bytes()
        at = to_file(original, 0x8135E820)
        self.assertNotEqual(original[at:at+4], old[at:at+4])
        self.assertEqual(original[at:at+4], new[at:at+4])
        import json
        meta = json.loads((ROOT/'workspace/experiments/dvd-native-hook-v62/manifest.json').read_text())
        self.assertTrue(meta['local_only']); self.assertTrue(meta['sd_passive_reader'])
        self.assertFalse(meta['sd_attach_hook'])
        from kwce.dvd_native_hardware import entry
        with self.assertRaisesRegex(ValueError, 'Local-only'):
            entry(b'', {'hook': 'dvd-native-hook-v62'})
        import subprocess, sys
        result = subprocess.run([sys.executable, 'scripts/build_dvd_native_hook.py',
            '--revision', '62', '--source-revision', '33', '--install'],
            cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Local-only', result.stderr)



if __name__ == '__main__':
    unittest.main()
