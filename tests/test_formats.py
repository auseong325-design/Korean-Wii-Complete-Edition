import hashlib,random,struct,unittest
from kwce.formats import ash_compress,ash_decompress,U8
from kwce.patches import patch_layout,_gc_candidates,gc_detection_prototype,CHANGES

def archive(payload=b'example'):
    strings=b'\0arc\0test\0other\0';root=32;count=4;header=count*12+len(strings);start=(root+header+31)&~31
    data=bytearray(start);data[:16]=struct.pack('>4I',0x55aa382d,root,header,start)
    nodes=[(0x1000000,0,4),(0x1000001,0,3),(5,start,len(payload)),(10,start+len(payload),3)]
    for i,row in enumerate(nodes):struct.pack_into('>III',data,root+i*12,*row)
    data[root+count*12:root+header]=strings;data.extend(payload+b'xyz');return bytes(data)

class ArchiveTests(unittest.TestCase):
    def test_ash_literal_overlap_and_random_roundtrips(self):
        rng=random.Random(34)
        for data in [b'',b'x',b'x'*10000,bytes(range(256))*24,rng.randbytes(4096),b'abcd'*4000]:
            with self.subTest(length=len(data)):self.assertEqual(ash_decompress(ash_compress(data)),data)

    def test_truncated_ash_rejected(self):
        with self.assertRaises(ValueError):ash_decompress(b'ASH0'+bytes(12))

    def test_ash_size_limit_rejected(self):
        with self.assertRaises(ValueError):ash_decompress(ash_compress(b'x'*100),max_size=99)

    def test_u8_append_keeps_directory_and_other_file(self):
        raw=archive();u=U8(raw);result=u.replace('arc/test',b'q'*150);v=U8(result)
        self.assertEqual(v.get('arc/test'),b'q'*150);self.assertEqual(v.get('other'),b'xyz')
        self.assertEqual(raw[44:56],result[44:56])

    def test_same_size_edit_does_not_repack_header(self):
        raw=archive(b'ab');u=U8(raw);result=u.replace('arc/test',b'cd')
        self.assertEqual(raw[:u.files['arc/test'][0]],result[:u.files['arc/test'][0]])

    def test_bad_directory_parent_rejected(self):
        raw=bytearray(archive());struct.pack_into('>I',raw,48,3)
        with self.assertRaises(ValueError):U8(raw)

    def test_unsafe_name_rejected(self):
        raw=archive().replace(b'arc\0',b'../\0')
        with self.assertRaises(ValueError):U8(raw)

    def test_out_of_bounds_file_rejected(self):
        raw=bytearray(archive());struct.pack_into('>I',raw,60,len(raw)+1)
        with self.assertRaises(ValueError):U8(raw)

    def test_unrecognized_layout_rejected(self):
        with self.assertRaises(ValueError):patch_layout(b'RLYT'+bytes(10000))

    def test_only_declared_layout_offsets_change(self):
        data=b'RLYT'+bytes(10000);out=patch_layout(data,hashlib.sha256(data).hexdigest())
        self.assertEqual({i for i,(a,b) in enumerate(zip(data,out)) if a!=b},set(CHANGES))

    def test_non_original_dol_refused(self):
        with self.assertRaises(ValueError):gc_detection_prototype(bytes(500))

    def test_gc_pattern_requires_gc_state_and_function_range(self):
        data=bytearray(320);struct.pack_into('>I',data,7*4,256);struct.pack_into('>I',data,0x48+7*4,0x8137c74c);struct.pack_into('>I',data,0x90+7*4,64)
        motif=bytes.fromhex('380000002c0000004082001038000036900da9c84800176038000032')
        data[256:256+len(motif)]=motif;self.assertEqual(len(_gc_candidates(data)),1)
        data[280:284]=bytes.fromhex('38000031');self.assertEqual(_gc_candidates(data),[])

if __name__=='__main__':unittest.main()
