"""Display each native banner caption offline; diagnostic builds only.

The ordinary missing-update presenter is used to inspect the original other
caption's geometry, font and material. This does not simulate a live update.
"""
import argparse,hashlib,json,struct,sys
from pathlib import Path
from audit_sd import ROOT,sha256
sys.path.insert(0,str(ROOT))
from kwce.channels import ChannelArchive,load_library,layout_sections,textbox,rebuild_layout,compress_lz10


def main():
    ap=argparse.ArgumentParser();ap.add_argument('case',choices=['intro','regional']);args=ap.parse_args()
    revision=96 if args.case=='intro'else 97;out=ROOT/f'workspace/channels/forecast/build-v{revision}'
    if out.exists():raise SystemExit('Existing diagnostic preserved')
    source=ROOT/'workspace/channels/forecast/build-v95';meta=json.loads((source/'build-manifest.json').read_text(encoding='utf-8'))
    wad=source/'forecast-ko-personal-test.wad'
    if sha256(wad)!=meta['wad_sha256']:raise ValueError('Normal source differs')
    title=load_library().title.Title();title.load_wad(wad.read_bytes())
    from libWiiPy.archive import decompress_lz77
    content=title.get_content_by_index(0);outer=ChannelArchive(content[0x640:]);wrapped=outer.get('meta/banner.bin')
    if wrapped[:4]!=b'IMD5'or wrapped[16:32]!=hashlib.md5(wrapped[32:]).digest():raise ValueError('Banner integrity')
    banner=ChannelArchive(decompress_lz77(wrapped[32:]));changes=0
    for path in [n for n in banner.files if n.endswith('.brlyt')]:
        data=banner.get(path);sections=layout_sections(data)
        panes={textbox(s)[0]:(i,s)for i,s in enumerate(sections)if textbox(s)}
        if 'textT1ENG'not in panes:continue
        _,original=panes['textT0ENG'if args.case=='intro'else'textT2ENG'];at,target=panes['textT1ENG']
        edited=bytearray(original);edited[12:28]=target[12:28];edited[8]=target[8];edited[10]=target[10]
        sections[at]=bytes(edited);banner=ChannelArchive(banner.replace(path,rebuild_layout(data,sections)));changes+=1
    if changes!=1:raise ValueError('Native banner caption identity')
    raw=banner.compact();payload=b'LZ77'+compress_lz10(raw)
    if decompress_lz77(payload)!=raw:raise ValueError('Banner roundtrip')
    packed=b'IMD5'+len(payload).to_bytes(4,'big')+bytes(8)+hashlib.md5(payload).digest()+payload
    outer=ChannelArchive(outer.replace('meta/banner.bin',packed));prefix=bytearray(content[:0x640]);struct.pack_into('>I',prefix,0x90,len(raw))
    prefix[0x630:0x640]=bytes(16);prefix[0x630:0x640]=hashlib.md5(prefix[0x40:0x640]).digest()
    title.set_content(bytes(prefix)+outer.compact(),0);out.mkdir();wad=out/'forecast-ko-personal-test.wad';wad.write_bytes(title.dump_wad())
    meta.update(revision=revision,source_build=95,wad_sha256=sha256(wad),visual_diagnostic_only=True,banner_caption_review=args.case,
        actual_live_banner_state=False)
    (out/'build-manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared native banner caption diagnostic',args.case,revision)


if __name__=='__main__':main()
