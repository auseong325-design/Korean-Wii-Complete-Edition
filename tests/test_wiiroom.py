import random,struct,unittest
from kwce.wiiroom_formats import decompress_lz11,compress_lz11_optimal
from kwce.wiiroom_schema import tree,problems

def schema():
    # MovieLink-like tree: root list 1..1 > ver uint 0..9999, linkinfo list 0..3 >
    # movieid str 1..4 (required), categid str 5..7. Nodes sit at 0x20+p from p=4.
    names=[b'MovieLink',b'ver',b'linkinfo',b'movieid',b'categid'];table=0xa4;offs=[]
    blob=b''
    for n in names:offs.append(table+len(blob));blob+=n+b'\0'
    nodes=[(0,offs[0],0x24,0,0,0,1,1),(3,offs[1],0,0x44,0,1<<24,0,9999),(0,offs[2],0x64,0,0,0,0,3),
           (2,offs[3],0,0x84,0,1<<24,1,4),(2,offs[4],0,0,0,0,5,7)]
    return b'HDPK001B'+bytes(0x1c)+b''.join(struct.pack('>8I',*row)for row in nodes)+blob

class WiiRoomTests(unittest.TestCase):
    def test_lz11_optimal_roundtrip(self):
        rng=random.Random(7)
        for data in [b'x',b'\0'*70000,bytes(range(256))*40,rng.randbytes(3000),b'abc'*5000+rng.randbytes(50)]:
            packed=compress_lz11_optimal(data);self.assertEqual(decompress_lz11(packed),data)
        self.assertLess(len(compress_lz11_optimal(b'\0'*70000)),40)

    def test_schema_counts_and_lengths(self):
        node=tree(schema())
        self.assertEqual([c['name']for c in node['children']],['ver','linkinfo'])
        self.assertEqual(problems(b'<MovieLink><ver>1</ver><linkinfo><movieid>1</movieid><categid>11111</categid></linkinfo></MovieLink>',node),[])
        found=problems(b'<MovieLink><ver>1</ver><linkinfo><movieid>1</movieid><categid>1</categid></linkinfo></MovieLink>',node)
        self.assertEqual(found,['MovieLink/linkinfo/categid: length 1 not in 5..7'])
        self.assertIn('MovieLink/linkinfo/movieid: missing',problems(b'<MovieLink><ver>1</ver><linkinfo></linkinfo></MovieLink>',node))

if __name__=='__main__':unittest.main()
