"""Exercise the ACTUAL assembled country bridge on a tiny PPC interpreter.

Modelled on tests/test_channel_ipc_deadline.py: we assemble the real bridge, write it
into the real channel DOL at the real addresses, then execute the country / region
getters instruction by instruction. The reader at 0x8010db60 (a SYSCONF IPL.SADR read)
is stubbed to hand back a test address word, exactly as the IPC test stubs its SDK
calls, so the test needs no console and no IOS.

Proven here:
  * country byte 136 -> 49, every other country byte unchanged (all 256 inputs);
  * the region byte and all other SADR bytes are preserved;
  * the region getter is byte-for-byte unaffected by the disguise;
  * r1 (stack), LR and every non-volatile register are preserved;
  * the bridge is deterministic and refuses a base whose bytes differ.
"""
import unittest
from pathlib import Path

from kwce.channels import load_library
from kwce.ppc_patch import to_file
from kwce import votes_country_bridge as bridge

READER = 0x8010DB60          # SYSCONF IPL.SADR reader (stubbed)
COUNTRY_GETTER = 0x800509B4  # bl reader; srwi r3,r3,24
REGION_GETTER = 0x800509D8   # bl reader; rlwinm r3,r3,16,24,31
SENTINEL_LR = 0x81000000
VOTES = Path('workspace/channels/votes')


def signed(v, bits=32):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


class Machine:
    """Just enough PPC to run the two getters and the bridge cave."""

    def __init__(self, dol, sadr):
        self.dol = dol
        self.sadr = sadr & 0xFFFFFFFF
        # Section map: (file_offset, virtual_address, size) for addressing.
        import struct
        off = struct.unpack_from('>18I', dol, 0)
        addr = struct.unpack_from('>18I', dol, 0x48)
        size = struct.unpack_from('>18I', dol, 0x90)
        self.secs = [(off[i], addr[i], size[i]) for i in range(18) if size[i]]
        self.r = [0] * 32
        self.r[1] = 0x81600000               # stack pointer
        self.r[24:] = range(0xA24, 0xA24 + 8)  # non-volatile sentinels r24..r31
        self.cr = [False] * 3                 # lt, gt, eq (cr0)
        self.lr = SENTINEL_LR
        self.ram = {}

    def _fo(self, va):
        for o, a, s in self.secs:
            if a <= va < a + s:
                return o + va - a
        return None

    def ins(self, va):
        import struct
        return struct.unpack_from('>I', self.dol, self._fo(va))[0]

    def run(self, start):
        pc = start
        for _ in range(10000):
            if pc == SENTINEL_LR:
                return self.r[3]
            w = self.ins(pc)
            op = w >> 26
            rt = (w >> 21) & 31
            ra = (w >> 16) & 31
            imm = signed(w & 0xFFFF, 16)
            nxt = pc + 4
            if op == 14:                                  # addi / li
                self.r[rt] = ((self.r[ra] if ra else 0) + imm) & 0xFFFFFFFF
            elif op == 32:                                # lwz
                self.r[rt] = self.ram.get((self.r[ra] + imm) & 0xFFFFFFFF, 0)
            elif op in (36, 37):                          # stw / stwu
                a = (self.r[ra] + imm) & 0xFFFFFFFF
                self.ram[a] = self.r[rt]
                if op == 37:
                    self.r[ra] = a
            elif op == 10:                                # cmpli (cmplwi)
                v = self.r[ra] & 0xFFFFFFFF
                u = w & 0xFFFF
                self.cr = [v < u, v > u, v == u]
            elif op == 21:                                # rlwinm
                sh = (w >> 11) & 31
                mb = (w >> 6) & 31
                me = (w >> 1) & 31
                v = ((self.r[rt] << sh) | (self.r[rt] >> (32 - sh if sh else 32))) & 0xFFFFFFFF
                mask = sum(1 << (31 - i) for i in range(32)
                           if (mb <= i <= me if mb <= me else i >= mb or i <= me))
                self.r[ra] = v & mask
            elif op == 16:                                # bc (bne/beq cr0)
                assert rt in (4, 12), f'unexpected BO {rt}'
                if self.cr[2] == (rt == 12):
                    nxt = pc + signed(w & 0xFFFC, 16)
            elif op == 18:                                # b / bl
                target = pc + signed(w & 0x3FFFFFC, 26)
                if w & 1:
                    self.lr = pc + 4
                if target == READER:                      # stub the IPL.SADR reader
                    self.r[3] = self.sadr
                    nxt = pc + 4
                else:
                    nxt = target
            elif op == 19 and (w >> 1) & 0x3FF == 16:     # blr
                nxt = self.lr
            elif op == 31:                                # mflr / mtlr
                xo = (w >> 1) & 0x3FF
                if xo == 339:
                    self.r[rt] = self.lr
                elif xo == 467:
                    self.lr = self.r[rt]
                else:
                    raise AssertionError(f'unexpected ext op {xo} at {pc:#x}')
            else:
                raise AssertionError(f'unexpected opcode {op} at {pc:#x}')
            pc = nxt
        raise AssertionError('getter did not return')


class CountryBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = load_library().title.Title()
        t.load_wad((VOTES / 'build-v18/votes-ko-ui-test.wad').read_bytes())
        cls.base = t.get_content_by_index(1)
        cls.dol = bridge.patch(cls.base)

    def _call(self, va, sadr):
        m = Machine(self.dol, sadr)
        sp, nonvol = m.r[1], list(m.r[24:])
        result = m.run(va)
        self.assertEqual(m.r[1], sp, 'stack pointer not restored')
        self.assertEqual(list(m.r[24:]), nonvol, 'non-volatile register clobbered')
        self.assertEqual(m.lr, SENTINEL_LR, 'LR not preserved')
        return result

    def test_cave_reproduces_the_replaced_shift(self):
        # The cave's first instruction must be the exact srwi it replaced.
        cave, _ = bridge.code()
        self.assertEqual(cave[:4], bridge.ORIG_SRWI)

    def test_korea_is_disguised_as_usa(self):
        # Country byte 136 in bits 24..31, arbitrary region/other bytes elsewhere.
        for other in (0x00000000, 0x0000AB00, 0x00FF5A00, 0xFFFFFFFF & ~(0xFF << 24)):
            sadr = (136 << 24) | (other & 0x00FFFFFF)
            self.assertEqual(self._call(COUNTRY_GETTER, sadr), 49)

    def test_every_other_country_is_unchanged(self):
        for c in range(256):
            if c == 136:
                continue
            sadr = (c << 24) | 0x00125A00   # region byte = 0x5A, noise in byte1
            self.assertEqual(self._call(COUNTRY_GETTER, sadr), c,
                             f'country {c} should pass through unchanged')

    def test_region_getter_untouched_even_for_korea(self):
        # Region is extracted as (SADR>>16)&0xFF (bits 8..15); the disguise must not
        # alter it, Korea or not.
        for country in (136, 49, 1):
            for region in (0x00, 0x2A, 0xFF):
                sadr = (country << 24) | (region << 16) | 0x0000AB01
                self.assertEqual(self._call(REGION_GETTER, sadr), region)

    def test_region_getter_identical_on_unpatched_dol(self):
        patched, plain = self.dol, self.base
        for country in (136, 49):
            sadr = (country << 24) | (0x2A << 16)
            a = Machine(patched, sadr).run(REGION_GETTER)
            b = Machine(plain, sadr).run(REGION_GETTER)
            self.assertEqual(a, b)
            self.assertEqual(a, 0x2A)

    def test_unpatched_country_getter_returns_raw_byte(self):
        # Control: without the bridge, 136 stays 136.
        self.assertEqual(Machine(self.base, 136 << 24).run(COUNTRY_GETTER), 136)

    def test_bridge_is_deterministic(self):
        self.assertEqual(bridge.code(), bridge.code())
        self.assertEqual(bridge.patch(self.base), self.dol)

    def test_refuses_changed_base(self):
        corrupt = bytearray(self.base)
        corrupt[to_file(corrupt, bridge.GETTER_SRWI)] ^= 1
        with self.assertRaises(ValueError):
            bridge.patch(bytes(corrupt))
        corrupt = bytearray(self.base)
        corrupt[to_file(corrupt, bridge.CAVE, bridge.CAVE_SIZE)] = 1
        with self.assertRaises(ValueError):
            bridge.patch(bytes(corrupt))


