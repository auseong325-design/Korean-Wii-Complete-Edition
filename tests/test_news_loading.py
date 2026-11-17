"""Execute the assembled patch's small PPC subset, with SDK calls stubbed."""
import struct, unittest
from pathlib import Path
from kwce.news_loading import CAVE, OPEN, RETRIES, code, patch, branch
from kwce.ppc_patch import to_file
from kwce.channels import load_library

def signed(n, bits=32):
    return n - (1 << bits) if n & (1 << (bits - 1)) else n

class PPC:
    def __init__(self, blob):
        self.mem = {CAVE+i: b for i, b in enumerate(blob)}
        self.r = [0]*32; self.r[1] = 0x81700000; self.r[13] = 0x80300000
        self.lr = 0; self.cr = [False]*32
        self.sdk_result = 0; self.hour = 0
    def read(self, a):
        return sum(self.mem.get(a+i, 0) << (24-8*i) for i in range(4))
    def write(self, a, n):
        for i, b in enumerate(struct.pack('>I', n & 0xffffffff)): self.mem[a+i] = b
    def run(self, start):
        pc = start; self.lr = 0x81000000
        for _ in range(300):
            if not CAVE <= pc < CAVE+188: return pc
            w = self.read(pc); op = w >> 26; rt = (w >> 21) & 31; ra = (w >> 16) & 31
            imm = signed(w & 65535, 16); nxt = pc+4
            if op in (14, 15): self.r[rt] = ((self.r[ra] if ra else 0)+(imm << (16 if op == 15 else 0))) & 0xffffffff
            elif op == 24: self.r[ra] = self.r[rt] | (w & 65535)
            elif op in (32, 36, 37):
                a = ((self.r[ra] if ra else 0)+imm) & 0xffffffff
                if op == 32: self.r[rt] = self.read(a)
                else: self.write(a, self.r[rt])
                if op == 37: self.r[ra] = a
            elif op in (10, 11):
                a, b = self.r[ra], w & 65535
                if op == 11: a, b = signed(a), imm
                self.cr[0:3] = [a < b, a > b, a == b]
            elif op == 16:
                bo, bi = rt, ra
                assert bo in (4, 12), 'Only simple condition branches expected'
                if self.cr[bi] == (bo == 12): nxt = pc+signed(w & 0xfffc, 16)
            elif op == 18:
                target = pc+signed(w & 0x3fffffc, 26)
                if w & 1: self.lr = pc+4
                if target == OPEN: self.r[3] = self.sdk_result & 0xffffffff
                elif target == 0x80076138: self.write(self.r[3]+8, self.hour)
                else: nxt = target
            elif op == 19 and (w >> 1) & 1023 == 16: nxt = self.lr
            elif op == 31:
                xo = (w >> 1) & 1023
                if xo == 339: self.r[rt] = self.lr
                elif xo == 467: self.lr = self.r[rt]
                elif xo == 24: self.r[ra] = (self.r[rt] << (self.r[(w >> 11) & 31] & 63)) & 0xffffffff
                else: raise AssertionError(f'Unexpected extended opcode {xo}')
            else: raise AssertionError(f'Unexpected opcode {op}')
            pc = nxt
        raise AssertionError('Patch did not return within instruction budget')

class NewsLoadingCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.blob, cls.labels = code()
    def test_consecutive_busy_is_bounded_and_sdk_error_is_native(self):
        for error in (-22, -26, -29):
            cpu = PPC(self.blob); cpu.sdk_result = error
            sp, preserved = cpu.r[1], cpu.r[13:]
            for _ in range(299):
                self.assertEqual(cpu.run(self.labels['retry']), 0x81000000)
                self.assertEqual(signed(cpu.r[3]), error)
            cpu.run(self.labels['retry'])
            self.assertEqual(signed(cpu.r[3]), -31)
            self.assertEqual(signed(cpu.read(cpu.r[13]-28364)), -107226)
            self.assertEqual(cpu.read(CAVE+188), 0)
            self.assertEqual(cpu.r[1], sp); self.assertEqual(cpu.r[13:], preserved)
    def test_success_or_other_error_resets_only_consecutive_busy(self):
        cpu = PPC(self.blob); cpu.sdk_result = -26
        for _ in range(299): cpu.run(self.labels['retry'])
        for result in (0, -1, -31):
            cpu.sdk_result = result; cpu.run(self.labels['retry'])
            self.assertEqual(signed(cpu.r[3]), result); self.assertEqual(cpu.read(CAVE+188), 0)
        cpu.sdk_result = -22; cpu.run(self.labels['retry'])
        self.assertEqual(signed(cpu.r[3]), -22); self.assertEqual(cpu.read(CAVE+188), 1)
    def test_calendar_mask_all_hours_and_invalid_hour_with_balanced_stack(self):
        for hour in list(range(24))+[24, 0xffffffff]:
            cpu = PPC(self.blob); cpu.hour = hour; sp = cpu.r[1]
            self.assertEqual(cpu.run(self.labels['mask']), 0x81000000)
            self.assertEqual(cpu.r[3], 1 << hour if hour < 24 else 1)
            self.assertEqual(cpu.r[1], sp)
    def test_partial_cache_continues_only_after_an_existing_file(self):
        for opened, loaded, target in [(True,0,0x80042f60),(False,0,0x80042ed8),(False,1,0x8004309c),(False,23,0x8004309c)]:
            cpu = PPC(self.blob); cpu.cr[2] = not opened; cpu.r[29] = loaded
            self.assertEqual(cpu.run(self.labels['missing']), target)
    def test_branch_encoding_refuses_out_of_range_and_unaligned(self):
        for target in (CAVE+1, CAVE+0x2000000):
            with self.assertRaises(ValueError): branch(CAVE, target)

@unittest.skipUnless(Path('workspace/channels/news/build-v16/news-ko-personal.wad').exists(), 'local personal News builds required')
class NewsLoadingArtifactTests(unittest.TestCase):
    def test_production_rebuild_and_exact_change_boundary(self):
        lib = load_library(); titles = []
        for v in (15,16):
            t = lib.title.Title(); t.load_wad(Path(f'workspace/channels/news/build-v{v}/news-ko-personal.wad').read_bytes()); titles.append(t)
        old, new = titles; before = old.get_content_by_index(1); after = new.get_content_by_index(1)
        self.assertEqual(patch(before)[0], after)
        old.set_content(after,1)
        self.assertEqual(old.dump_wad(), Path('workspace/channels/news/build-v16/news-ko-personal.wad').read_bytes())
        self.assertEqual(after[to_file(after,OPEN):to_file(after,OPEN)+8], before[to_file(before,OPEN):to_file(before,OPEN)+8])
        allowed = set(range(to_file(before,CAVE),to_file(before,CAVE)+192))
        for va in RETRIES+[0x80042044,0x80042048,0x80042ed4]: allowed.update(range(to_file(before,va),to_file(before,va)+4))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(before,after)) if a != b))
        self.assertEqual(after[to_file(after,0x80042048):to_file(after,0x80042048)+4], bytes.fromhex('7c651b78'))
        changed = bytearray(before); changed[to_file(before,RETRIES[0])] ^= 1
        with self.assertRaises(ValueError): patch(bytes(changed))

if __name__ == '__main__': unittest.main()
