import unittest
from kwce.wiiroom_compat import null_path_blocks,patch_null_open_diagnostic,normalize_null_path_blocks


class NullPathGuardTests(unittest.TestCase):
    def test_null_returns_invalid_without_stack_or_memory_writes(self):
        self.check_path(0)

    def test_valid_path_preserves_argument_and_original_prologue(self):
        for path in(1,0x80300000,0xffffffff):
            with self.subTest(path=path):self.check_path(path)

    def check_path(self,path,normalize=False):
        entry=0x80302cd0;caves=[0x802cfe64,0x802d0524,0x802d1304]
        blocks=(normalize_null_path_blocks if normalize else null_path_blocks)(entry,caves,bytes.fromhex('9421ffa0'))
        words={address+i:int.from_bytes(data[i:i+4],'big')for address,data in blocks.items()for i in range(0,len(data),4)}
        regs={1:0x81700000,3:path};pc=entry;eq=False;writes=[];returned=False
        def signed(value,bits):return value-(1<<bits)if value&(1<<(bits-1))else value
        for step in range(12):
            if pc==entry+4:break
            word=words[pc];op=word>>26;next_pc=pc+4
            if word==0x4e800020:returned=True;break
            if op==18:next_pc=pc+signed(word&0x3fffffc,26)
            elif op==16:
                self.assertEqual((word>>21)&31,4);self.assertEqual((word>>16)&31,2)
                if not eq:next_pc=pc+signed(word&0xfffc,16)
            elif op==11:eq=regs[3]==signed(word&65535,16)
            elif op==14:regs[3]=(signed(word&65535,16)+(regs[3]if(word>>16)&31 else 0))&0xffffffff
            elif op==15:regs[3]=(word&65535)<<16
            elif op==37:
                self.assertEqual(word,0x9421ffa0);old=regs[1];regs[1]=(old-0x60)&0xffffffff;writes.append((regs[1],old))
            else:self.fail('Unexpected guard instruction')
            pc=next_pc
        if path or normalize:
            self.assertFalse(returned);self.assertEqual(pc,entry+4);self.assertEqual(regs[3],path if path else caves[1]+8);self.assertEqual(regs[1],0x81700000-0x60);self.assertEqual(writes,[(regs[1],0x81700000)])
        else:
            self.assertTrue(returned);self.assertEqual(regs[3],(-101)&0xffffffff);self.assertEqual(regs[1],0x81700000);self.assertEqual(writes,[])

    def test_other_executable_is_refused(self):
        with self.assertRaises(ValueError):patch_null_open_diagnostic(bytes(1024))

    def test_empty_path_normalization_preserves_real_filesystem_call(self):
        for path in(0,1,0x80300000):
            with self.subTest(path=path):self.check_path(path,normalize=True)
