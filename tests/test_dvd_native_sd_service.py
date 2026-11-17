"""Compiled PPC service + original 43K BoardSD/SDVF scheduling contracts.

FA, allocator, hashing/cache and OS primitives are modeled; original menu
state transitions execute. Paused worker contexts allow real C cancel calls
between chunks. No physical SD, graphics, BS2 or console installation.
"""
import hashlib
import struct
import unittest

from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
from kwce.dvd_disc_hook import _branch
from kwce.dvd_sd_service import compile_service, FIXTURE_BASE
from test_dvd_native_sd_ownership import OwnershipMachine

MESSAGE = 0x4b574345


class ServiceMachine(OwnershipMachine):
    SPEC = 0x80302000
    RESULT = 0x80303000

    def __init__(self, compiled):
        super().__init__(({n: b'' for n in ('native', 'banner', 'bannerio', 'payload')}, {}))
        blob, self.symbols = compiled
        self.u.mem_write(FIXTURE_BASE, blob)
        # Only the wait call inside ORIGINAL SDVFWorker::run is redirected.
        insns = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN).disasm(
            bytes(self.u.mem_read(0x8135E4D0, 0x2c0)), 0x8135E4D0)
        sites = [i.address for i in insns if i.mnemonic == 'bl' and i.op_str == '0x8135eccc']
        assert len(sites) == 1
        self.u.mem_write(sites[0], _branch(sites[0], self.symbols['kwce_sd_wait'], True))
        self.put(0x81089030, 0x80304000)
        self.payloads = [b'icon-fixture-' * 2600, b'banner-fixture-' * 1600]
        for i, data in enumerate(self.payloads):
            self.put(self.SPEC + 24*i, len(data))
            self.u.mem_write(self.SPEC + 24*i + 4, hashlib.sha1(data).digest())
        self.put(self.SD_STATE, 5)
        self.thread = 'main'
        self.locks = {}
        self.files = {}
        self.allocations = {}
        self.freed = []
        self.io = []
        self.sha = {}
        self.published = []
        self.fault = None
        self.pause = False
        self.paused = False
        self.reject_submit = False
        self.pause_idle = False
        self.next_alloc = 0x90600000
        self.extra_hook = self.service_hook

    def service_hook(self, uc, addr):
        R = self.R
        arg = lambda n: uc.reg_read(getattr(R, 'UC_PPC_REG_'+str(n)))
        ret = 0
        if addr == 0x8150A988:
            self.locks[arg(3)] = 0
        elif addr == 0x8135ED70 and self.pause_idle and arg(4) == 0:
            self.pause_idle = False; self.paused = True
            uc.emu_stop(); return True
        elif addr == 0x8150A9C0:
            self.locks[arg(3)] = self.locks.get(arg(3), 0) + 1
        elif addr == 0x8150AA9C:
            assert self.locks[arg(3)] > 0
            self.locks[arg(3)] -= 1
        elif addr == 0x81509E38:
            if not (self.reject_submit and arg(4) == MESSAGE):
                self.queue.append(arg(4)); ret = 1
        elif addr == 0x815C0DA4:
            self.check_io()
            path = bytes(uc.mem_read(arg(3), 24)).split(b'\0')[0]
            assert path in (b'A:/kwce/dvd/icon.arc', b'A:/kwce/dvd/menu.arc')
            index = int(path.endswith(b'menu.arc'))
            self.io.append(('open', index))
            if self.fault != ('open', index):
                ret = 0x80510000 + index*32
                self.files[ret] = [index, 0]
        elif addr == 0x815D0A08:
            assert arg(4) == 32 and arg(5) == 0x80304000
            if self.fault != 'alloc':
                ret = self.next_alloc; self.next_alloc += 0x50000
                self.allocations[ret] = arg(3)
        elif addr == 0x815D0B6C:
            assert arg(3) in self.allocations and arg(4) == 0x80304000
            assert arg(3) not in self.freed
            self.freed.append(arg(3))
        elif addr == 0x815C0E00:
            self.check_io()
            if self.pause:
                self.pause = False; self.paused = True; uc.emu_stop(); return True
            index, pos = self.files[arg(6)]
            assert arg(4) == 1 and arg(5) <= 16384
            count = min(arg(5), len(self.payloads[index])-pos)
            if self.fault == ('short', index): count = 0
            data = self.payloads[index][pos:pos+count]
            if data: uc.mem_write(arg(3), data)
            self.files[arg(6)][1] += count
            self.io.append(('read', index, count)); ret = count
        elif addr == 0x815C0D4C:
            self.check_io()
            index = self.files.pop(arg(3))[0]
            self.io.append(('close', index))
            ret = int(self.fault == ('close', index))
        elif addr == 0x8146CCCC:
            self.sha[arg(3)] = b''
        elif addr == 0x8146CD1C:
            self.sha[arg(3)] += bytes(uc.mem_read(arg(4), arg(5)))
        elif addr == 0x8146CDD0:
            uc.mem_write(arg(4), hashlib.sha1(self.sha.pop(arg(3))).digest())
        elif addr == 0x8150671C:
            assert arg(3) in self.allocations
            assert arg(4) == self.allocations[arg(3)]
            self.published.append(arg(3))
        else:
            return False
        uc.reg_write(R.UC_PPC_REG_3, ret)
        uc.reg_write(R.UC_PPC_REG_PC, uc.reg_read(R.UC_PPC_REG_LR))
        return True

    def check_io(self):
        assert self.thread == 'worker', 'UI thread performed file I/O'
        assert not any(self.locks.values()), 'I/O performed holding a mutex'
        assert not self.owned(), 'File I/O overlaps CDB ownership'
        assert self.get(self.WORK+0x214D0) == 1

    def call(self, name, arg=0):
        R = self.R; u = self.u
        self.thread = 'main'
        # Separate UI stack: cancellation must not corrupt the suspended worker.
        u.reg_write(R.UC_PPC_REG_1, 0x817C0000)
        u.reg_write(R.UC_PPC_REG_LR, 0x80001000)
        u.reg_write(R.UC_PPC_REG_3, arg)
        u.emu_start(self.symbols['kwce_sd_'+name], 0x80001000, count=200000)
        assert u.reg_read(R.UC_PPC_REG_PC) == 0x80001000
        assert not any(self.locks.values())
        return u.reg_read(R.UC_PPC_REG_3)

    def start(self):
        assert self.call('init', self.SPEC) == 1

    def board(self):
        self.call('board_update', self.BOARD)

    def worker(self, pause=False, pause_idle=False):
        R = self.R; u = self.u
        self.thread = 'worker'; self.pause = pause; self.paused = False; self.at_wait = False
        self.pause_idle = pause_idle
        u.reg_write(R.UC_PPC_REG_1, 0x817E0000)
        u.reg_write(R.UC_PPC_REG_LR, 0x80001000)
        u.reg_write(R.UC_PPC_REG_3, self.CDB+0x18)
        u.emu_start(0x8135E4D0, 0x80001000, count=400000)
        assert self.paused if (pause or pause_idle) else self.at_wait
        assert not any(self.locks.values())
        return u.context_save()

    def resume(self, context):
        self.thread = 'worker'; self.paused = False; self.at_wait = False
        self.u.context_restore(context)
        self.u.emu_start(self.u.reg_read(self.R.UC_PPC_REG_PC), 0x80001000, count=400000)
        assert self.at_wait and not any(self.locks.values())


class SDServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = compile_service()

    def machine(self):
        return ServiceMachine(self.compiled)

    def test_worker_preloads_then_original_board_hands_card_to_cdb(self):
        m = self.machine(); m.start(); m.board()
        self.assertEqual(m.queue, [MESSAGE]); self.assertEqual(m.io, [])
        self.assertEqual(m.call('take', m.RESULT), 0)
        for _ in range(5): m.board()
        self.assertEqual(m.queue, [MESSAGE])
        m.worker()
        self.assertEqual(m.call('status'), 3)
        self.assertEqual(len(m.published), 2)
        self.assertEqual(m.get(m.WORK+0x214D0), 0)
        m.board(); self.assertEqual(m.queue, [5])
        m.worker(); m.board()
        self.assertTrue(m.owned()); self.assertEqual(m.get(m.BOARD), 2)
        self.assertEqual(m.events, ['fa-unmount', 'fa-detach', 'cdb-mount'])
        self.assertEqual(m.call('take', m.RESULT), 1)
        self.assertEqual(m.call('take', m.RESULT), 0)
        for i, data in enumerate(m.payloads):
            self.assertEqual(bytes(m.u.mem_read(m.get(m.RESULT+4*i), len(data))), data)
        m.call('cancel'); self.assertEqual(m.call('drained'), 1)
        self.assertEqual(m.freed, [])  # Transferred resources belong to the UI.
        m.call('release', m.RESULT); m.call('release', m.RESULT)
        self.assertEqual(len(m.freed), 2)
        self.assertEqual(m.files, {})

    def test_ineligible_states_do_not_enqueue_resource_read(self):
        for state in range(6):
            for busy in (0, 1):
                for cdb in (0, 1):
                    with self.subTest(state=state, busy=busy, cdb=cdb):
                        m = self.machine(); m.start()
                        m.put(m.SD_STATE, state); m.put(m.WORK+0x214D0, busy)
                        m.u.mem_write(m.CDB+0x14, bytes([cdb])); m.board()
                        self.assertEqual(MESSAGE in m.queue, state == 5 and busy == 0 and cdb == 0)
                        self.assertEqual(m.io, [])

    def test_already_cdb_owned_is_not_reclaimed(self):
        m = self.machine(); m.transfer_to_cdb(); m.start()
        before = list(m.events)
        for _ in range(10): m.board()
        self.assertEqual(m.queue, []); self.assertEqual(m.events, before)
        self.assertEqual(m.call('status'), 0)
        m.call('cancel'); self.assertEqual(m.call('drained'), 1)

    def test_cancel_before_submit_and_while_queued(self):
        for queued in (False, True):
            with self.subTest(queued=queued):
                m = self.machine(); m.start()
                if queued: m.board()
                m.call('cancel')
                self.assertEqual(m.call('drained'), int(not queued))
                if queued: m.worker()
                self.assertEqual(m.call('status'), 5)
                self.assertEqual(m.call('drained'), 1)
                self.assertEqual(m.io, []); self.assertEqual(m.allocations, {})
                m.board(); self.assertEqual(m.queue, [5])

    def test_cancel_inflight_uses_real_c_entry_and_discards_result(self):
        m = self.machine(); m.start(); m.board()
        context = m.worker(pause=True)
        self.assertEqual(m.call('status'), 2)
        self.assertEqual(len(m.allocations), 1)
        m.call('cancel')
        self.assertEqual(m.call('drained'), 0)
        self.assertEqual(m.freed, [])  # Worker still owns its buffer/file.
        self.assertEqual(m.call('take', m.RESULT), 0)
        m.resume(context)
        self.assertEqual(m.call('drained'), 1)
        self.assertEqual(m.call('status'), 5)
        self.assertEqual(len(m.freed), 1)
        self.assertEqual(m.files, {}); self.assertEqual(m.published, [])
        self.assertEqual(len([e for e in m.io if e[0] == 'read']), 1)

    def test_cancel_ready_releases_unclaimed_batch_exactly_once(self):
        m = self.machine(); m.start(); m.board(); m.worker()
        m.call('cancel'); m.call('cancel')
        self.assertEqual(m.call('take', m.RESULT), 0)
        self.assertEqual(m.call('drained'), 1)
        self.assertEqual(len(m.freed), 2)

    def test_drain_waits_for_original_worker_idle_even_after_publication(self):
        m = self.machine(); m.start(); m.board()
        context = m.worker(pause_idle=True)
        self.assertEqual(m.call('status'), 3)
        m.call('cancel')
        self.assertEqual(m.call('drained'), 0)
        self.assertEqual(len(m.freed), 2)
        m.resume(context)
        self.assertEqual(m.call('drained'), 1)

    def test_ejection_between_chunks_closes_and_discards(self):
        m = self.machine(); m.start(); m.board()
        context = m.worker(pause=True)
        m.put(m.SD_STATE, 1)
        m.resume(context)
        self.assertEqual(m.call('status'), 4)
        self.assertEqual(m.call('take', m.RESULT), 0)
        self.assertEqual(m.files, {}); self.assertEqual(len(m.freed), 1)
        self.assertEqual(m.published, [])
        self.assertEqual(len([e for e in m.io if e[0] == 'read']), 1)

    def test_read_failures_never_publish_partial_batch_or_leak(self):
        for fault in ('alloc', ('open', 0), ('open', 1), ('short', 0),
                      ('short', 1), ('close', 1), 'hash', 'trailing'):
            with self.subTest(fault=fault):
                m = self.machine(); m.start(); m.fault = fault
                if fault == 'hash': m.payloads[1] = b'X' + m.payloads[1][1:]
                if fault == 'trailing': m.payloads[1] += b'X'
                m.board(); m.worker()
                self.assertEqual(m.call('status'), 4)
                self.assertEqual(m.call('take', m.RESULT), 0)
                self.assertEqual(m.files, {})
                self.assertEqual(set(m.freed), set(m.allocations))
                m.board(); self.assertEqual(m.queue, [5])

    def test_ejected_or_replaced_worker_fails_without_open(self):
        for kind in ('eject', 'replacement'):
            with self.subTest(kind=kind):
                m = self.machine(); m.start(); m.board()
                if kind == 'eject': m.put(m.SD_STATE, 1)
                else:
                    # Replace the captured pointer only for admission validation;
                    # original run uses a structurally valid copied worker area.
                    other = 0x90a00000
                    m.u.mem_write(other, bytes(m.u.mem_read(m.WORK, 0x21500)))
                    m.put(m.CDB+0x18, other)
                m.worker()
                self.assertEqual(m.call('status'), 4)
                self.assertEqual(m.io, [])

    def test_submit_failure_releases_busy_flag_and_preserves_stock_handoff(self):
        m = self.machine(); m.start(); m.reject_submit = True; m.board()
        self.assertEqual(m.call('status'), 4)
        self.assertEqual(m.queue, [5])  # Original BoardSD can still run.
        m.worker(); self.assertTrue(m.owned())
        self.assertEqual(m.io, []); self.assertEqual(m.get(m.WORK+0x214D0), 0)

    def test_init_bounds_single_lifetime_and_byte_reproducibility(self):
        m = self.machine()
        m.put(m.SPEC, 0); self.assertEqual(m.call('init', m.SPEC), 0)
        m.put(m.SPEC, 256*1024+1); self.assertEqual(m.call('init', m.SPEC), 0)
        m.put(m.SPEC, len(m.payloads[0])); m.start()
        self.assertEqual(m.call('init', m.SPEC), 0)
        m.call('cancel'); self.assertEqual(m.call('init', m.SPEC), 0)
        self.assertEqual(compile_service(), self.compiled)


if __name__ == '__main__':
    unittest.main()
