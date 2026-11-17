"""Build a private DVD-Video ISO from a user ZIP without transcoding its files."""
import argparse,hashlib,json,re,stat,struct,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from make_dvd_test_disc import tool

def digest(path):
    h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def dvd_entries(archive):
    result={};total=0
    if len(archive.infolist())>512:raise ValueError('DVD ZIP entry limit')
    for entry in archive.infolist():
        name=entry.filename.replace('\\','/');parts=PurePosixPath(name).parts
        if name.startswith('/')or ':'in name or '..'in parts or stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Unsafe DVD ZIP entry')
        if entry.is_dir():continue
        if entry.flag_bits&1:raise ValueError('Encrypted ZIP unsupported')
        base=PurePosixPath(name).name.upper()
        if not re.fullmatch(r'(VIDEO_TS|VTS_[0-9]{2}_[0-9])[.](IFO|BUP|VOB)',base):raise ValueError('Non-DVD file in ZIP')
        if base in result:raise ValueError('Duplicate DVD filename')
        total+=entry.file_size
        if not 0<entry.file_size<=1024**3 or total>8*1024**3:raise ValueError('DVD ZIP size limit')
        result[base]=entry
    if not {'VIDEO_TS.IFO','VIDEO_TS.BUP'}<=result.keys():raise ValueError('DVD manager files missing')
    return result

def validate_folder(folder):
    rows=[];scrambled=0
    for path in sorted(folder.iterdir()):
        size=path.stat().st_size
        if size%2048:raise ValueError('DVD sector alignment differs')
        if path.suffix=='.IFO':
            with path.open('rb')as f:magic=f.read(12)
            if magic!=(b'DVDVIDEO-VMG'if path.name=='VIDEO_TS.IFO'else b'DVDVIDEO-VTS'):raise ValueError('DVD IFO identity differs')
            backup=path.with_suffix('.BUP')
            if not backup.is_file()or digest(path)!=digest(backup):raise ValueError('DVD IFO backup differs')
            if path.name!='VIDEO_TS.IFO'and not(folder/(path.stem[:6]+'_1.VOB')).is_file():raise ValueError('DVD title VOB missing')
        if path.suffix=='.VOB':
            with path.open('rb')as f:
                for sector in iter(lambda:f.read(2048),b''):
                    if sector[:4]==b'\0\0\x01\xba'and sector[0x14]&0x30:scrambled+=1
        rows.append(dict(name=path.name,size=size,sha256=digest(path)))
    if not any(r['name'].startswith('VTS_')and r['name'].endswith('_1.VOB')for r in rows):raise ValueError('DVD has no title')
    return rows,scrambled

def verify_iso(iso,rows):
    expected={r['name']:r for r in rows};found={}
    with iso.open('rb')as f:
        f.seek(16*2048);pvd=f.read(2048)
        if pvd[:7]!=b'\x01CD001\x01':raise ValueError('ISO9660 primary volume missing')
        def directory(record):
            sector=struct.unpack_from('<I',record,2)[0];size=struct.unpack_from('<I',record,10)[0]
            if size>128*1024 or sector*2048+size>iso.stat().st_size:raise ValueError('ISO directory bounds')
            f.seek(sector*2048);data=f.read(size);items={};at=0
            while at<len(data):
                length=data[at]
                if not length:at=(at//2048+1)*2048;continue
                r=data[at:at+length]
                if length<34 or len(r)!=length:raise ValueError('ISO directory record bounds')
                n=r[33:33+r[32]]
                if n not in(b'\0',b'\x01'):items[n.decode('ascii').split(';')[0]]=r
                at+=length
            return items
        root=directory(pvd[156:190]);files=directory(root['VIDEO_TS'])
        for name,row in expected.items():
            r=files[name];sector=struct.unpack_from('<I',r,2)[0];size=struct.unpack_from('<I',r,10)[0]
            if size!=row['size']or sector*2048+size>iso.stat().st_size:raise ValueError('ISO DVD file bounds')
            f.seek(sector*2048);h=hashlib.sha256();left=size
            while left:
                block=f.read(min(left,1024*1024))
                if not block:raise ValueError('Truncated ISO DVD file')
                h.update(block);left-=len(block)
            if h.hexdigest()!=row['sha256']:raise ValueError('DVD file changed inside ISO')
            found[name]=dict(size=size,sha256=h.hexdigest())
        # UDF bridge volume recognition sequence; ISO files are verified above.
        f.seek(16*2048);udf=b'NSR02'in f.read(32*2048)or b'NSR03'in pvd
        if not udf:raise ValueError('UDF bridge marker missing')
    return found

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--zip',type=Path,required=True);ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
    source=args.zip.resolve();before=(source.stat().st_size,source.stat().st_mtime_ns,digest(source));out=ROOT/f'workspace/private/dvd-user-test-v{args.revision}'
    if args.revision<1 or out.exists():raise SystemExit('Numbered private DVD test asset preserved')
    with zipfile.ZipFile(source)as archive:
        entries=dvd_entries(archive);out.mkdir(parents=True);folder=out/'DVD/VIDEO_TS';folder.mkdir(parents=True)
        for name,entry in entries.items():
            with archive.open(entry)as src,(folder/name).open('xb')as dst:
                for block in iter(lambda:src.read(1024*1024),b''):dst.write(block)
    rows,scrambled=validate_folder(folder);iso=out/'test-disc.iso';mkisofs=Path(tool('mkisofs'));ffprobe=Path(tool('ffprobe'));ffmpeg=Path(tool('ffmpeg'))
    command=[str(mkisofs),'-dvd-video','-udf','-iso-level','1','-V','KWCE_USER_DVD','-o',str(iso),str(folder.parent)]
    result=subprocess.run(command,capture_output=True);(out/'iso-authoring.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:raise SystemExit('DVD ISO authoring failed; private log preserved')
    verified=verify_iso(iso,rows);probe=[];decode=[]
    for path in sorted(folder.glob('VTS_*_1.VOB')):
        result=subprocess.run([str(ffprobe),'-v','error','-show_entries','stream=codec_type,codec_name,width,height,sample_rate,channels:format=duration','-of','json',str(path)],capture_output=True)
        if result.returncode:raise SystemExit('DVD probe failed')
        probe.append(json.loads(result.stdout))
        result=subprocess.run([str(ffmpeg),'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(path),'-map','0:v:0','-map','0:a?','-f','null','-'],capture_output=True)
        (out/(path.stem+'-decode.log')).write_bytes(result.stderr);decode.append(result.returncode)
    after=(source.stat().st_size,source.stat().st_mtime_ns,digest(source))
    if before!=after:raise ValueError('Source ZIP changed')
    record=dict(revision=args.revision,user_provided=True,synthetic=False,source_zip=str(source),source_size=before[0],source_mtime_ns=before[1],source_sha256=before[2],source_unchanged=True,iso_file='test-disc.iso',iso_sha256=digest(iso),iso_size=iso.stat().st_size,iso9660_files_verified=len(verified),udf_bridge=True,transcoded=False,css_scrambling_marked_sectors=scrambled,probe=probe,decode_exit_codes=decode,files=rows,tools={p.name:digest(p)for p in [mkisofs,ffprobe,ffmpeg]})
    (out/'import-manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(revision=args.revision,dvd_files=len(rows),iso_bytes=record['iso_size'],source_unchanged=True,all_files_byte_identical=True,css_scrambling_marked_sectors=scrambled,probe=probe,decode_exit_codes=decode),ensure_ascii=False))
if __name__=='__main__':main()
