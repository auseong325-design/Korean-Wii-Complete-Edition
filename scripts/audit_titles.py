"""Read local TMDs/WAD headers. Shared contents resolved through content.map.

Outputs only non-secret counts; exact inventories remain in ignored workspace.
TMD SHA-1 checks are content consistency checks, not signature verification.
"""
import hashlib, json, struct
from collections import Counter
from audit_sd import ROOT, SD, PRIVATE

BASES={0x10000:0x240,0x10001:0x140,0x10002:0x80}

def main():
    base=ROOT/'workspace/extracted-system/nand-current'
    b=(base/'shared1/content.map').read_bytes()
    if len(b)%28:raise ValueError('Invalid shared content.map size')
    shared={b[i+8:i+28].hex():b[i:i+8].decode('ascii') for i in range(0,len(b),28)}
    rows=[];tmd_count=0
    for p in base.glob('title/*/*/content/title.tmd'):
        b=p.read_bytes();o=BASES.get(int.from_bytes(b[:4],'big'))
        if o is None:raise ValueError('Unknown TMD signature container')
        tmd_count+=1;n=int.from_bytes(b[o+0x9e:o+0xa0],'big');tid=b[o+0x4c:o+0x54].hex()
        for i in range(n):
            cid,idx,typ,size=struct.unpack_from('>IHHQ',b,o+0xa4+i*36)
            expected=b[o+0xa4+i*36+16:o+0xa4+i*36+36].hex()
            p2=base/'shared1'/(shared.get(expected,'missing')+'.app') if typ&0x8000 else p.parent/f'{cid:08x}.app'
            rows.append(dict(title_id=tid,content_id=f'{cid:08x}',index=idx,shared=bool(typ&0x8000),present=p2.exists(),size_ok=p2.exists() and p2.stat().st_size==size,sha1_matches=p2.exists() and hashlib.sha1(p2.read_bytes()).hexdigest()==expected))
    (PRIVATE/'title-content-audit.json').write_text(json.dumps(rows,indent=2))
    wads=[];errors=[]
    for p in SD.rglob('*'):
        if p.suffix.lower()!='.wad' or not p.is_file():continue
        try:
            with p.open('rb') as f:
                head,typ,pad,cert,unused,tik,tmd,data,foot=struct.unpack('>IHH6I',f.read(32))
                align=lambda n:(n+63)&~63
                pos=align(head)+align(cert)+align(unused)+align(tik)
                if pos+tmd>p.stat().st_size:raise ValueError('WAD section bounds')
                f.seek(pos);b=f.read(tmd)
            o=BASES.get(int.from_bytes(b[:4],'big'))
            if o is None or len(b)<o+0xa4:raise ValueError('WAD TMD missing')
            wads.append(dict(path=p.relative_to(ROOT).as_posix(),title_id=b[o+0x4c:o+0x54].hex(),version=int.from_bytes(b[o+0x9c:o+0x9e],'big')))
        except (ValueError,struct.error) as e:errors.append(dict(path=p.relative_to(ROOT).as_posix(),error=str(e)))
    (PRIVATE/'wad-inventory.json').write_text(json.dumps(dict(wads=wads,errors=errors),indent=2))
    summary=dict(tmds=tmd_count,content_records=len(rows),missing_categories=dict(Counter(x['title_id'][:8] for x in rows if not x['present'])),
                 missing=sum(not x['present'] for x in rows),present_hash_mismatch=[x for x in rows if x['present'] and not x['sha1_matches']],
                 wad_count=len(wads),wad_parse_errors=len(errors),system_menu_wads=sum(x['title_id']=='0000000100000002' for x in wads))
    (PRIVATE/'title-audit-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))

if __name__=='__main__':main()
