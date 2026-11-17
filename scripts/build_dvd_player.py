"""Build the KWCE DVD player DOL (WiiMC fork, see kwce/dvd_player_fork.py).

Default build has no CSS decryption (libdvdcss device I/O only); --css keeps
upstream css.c and must only be used when the user asks for it.
The patched tree is synced into a persistent build cache (unchanged files keep
their mtimes, so make only recompiles what changed). Output: a new
workspace/channels/dvd-player/build-vN (never overwritten).
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce import dvd_player_fork as fork

UPSTREAM=ROOT/'external/other-tools/wiimc'
BASH=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/bin/bash.exe'

def sha256(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def sync(staged,cache):
    changed=0
    for src in staged.rglob('*'):
        if src.is_dir():continue
        dst=cache/src.relative_to(staged);data=src.read_bytes()
        if dst.exists() and dst.read_bytes()==data:continue
        dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data);changed+=1
    return changed

def msys(path):
    p=Path(path).resolve().as_posix()
    return '/'+p[0].lower()+p[2:] if p[1]==':' else p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--css',action='store_true');ap.add_argument('--jobs',type=int,default=8);ap.add_argument('--reproduce',action='store_true',help='compare a preserved numbered build in a new private output directory')
    args=ap.parse_args()
    out=ROOT/f'workspace/channels/dvd-player/build-v{args.revision}'
    expected=None
    if args.reproduce:
        expected=json.loads((out/'build-manifest.json').read_text(encoding='utf-8'))
        if expected['css_decryption']!=args.css or sha256(out/'boot.dol')!=expected['boot_dol_sha256']:raise SystemExit('Preserved DVD build differs from requested reproduction')
        run=1
        while(ROOT/f'workspace/private/dvd-player-reproduce-v{args.revision}-{run}').exists():run+=1
        out=ROOT/f'workspace/private/dvd-player-reproduce-v{args.revision}-{run}'
    elif out.exists():raise SystemExit('Existing DVD player build preserved')
    head=subprocess.run(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    if head!=fork.SOURCE_COMMIT:raise SystemExit('Upstream WiiMC commit differs from the reviewed fork base')
    cache=ROOT/('workspace/build/dvd-player-cache'+('-css' if args.css else ''))
    with tempfile.TemporaryDirectory(dir=ROOT/'workspace/build') as tmp:
        staged=Path(tmp)/'src'
        shutil.copytree(UPSTREAM,staged,ignore=shutil.ignore_patterns('.git','executables','build'))
        applied=fork.apply(staged,ROOT,args.revision,args.css)
        changed=sync(staged,cache)
    # The old MPlayer makefiles do not track configuration flags as dependencies.
    # Rebuild the decoder objects when the compiler policy changes, including
    # returning to an older revision for byte reproduction.
    flags=cache/'kwce-mplayer-flags.sha256'
    signature=sha256(cache/'source/mplayer/config.mak')
    if args.revision>=38 or flags.exists():
        if not flags.exists() or flags.read_text()!=signature:
            for ext in ('*.o','*.a'):
                for object_file in (cache/'source/mplayer').rglob(ext):object_file.unlink()
            (cache/'libmplayerwii.a').unlink(missing_ok=True)
            flags.write_text(signature)
    # Upstream's final ELF target omits libmplayerwii.a as a dependency.
    # Reuse compiled objects but always relink; a library-only fix otherwise
    # silently leaves the previous DOL in place. Numbered outputs are preserved.
    for suffix in ['elf','dol']:
        cached_output=cache/f'executables/wiimc.{suffix}'
        if cached_output.exists():cached_output.unlink()
    dkp=ROOT/'tools/devkitpro-root/opt/devkitpro';pp=dkp/'portlibs/ppc'
    if args.revision>=31:
        # Reuse the exact locked library object; make only its controller
        # table visible to our status-request bridge. Never modify the SDK.
        binpath=dkp/'devkitPPC/bin'
        archive=dkp/'libogc2/wii/lib/libwiiuse.a'
        with tempfile.TemporaryDirectory(dir=ROOT/'workspace/build') as objdir:
            subprocess.run([str(binpath/'powerpc-eabi-ar.exe'),'x',str(archive),'wpad.o'],cwd=objdir,check=True)
            subprocess.run([str(binpath/'powerpc-eabi-objcopy.exe'),'--globalize-symbol=__wpads',str(Path(objdir)/'wpad.o'),str(cache/'kwce_wpad.o')],check=True)
    env=dict(os.environ,DEVKITPRO=msys(dkp),DEVKITPPC=msys(dkp/'devkitPPC'))
    path=':'.join(msys(p) for p in [ROOT/'tools/msys-make/usr/bin',dkp/'devkitPPC/bin',dkp/'tools/bin'])
    cmd=(f'export PATH="{path}:$PATH"; make -j{args.jobs} FREETYPE_CFLAGS="-I{msys(pp)}/include/freetype2 -I{msys(pp)}/include" '
         f'FREETYPE_LIBS="-L{msys(pp)}/lib -lfreetype -lpng16 -lbz2 -lbrotlidec -lbrotlicommon -lz"')
    log=ROOT/f'workspace/build/dvd-player-v{args.revision}.log'
    attempt=1
    while log.exists():
        attempt+=1;log=ROOT/f'workspace/build/dvd-player-v{args.revision}-attempt{attempt}.log'
    with log.open('w',encoding='utf-8') as f:
        r=subprocess.run([str(BASH),'-c',cmd],cwd=cache,env=env,stdout=f,stderr=subprocess.STDOUT)
    dol=cache/'executables/wiimc.dol'
    if r.returncode or not dol.exists():raise SystemExit(f'Build failed; see {log.relative_to(ROOT)}')
    out.mkdir(parents=True);shutil.copy2(dol,out/'boot.dol')
    # Keep symbols beside a new private/local build so runtime fault addresses
    # can be resolved against that exact DOL, without relying on mutable cache.
    elf=cache/'executables/wiimc.elf'
    if elf.exists():shutil.copy2(elf,out/'boot.elf')
    manifest=dict(revision=args.revision,css_decryption=args.css,upstream='dborth/wiimc',upstream_commit=head,license='GPL-3.0 (fork, personal use only)',
                  patches_applied=applied,files_changed_in_cache=changed,forced_relink=True,boot_dol_sha256=sha256(out/'boot.dol'),boot_dol_bytes=(out/'boot.dol').stat().st_size,
                  toolchain=dict(devkit=sha256(ROOT/'configs/devkit.lock.json'),dvd=sha256(ROOT/'configs/dvd-player-toolchain.lock.json')))
    (out/'build-manifest.json').write_text(json.dumps(manifest,indent=1),encoding='utf-8')
    if expected:
        identical=manifest['boot_dol_sha256']==expected['boot_dol_sha256']
        (out/'reproduction.json').write_text(json.dumps(dict(revision=args.revision,byte_identical=identical,expected_sha256=expected['boot_dol_sha256'],actual_sha256=manifest['boot_dol_sha256']),indent=2),encoding='utf-8')
        if not identical:raise SystemExit('DVD player reproduction differs; original preserved, private result retained')
        print('PASS: DVD player build-v'+str(args.revision)+' byte-identical reproduction; original preserved')
    else:print(json.dumps(manifest))

if __name__=='__main__':main()
