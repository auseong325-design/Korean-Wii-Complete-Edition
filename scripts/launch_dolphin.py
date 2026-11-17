"""Launch only the sanitized project profile; never an authentic baseline.

No arbitrary --exec/--movie arguments: old savestates contain real WC24 data.
Use --menu to launch the validated Wii Menu. No channels or service actions.
"""
import argparse, os, socket, struct, subprocess,json,hashlib,sys
from pathlib import Path
from urllib.parse import urlparse
from audit_sd import ROOT

def detach_kwargs():
    """Std handles for a long-lived helper (Dolphin, AppContainerRunner).

    A helper that inherits the caller's stdout pipe keeps it open until Dolphin exits, so a caller that
    reads the pipe (PowerShell `| Select-Object`) blocks for as long as Dolphin runs (~90 min).
    NUL handles end that; launchers that already log to a file do not need this.
    """
    return dict(stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True)

def popen_detached(cmd,**kw):
    return subprocess.Popen(cmd,**detach_kwargs(),**kw)

def korean_locale(wii):
    b=(wii/'shared2/sys/SYSCONF').read_bytes()
    if b[:4]!=b'SCv0':raise ValueError('Invalid SYSCONF header')
    values={}
    for i in range(int.from_bytes(b[4:6],'big')):
        off=int.from_bytes(b[6+2*i:8+2*i],'big');head=b[off];length=(head&31)+1
        name=b[off+1:off+1+length].decode('ascii');start=off+1+length
        if name not in ('IPL.LNG','IPL.SADR'):continue
        if head>>5==1:start+=2
        elif head>>5==2:start+=1
        values[name]=b[start]
    return values=={'IPL.LNG':9,'IPL.SADR':136}

NATIVE_PROFILES={f'gc-native-v{rev}-user':f'workspace/sandbox/gc-v{rev}' for rev in (2,3,4,5,6,7,8,9)}
# v7 = v6 runtime + animated DVD disc model resource (kwce.disk_dvd_anim).
# v8 = v7 + disc channel DVD player hook (kwce.dvd_disc_hook) + DVD player channel in the NAND.
# v9 = v6 + GameCube-only disc channel: original two-disc layout names (kwce.gc_disc_layout), no DVD.
V6_FAMILY=('gc-native-v6-user','gc-native-v7-user','gc-native-v8-user','gc-native-v9-user')
PROFILES=('experiment-user','gc-visual-v1-user',*NATIVE_PROFILES)

def user_path(profile):
    if profile not in PROFILES:raise SystemExit('Unsupported project profile')
    native=profile in NATIVE_PROFILES;runtime=ROOT/NATIVE_PROFILES[profile] if native else None
    user=runtime/'user' if native else ROOT/'workspace/dolphin'/profile
    allowed=runtime if native else ROOT/'workspace/dolphin'
    for part in [user,*user.parents]:
        if part==ROOT.parent:break
        if part.is_symlink() or part.is_junction():raise SystemExit('Indirect project profile refused')
    if not user.resolve().is_relative_to(allowed.resolve()):raise SystemExit('Profile escaped project')
    return user

