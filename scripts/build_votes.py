"""First metadata-only Votes build; preserves executable and resource bytes."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library,sha256

def main():
    base=ROOT/'workspace/channels/votes';out=base/'build-v1'
    if out.exists():raise SystemExit('Existing build preserved')
    source=base/'originals/votes-usa-wiilink-archive.wad'
    records=json.loads((source.parent/'acquisition.json').read_text())['files']
    row=next(r for r in records if r['alias']==source.name)
    if sha256(source.read_bytes())!=row['sha256']:raise ValueError('Original changed')
    lib=load_library();title=lib.title.Title();title.load_wad(source.read_bytes())
    original=[title.get_content_by_index(i)for i in range(len(title.tmd.content_records))]
    data=bytearray(original[0]);assert data[0x80:0x84]==b'IMET'
    for lang in range(10):
        at=0x40+0x5c+84*lang;label='모두의 투표 채널'.encode('utf-16-be');data[at:at+84]=label+bytes(84-len(label))
    data[0x630:0x640]=bytes(16);data[0x630:0x640]=hashlib.md5(data[0x40:0x640]).digest()
    title.set_content(bytes(data),0);title.tmd.region=4;wad=title.dump_wad()
    check=lib.title.Title();check.load_wad(wad)
    changed=[i for i in range(len(original))if check.get_content_by_index(i)!=original[i]]
    assert changed==[0] and check.get_content_by_index(0)[0x640:]==original[0][0x640:]
    out.mkdir();(out/'votes-ko-metadata-test.wad').write_bytes(wad)
    report=dict(revision=1,title_id=title.tmd.title_id,wad_sha256=sha256(wad),source_sha256=row['sha256'],changed_contents=changed,scope='IMET Korean name only; body, bitmap banner and service not localized',installed=False,runtime_verified=False)
    (out/'build-manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main()
