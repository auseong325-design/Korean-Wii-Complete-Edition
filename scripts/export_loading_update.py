"""Frozen two-channel update; both existing Room entry points use identical WADs."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.hardware import hardware_wad
from kwce.channel_ipc_deadline import patch as patch_ipc
from kwce.channel_socket_startup import patch as patch_socket
from kwce.wiiroom_formats import decompress_lz11

OUT=ROOT/'workspace/hardware/kwce-loading-news20-room51-v1'
ZIP=OUT.with_suffix('.zip');MANIFEST='KWCE-LOADING-manifest.json';README='KWCE-LATEST-README-ko.txt'
ALLOWED={'kwce/news/korean.wad','kwce/wiiroom/korean.wad','kwce/packages.txt',
 'apps/kwce-wiiroom-installer/boot.dol','apps/kwce-wiiroom-installer/meta.xml',
 'apps/kwce-wiiroom-installer/icon.png','kwce-wiiroom/packages.txt',
 'kwce-wiiroom/wiiroom/korean.wad',README,MANIFEST}

def sha(data):return hashlib.sha256(data).hexdigest()

def verify():
    m=json.loads((OUT/MANIFEST).read_text(encoding='utf-8'))
    if m['kind']!='loading-two-channel-update-v1' or m['revisions']!={'news':20,'wiiroom':51} or m['hardware_success_verified']:
        raise ValueError('Loading update scope differs')
    if {r['path']for r in m['files']}!=ALLOWED-{MANIFEST}:raise ValueError('Loading file allowlist')
    if {p.relative_to(OUT).as_posix()for p in OUT.rglob('*')if p.is_file()}!=ALLOWED:raise ValueError('Unexpected loading payload')
    for r in m['files']:
        p=OUT/r['path']
        if p.is_symlink()or p.is_junction()or not p.resolve().is_relative_to(OUT.resolve()):raise ValueError('Indirect loading source')
        b=p.read_bytes()
        if len(b)!=r['bytes']or sha(b)!=r['sha256']:raise ValueError('Loading payload differs')
    if (OUT/'kwce/wiiroom/korean.wad').read_bytes()!=(OUT/'kwce-wiiroom/wiiroom/korean.wad').read_bytes():raise ValueError('Room entry points differ')
    with zipfile.ZipFile(ZIP)as z:
        if len(z.infolist())!=len(ALLOWED)or set(z.namelist())!=ALLOWED or z.testzip():raise ValueError('Loading ZIP/CRC')
        for name in ALLOWED:
            if z.read(name)!=(OUT/name).read_bytes():raise ValueError('Loading ZIP bytes')
    return m

def sd_files(package):
    p=Path(package)
    if p.name!=OUT.name or p.resolve()!=OUT.resolve():raise ValueError('Only current reviewed loading package')
    return verify(),[(OUT/name,name)for name in sorted(ALLOWED)]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    if args.check:verify();print('PASS: News20/Room51 ten-file ZIP, hashes/CRC, both Room paths identical');return
    if OUT.exists()or ZIP.exists():raise ValueError('Existing numbered loading package preserved')
    from export_wiiroom_update import verify as verify_room47,OUT as ROOM47
    verify_room47()
    files={};records={};lib=load_library()
    for channel,oldv,newv,name,original in [('news',16,20,'news-ko-personal.wad','news-usa-wiilink-archive.wad'),
          ('wiiroom',47,51,'wiiroom-ko-local-test.wad','wiiroom-english-wiilink-archive.wad')]:
        base=ROOT/'workspace/channels'/channel;parent=lib.title.Title();new=lib.title.Title()
        parent.load_wad((base/f'build-v{oldv}'/name).read_bytes());raw=(base/f'build-v{newv}'/name).read_bytes()
        meta=json.loads((base/f'build-v{newv}/build-manifest.json').read_text(encoding='utf-8'))
        if meta.get('diagnostic_only')or meta.get('hardware_allowed')is False or not meta.get('ipc_deadline'):
            raise ValueError('Diagnostic or unreviewed loading artifact')
        expected=meta['wads']['personal']['sha256']if channel=='news'else meta['wad_sha256']
        if sha(raw)!=expected:raise ValueError('Loading source hash')
        new.load_wad(raw);count=12 if channel=='news'else 16
        if [i for i in range(count)if parent.get_content_by_index(i)!=new.get_content_by_index(i)]!=[1]:raise ValueError('Loading changed content boundary')
        oldexe=parent.get_content_by_index(1);exe=new.get_content_by_index(1)
        if channel=='wiiroom':oldexe,exe=decompress_lz11(oldexe),decompress_lz11(exe)
        if patch_ipc(patch_socket(oldexe,channel)[0],channel)[0]!=exe:raise ValueError('Loading patch reproduction differs')
        wad,checks=hardware_wad(raw,(base/'originals'/original).read_bytes())
        files[f'kwce/{channel}/korean.wad']=wad
        if channel=='wiiroom':files['kwce-wiiroom/wiiroom/korean.wad']=wad
        records[channel]=dict(source_sha256=sha(raw),hardware_checks=checks,changed_contents=[1])
    listing=(ROOT/'workspace/hardware/kwce-channels-v1/kwce/packages.txt').read_bytes()
    for old,new in [(b'News r15 (retest)',b'News r20 (IPC deadline)'),(b'Wii Room r23',b'Wii Room r51 (IPC deadline)')]:
        if listing.count(old)!=1:raise ValueError('Frozen common list anchor')
        listing=listing.replace(old,new)
    files['kwce/packages.txt']=listing
    for name in ('boot.dol','meta.xml','icon.png'):
        b=(ROOM47/'apps/kwce-wiiroom-installer'/name).read_bytes()
        if name=='meta.xml':b=b.replace(b'r47',b'r51')
        files['apps/kwce-wiiroom-installer/'+name]=b
    files['kwce-wiiroom/packages.txt']=(ROOM47/'kwce-wiiroom/packages.txt').read_bytes().replace(b'Wii Room r47 (KOR boot fix)',b'Wii Room r51 (IPC deadline)')
    files[README]=(ROOT/'docs/hardware/LOADING-NEWS20-ROOM51-README-ko.txt').read_bytes()
    record=dict(kind='loading-two-channel-update-v1',revisions={'news':20,'wiiroom':51},
        hardware_success_verified=False,system_writer_linked=False,prerequisite='existing Wii Recent Channels v1 + Room r47 SD',
        channels=records,files=[dict(path=n,bytes=len(b),sha256=sha(b))for n,b in sorted(files.items())])
    files[MANIFEST]=(json.dumps(record,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    OUT.mkdir(parents=True)
    for name,b in files.items():p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    with zipfile.ZipFile(ZIP,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for name,b in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,10,26,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
    verify();print('PASS: News20/Room51 existing-SD update created; no SD write')

if __name__=='__main__':main()