def validate_native_runtime(profile):
    """No personal paths/devices or arbitrary disc are accepted by this mode."""
    import configparser
    user=user_path(profile);runtime=user.parent
    for p in runtime.rglob('*'):
        if p.is_symlink() or p.is_junction():raise SystemExit('Indirect sandbox content refused')
    c=configparser.ConfigParser(strict=False);c.read(user/'Config/Dolphin.ini',encoding='utf-8-sig')
    core=c['Core']
    for key in ['SerialPort1','SerialPort2']:
        if core.get(key,'255')!='255':raise SystemExit('GC network devices refused')
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:
        if core.get(key,'False').lower()!='false':raise SystemExit('Wii SD access refused in native GC experiment')
    for section in c.sections():
        for key,value in c[section].items():
            if (key.lower().endswith(('path','pathoverride')) or key.lower() in ['nandroot','dump','load']) and value.strip():
                if not Path(value).resolve().is_relative_to(user.resolve()):raise SystemExit('Sandbox profile contains an outside path')
    iso=core.get('DefaultISO','').strip()
    if iso or profile in ['gc-native-v5-user',*V6_FAMILY]:
        expected=runtime/'disc/GALJ01.iso'
        if Path(iso).resolve()!=expected.resolve():raise SystemExit('Only the staged local test disc is permitted')
        from audit_sd import PRIVATE,sha256
        catalog=json.loads((PRIVATE/'disc-catalog.json').read_text(encoding='utf-8'))
        row=next(r for r in catalog['files'] if r['name']=='GALJ01.iso')
        if sha256(expected)!=row['sha256']:raise SystemExit('Staged disc does not match catalog')
    exe=runtime/'Dolphin-x64/Dolphin.exe'
    lock=json.loads((ROOT/'configs/dolphin.lock.json').read_text(encoding='utf-8'))
    from audit_sd import sha256
    expected=lock['executable_sha256']
    if profile in ['gc-native-v5-user',*V6_FAMILY]:
        sys.path.insert(0,str(ROOT))
        from kwce.dolphin_gc_fix import patch_mios_ipc
        modified,record=patch_mios_ipc((ROOT/'tools/dolphin-2609a/Dolphin-x64/Dolphin.exe').read_bytes())
        if json.loads((ROOT/'configs/gc-runtime.lock.json').read_text())!=record:raise SystemExit('GC runtime derivative lock mismatch')
        expected=record['output_sha256']
        if profile in V6_FAMILY:
            from kwce.dolphin_fst_retry import patch_fst_retry
            modified,retry=patch_fst_retry(modified)
            if retry!=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text()):raise SystemExit('FST runtime derivative lock mismatch')
            expected=retry['output_sha256']
        from kwce.gc_native import patch_gc_native
        import hashlib
        menu,_=patch_gc_native((ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes(),japanese_cards=True,japanese_comments=True)
        if profile=='gc-native-v8-user':
            from kwce.dvd_disc_hook import patch_dvd_hook
            menu,_=patch_dvd_hook(menu)
        if profile=='gc-native-v9-user':
            from kwce.gc_disc_layout import patch_gc_only_layout
            menu,_=patch_gc_only_layout(menu,require_original=False)
        content=user/'Wii/title/00000001/00000002/content';tmd=(content/'title.tmd').read_bytes()
        matched=False
        for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
            at=0x1e4+36*i;cid,index,kind,size=struct.unpack_from('>IHHQ',tmd,at)
            if index!=6:continue
            if (content/f'{cid:08x}.app').read_bytes()!=menu or size!=len(menu) or tmd[at+16:at+36]!=hashlib.sha1(menu).digest():raise SystemExit('GC v5 menu derivative mismatch')
            matched=True
        if not matched:raise SystemExit('GC v5 menu content missing')
        if profile in V6_FAMILY:
            from kwce.gc_header import patch_gc_header
            from kwce.dolphin_fst import inspect_fst
            resource,_=patch_gc_header((ROOT/'workspace/experiments/gc-native-v4/menu-resource.app').read_bytes())
            if profile in ('gc-native-v7-user','gc-native-v8-user'):
                from kwce.disk_dvd_anim import patch_dvd_animation
                resource,_=patch_dvd_animation(resource)
            matched=False
            for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
                at=0x1e4+36*i;cid,index,kind,size=struct.unpack_from('>IHHQ',tmd,at)
                if index!=1:continue
                if (content/f'{cid:08x}.app').read_bytes()!=resource or size!=len(resource) or tmd[at+16:at+36]!=hashlib.sha1(resource).digest():raise SystemExit('GC v6/v7 resource derivative mismatch')
                matched=True
            if not matched:raise SystemExit('GC v6 resource missing')
            inspect_fst((user/'Wii/fst.bin').read_bytes())
            if (user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending FST transaction requires local diagnosis before launch')
    if sha256(exe)!=expected:raise SystemExit('Dolphin executable differs from approved runtime hash')
    bindir=ROOT/(f'tools/gc-sandbox/v{profile.split("-v")[1].split("-")[0]}/bin' if profile in V6_FAMILY[1:] else 'tools/gc-sandbox/v6/bin' if profile in V6_FAMILY else 'tools/gc-sandbox/bin')
    build=json.loads((bindir/'helper-build.json').read_text(encoding='utf-8'))
    for row in build['files']:
        if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('Sandbox helper differs from compiled manifest')
    if sha256(runtime/'NetProbe.exe')!=build['probe_sha256']:raise SystemExit('Sandbox probe differs from compiled manifest')
    return runtime

def validate(profile='experiment-user'):
    user=user_path(profile);wii=user/'Wii'
    if not korean_locale(wii):raise SystemExit('Refusing changed Korean language/country')
    if (wii/'keys.bin').exists() or list(wii.glob('*.pem')):
        raise SystemExit('Refusing profile containing key container/client certificates')
    wc=wii/'shared2/wc24';b=(wc/'nwc24msg.cfg').read_bytes()
    if len(b)!=1024 or b[:8]!=bytes.fromhex('5763436600000008'):
        raise SystemExit('Offline WC24 config invalid')
    original=(ROOT/'workspace/dolphin/baseline-user/Wii/shared2/wc24/nwc24msg.cfg').read_bytes()
    if int.from_bytes(b[20:24],'big') not in (0,1) or b[8:16]==original[8:16] or b[88:156]!=bytes(68):
        raise SystemExit('Refusing WC24 ID, registration stage, password or mail-check credentials')
    if sum(struct.unpack('>255I',b[:1020]))&0xffffffff != int.from_bytes(b[1020:],'big'):
        raise SystemExit('WC24 checksum mismatch')
    for i in range(5):
        u=urlparse(b[156+128*i:284+128*i].split(b'\0')[0].decode('ascii'))
        if u.scheme!='http' or u.hostname!='127.0.0.1' or u.port!=9:raise SystemExit('Non-loopback WC24 destination')
    dl=(wc/'nwc24dl.bin').read_bytes()
    if len(dl)!=0xf800 or dl[:8]!=bytes.fromhex('5763446c00000001'):
        raise SystemExit('Invalid WC24 download list')
    for i in range(120):
        e=dl[2048+512*i:2560+512*i]
        if not int.from_bytes(e[12:16],'big'):continue
        u=urlparse(e[180:416].split(b'\0')[0].decode('ascii'))
        if u.hostname!='127.0.0.1' or u.port!=9 or not int.from_bytes(e[4:8],'big')&32:
            raise SystemExit('A scheduled task must be scrubbed before launch')
    return user

def scrub_download_tasks(profile='experiment-user'):
    p=user_path(profile)/'Wii/shared2/wc24/nwc24dl.bin'
    b=bytearray(p.read_bytes())
    if len(b)!=0xf800 or b[:8]!=bytes.fromhex('5763446c00000001'):raise SystemExit('Invalid download list')
    for i in range(120):
        off=2048+512*i
        if not int.from_bytes(b[off+12:off+16],'big'):continue
        struct.pack_into('>I',b,off+4,int.from_bytes(b[off+4:off+8],'big')|32)
        url=f'http://127.0.0.1:9/phase0-disabled/task-{i}'.encode()
        b[off+180:off+416]=url+bytes(236-len(url))
    p.write_bytes(b)

def archive_run_log(log, target):
    """Move the stopped profile's previous Dolphin log to a gzip in the private area.

    Dolphin appends to one log; moving it gives each archive exactly one run
    and keeps the private area small. Returns the archive path or None.
    """
    import gzip, shutil
    if not log.exists() or not log.stat().st_size:
        return None
    target = target.with_name(target.name + '.gz')
    with log.open('rb') as source, gzip.open(target, 'xb', compresslevel=6) as packed:
        shutil.copyfileobj(source, packed)
    log.unlink()
    return target

def proxy_environment():
    # libcurl reads these per-process variables. Never changes Windows proxy settings.
    with socket.socket() as s:
        s.settimeout(0.25)
        if s.connect_ex(('127.0.0.1',9))==0:raise SystemExit('Refusing launch: loopback discard/proxy port 9 is occupied')
    env={k:v for k,v in os.environ.items() if k.lower() not in ('http_proxy','https_proxy','all_proxy','no_proxy')}
    env.update(http_proxy='http://127.0.0.1:9',https_proxy='http://127.0.0.1:9',all_proxy='http://127.0.0.1:9',no_proxy='127.0.0.1,localhost,::1')
    return env

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--menu',action='store_true');ap.add_argument('--disc',action='store_true',help='v5/v6 catalogued GC disc diagnostic only');ap.add_argument('--debugger',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--profile',choices=PROFILES,default=PROFILES[0]);args=ap.parse_args()
    if args.disc and (args.profile not in ['gc-native-v5-user',*V6_FAMILY] or args.menu):raise SystemExit('Direct disc diagnostic requires v5-v7 and is mutually exclusive with --menu')
    exe=ROOT/'tools/dolphin-2609a/Dolphin-x64/Dolphin.exe'
    running=subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True)
    if b'dolphin.exe' in (running.stdout or b'').lower():raise SystemExit('Close existing Dolphin processes first; profile sharing is forbidden')
    if not args.check:scrub_download_tasks(args.profile)
    user=validate(args.profile);env=proxy_environment()
    if args.profile in NATIVE_PROFILES:validate_native_runtime(args.profile)
    if args.check:print('PASS: non-authenticated profile, loopback task destinations, unused local proxy port');return
    if args.profile in NATIVE_PROFILES:
        if args.debugger:raise SystemExit('Sandbox debugger option not enabled')
        runner=ROOT/(f'tools/gc-sandbox/v{args.profile.split("-v")[1].split("-")[0]}/bin/AppContainerRunner.exe' if args.profile in V6_FAMILY[1:] else 'tools/gc-sandbox/v6/bin/AppContainerRunner.exe' if args.profile in V6_FAMILY else 'tools/gc-sandbox/bin/AppContainerRunner.exe');runtime=user.parent
        p=popen_detached([str(runner),str(runtime),'disc' if args.disc else 'menu'],cwd=ROOT,env=env)
        print('OS AppContainer launcher started; helper PID',p.pid);return
    cmd=[str(exe),'--user',str(user)]
    if args.menu:cmd+=['--nand_title','0000000100000002']
    if args.debugger:cmd+=['--debugger']
    p=popen_detached(cmd,cwd=exe.parent,env=env)
    print('Sanitized project Dolphin launched; PID',p.pid)

if __name__=='__main__':main()
