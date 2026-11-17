"""Extract the locally authored DVD channel thumbnail for an offline native prototype."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,ChannelArchive
from kwce.formats import U8
p=argparse.ArgumentParser();p.add_argument('--revision',type=int,required=True);p.add_argument('--wad',type=int,default=31);a=p.parse_args()
out=ROOT/f'workspace/experiments/dvd-native-icon-v{a.revision}'
if out.exists():raise SystemExit('Existing numbered icon preserved')
source=ROOT/f'workspace/channels/dvd-player/wad-v{a.wad}/dvd-player.wad';metadata=json.loads(source.with_name('wad-manifest.json').read_text(encoding='utf8'))
raw=source.read_bytes()
if hashlib.sha256(raw).hexdigest()!=metadata['wad_sha256']:raise ValueError('Source differs from manifest')
lib=load_library();from libWiiPy.archive import decompress_lz77
t=lib.title.Title();t.load_wad(raw);outer=U8(t.get_content_by_index(0)[0x640:]);entries=[n for n in outer.files if n.endswith('/icon.bin')]
if len(entries)!=1:raise ValueError('Expected one icon')
wrapped=outer.get(entries[0])
if wrapped[:4]!=b'IMD5':raise ValueError('Expected IMD5 icon')
icon=decompress_lz77(wrapped[32:]);arc=ChannelArchive(icon)
if not any(n.endswith('/icon.brlyt') for n in arc.files) or len(icon)>0x19000:raise ValueError('Invalid icon archive')
out.mkdir();(out/'icon.arc').write_bytes(icon);(out/'manifest.json').write_text(json.dumps({'schema':1,'source_wad':a.wad,'source_sha256':metadata['wad_sha256'],'bytes':len(icon),'sha256':hashlib.sha256(icon).hexdigest()},indent=2)+'\n')
print(f'PASS native icon v{a.revision}: {len(icon)} bytes')