class CountryBuildArtifact(unittest.TestCase):
    def test_v19_is_v18_plus_only_the_country_bridge(self):
        wad = VOTES / 'build-v19/votes-ko-ui-test.wad'
        if not wad.exists():
            self.skipTest('build-v19 not built yet')
        lib = load_library()
        v18, v19 = lib.title.Title(), lib.title.Title()
        v18.load_wad((VOTES / 'build-v18/votes-ko-ui-test.wad').read_bytes())
        v19.load_wad(wad.read_bytes())
        changed = [i for i in range(14)
                   if v18.get_content_by_index(i) != v19.get_content_by_index(i)]
        self.assertEqual(changed, [1])
        self.assertEqual(bridge.patch(v18.get_content_by_index(1)),
                         v19.get_content_by_index(1))
        self.assertEqual(v19.tmd.region, v18.tmd.region)


class CountryConstantTests(unittest.TestCase):
    """Revision 20: ``li r3,49`` in place of the srwi -- no cave, 4 bytes."""

    @classmethod
    def setUpClass(cls):
        t = load_library().title.Title()
        t.load_wad((VOTES / 'build-v18/votes-ko-ui-test.wad').read_bytes())
        cls.base = t.get_content_by_index(1)
        cls.dol = bridge.patch_constant(cls.base)

    def _call(self, va, sadr):
        m = Machine(self.dol, sadr)
        sp, nonvol = m.r[1], list(m.r[24:])
        result = m.run(va)
        self.assertEqual(m.r[1], sp)
        self.assertEqual(list(m.r[24:]), nonvol)
        self.assertEqual(m.lr, SENTINEL_LR)
        return result

    def test_only_one_instruction_changes(self):
        diff = [i for i, (a, b) in enumerate(zip(self.base, self.dol)) if a != b]
        self.assertEqual(len(self.dol), len(self.base))
        self.assertLessEqual(len(diff), 4)
        at = to_file(bytearray(self.base), bridge.GETTER_SRWI)
        self.assertTrue(all(at <= i < at + 4 for i in diff))
        self.assertEqual(self.dol[:0xE8], self.base[:0xE8])         # section table untouched

    def test_country_getter_returns_usa_for_korea_and_everything(self):
        for c in range(256):
            self.assertEqual(self._call(COUNTRY_GETTER, (c << 24) | 0x00125A00), 49)

    def test_region_getter_untouched(self):
        for country in (136, 49):
            for region in (0x00, 0x2A, 0xFF):
                sadr = (country << 24) | (region << 16) | 0x0000AB01
                self.assertEqual(self._call(REGION_GETTER, sadr), region)

    def test_does_not_use_the_init_table_tail(self):
        # build-v19 crashed because its cave was the zero tail of text0 (.init tables).
        import struct
        text1_start = struct.unpack_from('>I', self.dol, 0x48 + 4)[0]      # section 1 = text1
        self.assertGreaterEqual(bridge.GETTER_SRWI, text1_start)           # the only edit is in text1
        changed = [i for i, (a, b) in enumerate(zip(self.base, self.dol)) if a != b]
        self.assertTrue(changed)
        self.assertEqual(self.dol[to_file(bytearray(self.dol), bridge.CAVE, bridge.CAVE_SIZE):][:bridge.CAVE_SIZE],
                         bytes(bridge.CAVE_SIZE))                          # the .init tail stays all zero

    def test_refuses_changed_base_and_is_deterministic(self):
        self.assertEqual(bridge.patch_constant(self.base), self.dol)
        corrupt = bytearray(self.base)
        corrupt[to_file(corrupt, bridge.GETTER_SRWI)] ^= 1
        with self.assertRaises(ValueError):
            bridge.patch_constant(bytes(corrupt))

    def test_v20_artifact_is_v18_plus_only_the_constant(self):
        wad = VOTES / 'build-v20/votes-ko-ui-test.wad'
        if not wad.exists():
            self.skipTest('build-v20 not built yet')
        lib = load_library()
        v18, v20 = lib.title.Title(), lib.title.Title()
        v18.load_wad((VOTES / 'build-v18/votes-ko-ui-test.wad').read_bytes())
        v20.load_wad(wad.read_bytes())
        changed = [i for i in range(14) if v18.get_content_by_index(i) != v20.get_content_by_index(i)]
        self.assertEqual(changed, [1])
        self.assertEqual(bridge.patch_constant(v18.get_content_by_index(1)), v20.get_content_by_index(1))
        self.assertEqual(v20.tmd.region, v18.tmd.region)


if __name__ == '__main__':
    unittest.main()
