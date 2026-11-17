"""Wii Room v68 (MiiInfo code 0) and Votes v22 (239001 readout): the channels' own code under Unicorn.

No network or console data. Callees outside the edited routine are stubbed.
"""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOM = {n: ROOT / f'workspace/channels/wiiroom/build-v{n}/wiiroom-ko-local-test.wad' for n in (66, 68)}
VOTES = {n: ROOT / f'workspace/channels/votes/build-v{n}/votes-ko-ui-test.wad' for n in (21, 22)}
VOTES_V23 = ROOT / 'workspace/channels/votes/build-v23/votes-ko-ui-test.wad'
STOP = 0x817ffff0


def executable(path, compressed):
    from kwce.channels import load_library
    title = load_library().title.Title(); title.load_wad(path.read_bytes())
    raw = title.get_content_by_index(1)
    if compressed:
        from kwce.wiiroom_formats import decompress_lz11
        raw = decompress_lz11(raw)
    return raw


def machine(dol):
    from unicorn import Uc, UC_ARCH_PPC, UC_MODE_32, UC_MODE_BIG_ENDIAN
    from unicorn import ppc_const as p
    u = Uc(UC_ARCH_PPC, UC_MODE_32 | UC_MODE_BIG_ENDIAN); u.mem_map(0x80000000, 0x01800000)
    for i in range(18):
        off, addr, size = (struct.unpack_from('>I', dol, base + 4 * i)[0] for base in (0, 0x48, 0x90))
        if size: u.mem_write(addr, dol[off:off + size])
    u.reg_write(p.UC_PPC_REG_1, 0x817f0000); u.reg_write(p.UC_PPC_REG_LR, STOP)
    return u, p


