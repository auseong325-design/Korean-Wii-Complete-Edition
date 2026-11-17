import struct,unittest
from kwce.priiloader_hacks import _runs,_unique_hash,ini,apply,legacy_sections

class PriiloaderHackTests(unittest.TestCase):
    def test_runs_hash_and_apply(self):
        words=[0x60000000]*8+[0x38000000,0x2c000000,0x40820010]+[0x60000000]*8+[0x38000000,0x2c000000,0x41820010]
        old=struct.pack(f'>{len(words)}I',*words);new=bytearray(old);struct.pack_into('>I',new,8*4,0x38000001)
        runs=_runs(old,bytes(new));self.assertEqual(runs,[(32,36)])
        h=_unique_hash(old,32,1);self.assertEqual(h,[0x38000000,0x2c000000,0x40820010])
        entry=dict(name='t',pairs=[(h,[0x38000001])])
        self.assertEqual(apply(old,[entry]),bytes(new))
        text=ini([entry]);self.assertIn('hash=0x38000000,0x2c000000,0x40820010',text);self.assertIn('minversion=518',text)

    def test_legacy_filter(self):
        text='[A]\r\nmaxversion=518\r\nminversion=1\r\namount=1\r\nhash=0x1\r\npatch=0x2\r\n[B]\r\nminversion=1\r\nmaxversion=9\r\namount=1\r\noffset=0x8\r\npatch=0x1\r\n[C]\r\nmaxversion=9\r\nminversion=1\r\namount=1\r\nrequire=x\r\nhash=0x1\r\npatch=0x2\r\n'
        kept,dropped=legacy_sections(text)
        self.assertEqual(kept.split('\n')[0],'[A]');self.assertEqual(dropped,['[B]','[C]'])

if __name__=='__main__':unittest.main()
