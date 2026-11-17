"""Build local-only patched resources/profile. Never produces or installs WADs."""
import argparse,hashlib,json,shutil,struct,subprocess
from pathlib import Path
from .patches import patch_resources,gc_detection_prototype

ROOT=Path(__file__).resolve().parents[1]
PROFILE='gc-visual-v1-user'

def digest(data):return hashlib.sha256(data).hexdigest()

def build():
    running=subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True)
    if 'dolphin.exe' in running.stdout.lower():raise SystemExit('Close Dolphin before profile creation')
    out=ROOT/'workspace/experiments/gc-restoration-v1';profile=ROOT/'workspace/dolphin'/PROFILE
    if out.exists() or profile.exists():raise SystemExit('Output exists: use --verify. No overwrites allowed')
    baseline=ROOT/'workspace/extracted-system/nand-current/title/00000001/00000002/content'
    tmd=bytearray((baseline/'title.tmd').read_bytes());sig=int.from_bytes(tmd[:4],'big')
    if sig!=0x10001:raise ValueError('Unexpected TMD container')
    base=0x140;version,count=struct.unpack_from('>HH',tmd,base+0x9c)
    if version!=518:raise ValueError('43K v518 required')
    record=None
    for i in range(count):
        o=base+0xa4+36*i;cid,index,kind,size=struct.unpack_from('>IHHQ',tmd,o)
        if index==1:
            if kind&0x8000:raise ValueError('Expected unshared 43K resource')
            record=o;name=f'{cid:08x}.app';break
    if record is None:raise ValueError('No resource content index1')
    original=(baseline/name).read_bytes()
    if hashlib.sha1(original).digest()!=tmd[record+16:record+36]:raise ValueError('Original resource TMD mismatch')
    modified,detail=patch_resources(original)
    dol=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    executable,prototype=gc_detection_prototype(dol)
    # All preparation and guard checks must succeed before output mutations.
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from launch_dolphin import validate
    source=validate()
    out.mkdir(parents=True)
    (out/'menu-resource.app').write_bytes(modified)
    (out/'gc-detection-prototype.dol').write_bytes(executable)
    shutil.copytree(source,profile)
    content=profile/'Wii/title/00000001/00000002/content'
    # Retain the experiment profile's original TMD/boot/Priiloader arrangement.
    target_tmd=bytearray((content/'title.tmd').read_bytes())
    if target_tmd[record:record+8]!=tmd[record:record+8]:raise ValueError('Experimental TMD content mapping differs')
    struct.pack_into('>Q',target_tmd,record+8,len(modified));target_tmd[record+16:record+36]=hashlib.sha1(modified).digest()
    (content/name).write_bytes(modified);(content/'title.tmd').write_bytes(target_tmd)
    changed={'Wii/title/00000001/00000002/content/'+name,'Wii/title/00000001/00000002/content/title.tmd'}
    before={p.relative_to(source).as_posix():p for p in source.rglob('*') if p.is_file()}
    after={p.relative_to(profile).as_posix():p for p in profile.rglob('*') if p.is_file()}
    differences={p for p in before if digest(before[p].read_bytes())!=digest(after[p].read_bytes())}
    if before.keys()!=after.keys() or differences!=changed:raise ValueError('Unexpected experimental profile differences')
    validate(PROFILE)
    meta=dict(version='43K',profile=PROFILE,source_profile='experiment-user',resource_input_sha256=digest(original),
              artifact_files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p.read_bytes())) for p in [out/'menu-resource.app',out/'gc-detection-prototype.dol',content/name,content/'title.tmd']],
              resources=detail,executable_prototype=prototype,profile_changed_files=sorted(changed),
              original_TMD_signature_invalid_after_local_edit=True,WAD_created=False,real_console_writes=False,
              game_executed=False,GUI_verified=False)
    (out/'build-manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(dict(profile=PROFILE,resources=detail,executable_prototype=prototype,changed_profile_files=len(changed),local_only=True)))

def verify():
    out=ROOT/'workspace/experiments/gc-restoration-v1'
    meta=json.loads((out/'build-manifest.json').read_text(encoding='utf-8'))
    for item in meta['artifact_files']:
        p=(ROOT/item['path']).resolve()
        if not p.is_relative_to(ROOT/'workspace'):raise ValueError('Artifact escaped workspace')
        if digest(p.read_bytes())!=item['sha256']:raise ValueError('Artifact differs from build manifest')
    print('PASS: local patch artifacts and experimental profile content hashes')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--verify',action='store_true');args=ap.parse_args()
    verify() if args.verify else build()
