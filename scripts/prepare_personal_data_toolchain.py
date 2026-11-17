"""Project-local extras for the Korean Set Personal Data build.

Hash-locked ppc-libogg/ppc-libvorbisidec packages are extracted into
tools/personal-data-sandbox/toolchain (pacman metadata is never extracted or
run) and WiiLink's MIT libpatcher source is pinned by git blob SHA-1.
The shared tools/devkitpro-root is only read. No PATH/registry changes.
"""
import hashlib,io,json,lzma,sys,tarfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'configs/personal-data-toolchain.lock.json'

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'kwce-project-local'}),timeout=120).read()

def blob_sha1(raw):return hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()

def packages(lock):
    target=ROOT/lock['target'];stage=ROOT/'tools/personal-data-sandbox/packages';stage.mkdir(parents=True,exist_ok=True);done=[]
    for d in lock['packages']:
        p=stage/d['url'].rsplit('/',1)[1]
        if not p.exists():
            raw=get(d['url'])
            if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('Package hash mismatch: '+d['name'])
            p.write_bytes(raw)
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('Package hash mismatch: '+d['name'])
        if p.name.endswith('.zst'):
            import zstandard
            data=zstandard.ZstdDecompressor().decompressobj().decompress(raw)
        elif p.name.endswith('.xz'):data=lzma.decompress(raw)
        else:raise ValueError('Unsupported package compression')
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:')as t:
            for m in t:
                if m.name.startswith('.'):continue
                allowed='opt/devkitpro/portlibs/ppc/'
                if m.isdir()and allowed.startswith(m.name.rstrip('/')+'/'):continue
                if not m.name.startswith(allowed):raise ValueError('Package path outside portlibs: '+m.name)
                t.extract(m,target,filter='data')
        done.append(d['name']+' '+d['version'])
    return done

def sources(lock):
    out=[]
    for s in lock['sources']:
        base=ROOT/s['dest']
        for path,sha in s['files'].items():
            dest=base/path
            if dest.exists():raw=dest.read_bytes()
            else:raw=get(f'https://raw.githubusercontent.com/{s["repository"]}/{s["commit"]}/{path}')
            if blob_sha1(raw)!=sha:raise ValueError('Pinned source blob differs: '+s['name']+'/'+path)
            if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        out.append(f'{s["repository"]}@{s["commit"][:8]} ({len(s["files"])} files)')
    return out

def main():
    lock=json.loads(LOCK.read_text(encoding='utf-8'))
    font=lock['font_source']
    for key in['path','license_path']:
        sha=font['sha256'if key=='path'else'license_sha256']
        if hashlib.sha256((ROOT/font[key]).read_bytes()).hexdigest()!=sha:raise ValueError('Pinned OFL font input differs')
    print('Extracted:',', '.join(packages(lock)));print('Pinned:',', '.join(sources(lock)));print('OFL font input verified; shared devkitPro root unchanged')

if __name__=='__main__':sys.exit(main())