def stub(u, p, addresses, log):
    from unicorn import UC_HOOK_CODE
    def hook(uc, address, size, _):
        if address in addresses:
            log.append((address, uc.reg_read(p.UC_PPC_REG_3), uc.reg_read(p.UC_PPC_REG_4), uc.reg_read(p.UC_PPC_REG_5), uc.reg_read(p.UC_PPC_REG_6)))
            uc.reg_write(p.UC_PPC_REG_PC, uc.reg_read(p.UC_PPC_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)


def room_check(dol, code):
    """Run the MiiInfo reply checker; return (accepted, stored code, error value or None)."""
    CHECK, MAKE_ERROR, REPORT = 0x8004b454, 0x8001b1b8, 0x800184d8
    u, p = machine(dol); reply = 0x81700000; log = []
    u.mem_write(reply, struct.pack('>i', code)); u.reg_write(p.UC_PPC_REG_4, 0x81700100); u.reg_write(p.UC_PPC_REG_6, reply)
    stub(u, p, {MAKE_ERROR, REPORT}, log); u.emu_start(CHECK, STOP, count=2000)
    made = [struct.unpack('>i', struct.pack('>I', r4))[0] for a, _, r4, _, _ in log if a == MAKE_ERROR]
    return u.reg_read(p.UC_PPC_REG_3), struct.unpack('>i', bytes(u.mem_read(reply, 4)))[0], made[0] if made else None


def votes_number(dol, last_err, nwc24_err):
    """Run the DLTaskManager error display; return the number handed to the %06d formatter."""
    SHOW, FORMAT, DIALOG = 0x800766ac, 0x800cf240, 0x80053548
    u, p = machine(dol); this = 0x81700000; log = []; r13 = 0x81710000
    u.mem_write(this + 0xc, struct.pack('>ii', last_err, nwc24_err)); u.reg_write(p.UC_PPC_REG_13, r13)
    u.mem_write(r13 - 0x7440, struct.pack('>I', 0x81720000)); u.reg_write(p.UC_PPC_REG_3, this)
    stub(u, p, {FORMAT, DIALOG, 0x801010b8}, log); u.emu_start(SHOW, STOP, count=2000)
    (_, buffer, size, fmt, number), = [x for x in log if x[0] == FORMAT]
    return buffer, size, fmt, number


@unittest.skipUnless(all(p.is_file() for p in ROOM.values()), 'Wii Room v66/v68 builds not present')
class RoomMiiInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = executable(ROOM[66], True), executable(ROOM[68], True)

    def test_only_the_checker_changes(self):
        from kwce.ppc_patch import to_file
        at = to_file(self.old, 0x8004b468, 36)
        self.assertEqual(len(self.old), len(self.new))
        self.assertTrue(all(at <= i < at + 36 for i in range(len(self.old)) if self.old[i] != self.new[i]))

    def test_parent_rejects_the_live_reply_code(self):
        self.assertEqual(room_check(self.old, 0), (0, 0, 0))        # error type 5 -> 354405

    def test_zero_is_accepted_as_one_and_the_rest_is_unchanged(self):
        self.assertEqual(room_check(self.new, 0), (1, 1, None))
        for code in (1, 2):
            self.assertEqual(room_check(self.new, code), room_check(self.old, code))
            self.assertEqual(room_check(self.new, code), (1, code, None))
        for code in (3, -1, 399):
            self.assertEqual(room_check(self.new, code), room_check(self.old, code))
            self.assertEqual(room_check(self.new, code), (0, code, code))


@unittest.skipUnless(all(p.is_file() for p in VOTES.values()), 'Votes v21/v22 builds not present')
class VotesReadoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = executable(VOTES[21], False), executable(VOTES[22], False)

    def test_only_the_default_number_changes(self):
        from kwce.ppc_patch import to_file
        at = to_file(self.old, 0x80076870, 28)
        self.assertEqual(len(self.old), len(self.new))
        self.assertTrue(all(at <= i < at + 28 for i in range(len(self.old)) if self.old[i] != self.new[i]))

    def test_parent_shows_the_fixed_number(self):
        for state in ((7, -30), (0, 0), (8, 0)):
            self.assertEqual(votes_number(self.old, *state), (0x81720080, 7, 0x80230df8, 239001))

    def test_number_carries_the_nwc24_result(self):
        self.assertEqual(votes_number(self.new, 7, -30), (0x81720080, 7, 0x80230df8, 23930))
        self.assertEqual(votes_number(self.new, 7, -45), (0x81720080, 7, 0x80230df8, 23945))
        self.assertEqual(votes_number(self.new, 0, 0), (0x81720080, 7, 0x80230df8, 23900))

    def test_other_error_classes_are_unchanged(self):
        for state in ((1, -1), (3, -39), (5, -32)):
            with self.subTest(state=state):
                u_old = [x for x in self._trace(self.old, *state)]; u_new = [x for x in self._trace(self.new, *state)]
                self.assertEqual(u_old, u_new)

    @staticmethod
    def _trace(dol, last_err, nwc24_err):
        u, p = machine(dol); this = 0x81700000; log = []; r13 = 0x81710000
        u.mem_write(this + 0xc, struct.pack('>ii', last_err, nwc24_err)); u.reg_write(p.UC_PPC_REG_13, r13)
        u.mem_write(r13 - 0x7440, struct.pack('>I', 0x81720000)); u.mem_write(r13 - 0x6f54, struct.pack('>I', 0x81730000))
        u.reg_write(p.UC_PPC_REG_3, this)
        stub(u, p, {0x800cf240, 0x80053548, 0x801010b8}, log); u.emu_start(0x800766ac, STOP, count=2000)
        return log


@unittest.skipUnless(VOTES[22].is_file() and VOTES_V23.is_file(), 'Votes v22/v23 builds not present')
class VotesQuietSignatureTests(unittest.TestCase):
    """v23: NWC24 -45 (VERIFY_SIGNATURE, WiiLink result maps) shows no dialog; all else as v22."""
    @classmethod
    def setUpClass(cls):
        cls.old, cls.new = executable(VOTES[22], False), executable(VOTES_V23, False)

    def test_only_the_display_function_changes(self):
        from kwce.ppc_patch import to_file
        lo, hi = to_file(self.old, 0x800766ac, 4), to_file(self.old, 0x80076714, 4)
        self.assertEqual(len(self.old), len(self.new))
        changed = [i for i in range(len(self.old)) if self.old[i] != self.new[i]]
        self.assertTrue(changed and all(lo <= i < hi for i in changed))

    def test_signature_failure_shows_nothing(self):
        for last in (7, 0):
            with self.subTest(last=last):
                self.assertEqual(VotesReadoutTests._trace(self.new, last, -45), [])

    def test_every_other_result_is_shown_as_before(self):
        for state in ((7, -30), (7, -44), (7, -46), (0, 0), (8, -31), (1, -1), (2, -45), (3, -39), (4, -2), (5, -32), (6, -45)):
            with self.subTest(state=state):
                self.assertEqual(VotesReadoutTests._trace(self.old, *state), VotesReadoutTests._trace(self.new, *state))


if __name__ == '__main__':
    unittest.main()
