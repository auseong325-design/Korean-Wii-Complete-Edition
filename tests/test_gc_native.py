import struct,unittest
from kwce.gc_fixture import raw_card,gci_fixture,checksum
from kwce.gc_native import dol_offset,patch_gc_native
from kwce.gc_icons import patch_gc_icons

class GCNativeTests(unittest.TestCase):
    def test_wrong_dol_is_refused(self):
        with self.assertRaises(ValueError):patch_gc_native(bytes(512))

    def test_data_section_address_mapping_and_bounds(self):
        b=bytearray(512)
        for table,value in [(0,256),(0x48,0x81330000),(0x90,256)]:struct.pack_into('>I',b,table+7*4,value)
        self.assertEqual(dol_offset(b,0x81330040),320)
        with self.assertRaises(ValueError):dol_offset(b,0x80000000)
        struct.pack_into('>I',b,0x90+7*4,512)
        with self.assertRaises(ValueError):dol_offset(b,0x81330100)

    def test_synthetic_cards_checksums_all_sizes_encodings(self):
        for mbits in [4,128]:
            for encoding in [0,1]:
                for saved in [False,True]:
                    with self.subTest(mbits=mbits,encoding=encoding,saved=saved):
                        b=raw_card(saved,encoding,mbits)
                        self.assertEqual(len(b),mbits*131072)
                        self.assertEqual(struct.unpack_from('>HH',b,0x22),(mbits,encoding))
                        self.assertEqual(struct.unpack_from('>HH',b,0x1fc),checksum(b[:0x1fc]))
                        for start in [8192,16384]:self.assertEqual(struct.unpack_from('>HH',b,start+0x1ffc),checksum(b[start:start+0x1ffc]))
                        for start in [24576,32768]:
                            self.assertEqual(struct.unpack_from('>HH',b,start),checksum(b[start+4:start+8192]))
                            self.assertEqual(int.from_bytes(b[start+6:start+8],'big'),mbits*16-5-int(saved))
                        self.assertEqual(b[8192:16384],b[16384:24576])
                        self.assertEqual(b[24576:32768],b[32768:40960])
                        if saved:self.assertEqual(b[40960:49152],gci_fixture()[64:])

    def test_invalid_size_and_wrong_icon_archive_refused(self):
        with self.assertRaises(ValueError):raw_card(mbits=7)
        with self.assertRaises(ValueError):patch_gc_icons(bytes(128))

if __name__=='__main__':unittest.main()
