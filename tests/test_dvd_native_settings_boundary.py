"""Original 43K settings/Board termination with the local SD service.

The actual Board calc/destroy, SDVF run, Setting prepare wait loop, and BS2
Manager abort/update/splash/exec routines execute. Device BS2Tick, OS,
layout and background receive callbacks are modeled. Stop before settings
identity/resource/browser initialization. These are boundary tests, not a
claim of a rendered settings screen or a hardware hang reproduction.
"""
import unittest

from kwce.dvd_sd_service import compile_service
from test_dvd_native_sd_service import ServiceMachine, MESSAGE


class SettingsMachine(ServiceMachine):
    SCENE = 0x80308000
    BS2 = 0x8030A000

    def __init__(self, compiled):
        super().__init__(compiled)
        self.put(self.SCENE+0x60, 13)  # Board::STATE_TO_SETTINGS
        self.put(0x8108906c, 0x8030b000)  # Synthetic scene manager/root id.
        self.put(0x810890b0, self.BS2)
        self.put(self.BS2+4, 7)  # IPL_STATE_BAD_DISK
        self.u.mem_write(self.BS2+0x0c, b'\1')  # BS2 updates enabled
        self.device_states = [56]  # BS2_STT_WRONG_DISK
        self.ticks = self.retraces = self.abort_calls = 0
        self.retrace_limit = 8
        self.boundary = None

    def service_hook(self, uc, addr):
        R = self.R
        ret = 0
        if addr == 0x8137C74C:  # The device state machine, not Manager::update.
            self.ticks += 1
            ret = self.device_states[0]
            if len(self.device_states)>1:self.device_states.pop(0)
        elif addr == 0x8137F568:  # No seat titles in synthetic fixture.
            pass
        elif addr == 0x8137A5BC:
            self.abort_calls += 1
        elif addr == 0x81515DA0:
            self.retraces += 1
            if self.retraces >= self.retrace_limit:
                self.boundary='bs2-wait'; uc.emu_stop(); return True
        elif addr == 0x81333228:
            # No console identifier is read, even in the synthetic fixture.
            self.boundary='settings-resources'; uc.emu_stop(); return True
        elif addr == 0x8150E984:
            self.boundary='worker-wait'; uc.emu_stop(); return True
        elif addr in (0x81369A98, 0x8133318C):
            pass  # Layout::calc and receive schedule stop
        elif addr in (0x8150963C, 0x81509664):
            ret = 1
        else:
            return super().service_hook(uc, addr)
        uc.reg_write(R.UC_PPC_REG_3, ret)
        uc.reg_write(R.UC_PPC_REG_PC, uc.reg_read(R.UC_PPC_REG_LR))
        return True

    def original(self, address, arg=None):
        self.thread='main';self.boundary=None;u=self.u;R=self.R
        u.reg_write(R.UC_PPC_REG_1, 0x817A0000)
        u.reg_write(R.UC_PPC_REG_LR, 0x80001000)
        u.reg_write(R.UC_PPC_REG_3, self.SCENE if arg is None else arg)
        u.emu_start(address, 0x80001000, count=200000)
        assert self.boundary or u.reg_read(R.UC_PPC_REG_PC)==0x80001000
        assert not any(self.locks.values())
        return u.context_save()

    def terminate_worker(self):
        self.thread='worker'
        self.run(0x8135E4D0,self.CDB+0x18)
        assert self.get(self.CDB+0x18)==0

    def finish_destroy(self, context):
        self.u.context_restore(context);self.thread='main';self.boundary=None
        # Complete the mocked sleep that yielded to the worker.
        self.u.reg_write(self.R.UC_PPC_REG_PC,self.u.reg_read(self.R.UC_PPC_REG_LR))
        self.u.emu_start(self.u.reg_read(self.R.UC_PPC_REG_PC),0x80001000,count=200000)
        assert self.u.reg_read(self.R.UC_PPC_REG_PC)==0x80001000


class SettingsBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled=compile_service()

    def test_settings_board_waits_for_cancelled_sd_work_then_termination(self):
        m=SettingsMachine(self.compiled);m.start();m.board()
        self.assertEqual(m.queue,[MESSAGE])
        m.call('cancel')
        m.original(0x8138E4A0)
        self.assertEqual(m.get(m.SCENE+0x60),13)
        self.assertEqual(m.queue,[MESSAGE])
        m.worker()
        m.original(0x8138E4A0)
        self.assertEqual(m.get(m.SCENE+0x60),16)
        self.assertEqual(m.queue,[1])
        context=m.original(0x8138E94C)
        self.assertEqual(m.boundary,'worker-wait')
        m.terminate_worker();m.finish_destroy(context)
        self.assertEqual(m.io,[])
        self.assertEqual(m.events,['fa-unmount','fa-detach'])
        self.assertEqual(m.call('drained'),1)

    def test_completed_batch_cdb_ownership_is_released_by_original_destroy(self):
        m=SettingsMachine(self.compiled);m.start();m.board();m.worker()
        m.board();m.worker();m.board()
        self.assertTrue(m.owned())
        m.call('cancel');self.assertEqual(len(m.freed),2)
        m.original(0x8138E4A0)
        context=m.original(0x8138E94C)
        self.assertEqual(m.boundary,'worker-wait')
        m.terminate_worker();m.finish_destroy(context)
        self.assertFalse(m.owned())
        self.assertEqual(m.events,['fa-unmount','fa-detach','cdb-mount','cdb-unmount'])
        m.original(0x813F0044)
        self.assertEqual(m.boundary,'settings-resources')

    def test_wrong_dirty_and_empty_disc_can_finish_manager_abort(self):
        for device in (52,53,55,56,59,64,66,67,68):
            with self.subTest(device=device):
                m=SettingsMachine(self.compiled);m.device_states=[device]
                m.original(0x813F0044)
                self.assertEqual(m.boundary,'settings-resources')
                self.assertEqual(m.get(m.BS2+4),8)
                self.assertEqual(m.ticks,1)
                self.assertEqual(m.abort_calls,int(device==64))

    def test_pending_abort_waits_for_device_completion(self):
        m=SettingsMachine(self.compiled);m.device_states=[1,1,64]
        m.original(0x813F0044)
        self.assertEqual(m.boundary,'settings-resources')
        self.assertEqual(m.ticks,3);self.assertEqual(m.abort_calls,1)

    def test_sd_drain_does_not_bypass_a_device_that_never_completes_abort(self):
        m=SettingsMachine(self.compiled);m.start();m.call('cancel')
        self.assertEqual(m.call('drained'),1)
        m.device_states=[1]
        m.original(0x813F0044)
        self.assertEqual(m.boundary,'bs2-wait')
        self.assertEqual(m.retraces,8);self.assertEqual(m.abort_calls,1)
        self.assertNotEqual(m.get(m.BS2+4),8)

    def test_preexisting_terminal_manager_error_does_not_reach_resources(self):
        for state in (9,10):
            with self.subTest(state=state):
                m=SettingsMachine(self.compiled);m.put(m.BS2+4,state)
                m.original(0x813F0044)
                self.assertEqual(m.boundary,'bs2-wait')
                self.assertEqual(m.ticks,0);self.assertEqual(m.abort_calls,0)
                self.assertEqual(m.get(m.BS2+4),state)


if __name__=='__main__':unittest.main()
