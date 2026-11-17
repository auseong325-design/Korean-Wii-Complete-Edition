"""Register user-provided discs locally, never print game bytes or dump reports.

Classification is a verified same-workspace move preserving original filenames.
No source under sd is accepted, no archive contents are uploaded or modified.
"""
import argparse,hashlib,json,shutil,struct,re,zlib
from pathlib import Path
from datetime import datetime,timezone
from audit_sd import ROOT,PRIVATE,sha256

GC_SIZE=1459978240

def inspect_iso(path):
    with path.open('rb') as f:
        header=f.read(0x460);f.seek(0x458);region=struct.unpack('>I',f.read(4))[0]
    if len(header)<0x460 or header[0x1c:0x20]!=bytes.fromhex('c2339f3d'):raise ValueError('Not a raw GameCube image')
    disc_id=header[:6].decode('ascii')
    if not disc_id.isalnum():raise ValueError('Invalid game ID')
    size=path.stat().st_size
    for off in (0x420,0x424):
        ptr=struct.unpack_from('>I',header,off)[0]
        if ptr<0x440 or ptr>=size:raise ValueError('DOL/FST offset out of image bounds')
    fst=struct.unpack_from('>I',header,0x424)[0];length=struct.unpack_from('>I',header,0x428)[0]
    if not length or fst+length>size:raise ValueError('FST outside image')
    return dict(disc_id=disc_id,disc_number=header[6],revision=header[7],region_code=region,
                platform='GameCube',region='Japan' if disc_id[3]=='J' and region==0 else 'other',
                full_raw_size=size==GC_SIZE,size=size,header_and_offsets_valid=True,
                retail_reference_hash_verified=False)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source',nargs='?',default='GALJ01.iso');ap.add_argument('--verify',action='store_true');args=ap.parse_args()
    if args.verify:
        result=json.loads((PRIVATE/'disc-catalog.json').read_text(encoding='utf-8'))
        for row in result['files']:
            p=Path(row['path'])
            if sha256(p)!=row['sha256'] or p.stat().st_size!=row['size'] or p.stat().st_mtime_ns!=row['mtime_ns']:
                raise SystemExit('Preserved test asset differs from catalog')
        image=next(Path(r['path']) for r in result['files'] if r['name'].endswith('.iso'))
        report=next(Path(r['path']) for r in result['files'] if r['name'].endswith('-dumpinfo.txt')).read_text(encoding='utf-8',errors='replace')
        expected={}
        for name,pattern in [('md5',r'(?im)^.*?\bMD5\s*:\s*([0-9a-f]{32})\s*$'),('sha1',r'(?im)^.*?\bSHA-?1\s*:\s*([0-9a-f]{40})\s*$'),('crc32',r'(?im)^.*?\bCRC-?32\s*:\s*([0-9a-f]{8})\s*$')]:
            found=re.search(pattern,report)
            if found:expected[name]=found.group(1).lower()
        md5=hashlib.md5();sha1=hashlib.sha1();crc=0
        if expected:
            with image.open('rb') as f:
                for block in iter(lambda:f.read(8*1024*1024),b''):
                    md5.update(block);sha1.update(block);crc=zlib.crc32(block,crc)
        computed=dict(md5=md5.hexdigest(),sha1=sha1.hexdigest(),crc32=f'{crc:08x}')
        matches={k:computed[k]==v for k,v in expected.items()}
        result['dump_report_checksum_matches']=matches
        (PRIVATE/'disc-catalog.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if not all(matches.values()):raise SystemExit('Dump report checksum mismatch')
        print(json.dumps(dict(file_hash_size_mtime_preserved=True,dump_report_checksum_matches=matches,external_reference_verification=False)));return
    source=(ROOT/args.source).resolve();destroot=(ROOT/'workspace/test-assets/gamecube').resolve()
    if not destroot.is_relative_to(ROOT/'workspace'):raise SystemExit('Classification destination escaped workspace')
    if not source.is_relative_to(ROOT) or source.is_relative_to(ROOT/'sd'):raise SystemExit('Only project-local non-SD inputs accepted')
    if source.is_symlink() or source.is_junction():raise SystemExit('No indirect inputs')
    meta=inspect_iso(source);target=destroot/meta['disc_id']
    if target.exists() and source.parent!=target:raise SystemExit('Destination exists; no overwrite')
    candidates=[source,source.with_suffix('.bca'),source.with_name(source.stem+'-dumpinfo.txt')]
    if any(not p.is_file() for p in candidates):raise SystemExit('Expected ISO, BCA and dumpinfo set')
    rows=[dict(name=p.name,original_path=str(p),size=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha256(p)) for p in candidates]
    target.mkdir(parents=True,exist_ok=True)
    for p,row in zip(candidates,rows):
        q=target/p.name
        if q!=p:
            if q.exists():raise SystemExit('Refusing overwrite')
            shutil.move(str(p),str(q))
        if sha256(q)!=row['sha256'] or q.stat().st_size!=row['size'] or q.stat().st_mtime_ns!=row['mtime_ns']:
            raise SystemExit('Classification preservation check failed')
        row['path']=str(q)
    result=dict(registered_utc=datetime.now(timezone.utc).isoformat(),asset=meta,
                user_provenance='User states original Japanese Super Smash Bros. Melee disc was self-dumped',files=rows,
                policies=dict(local_only=True,do_not_patch_dump=True,game_execution_not_yet_tested=True))
    PRIVATE.mkdir(parents=True,exist_ok=True)
    (PRIVATE/'disc-catalog.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(asset=meta,classified_files=len(rows),all_hash_size_mtime_preserved=True)))

if __name__=='__main__':main()
