"""Project-local extraction of the DVD player build toolchain (libogc2 + portlibs + make).

Same rules as prepare_devkit.py: hash-locked packages only, extracted into
tools/ (devkitPro root or tools/msys-make). No registry, PATH, pacman database,
system folder or post-install script is changed or run.
"""
import hashlib,json,tarfile,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import zstandard

ROOT=Path(__file__).resolve().parents[1]
TARGETS={'devkitpro':ROOT/'tools/devkitpro-root','msys-make':ROOT/'tools/msys-make'}

def main():
    lock=json.loads((ROOT/'configs/dvd-player-toolchain.lock.json').read_text(encoding='utf-8'))
    stage=ROOT/'tools/packages';stage.mkdir(parents=True,exist_ok=True)
    def download(d):
        p=stage/d['url'].rsplit('/',1)[1]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=d['sha256']:
            req=urllib.request.Request(d['url'],headers={'User-Agent':'kwce-project-local'})
            with urllib.request.urlopen(req,timeout=120) as r,p.open('wb') as f:
                while b:=r.read(1024*1024):f.write(b)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=d['sha256']:raise ValueError('Package hash mismatch: '+d['name'])
        return d,p
    with ThreadPoolExecutor(max_workers=4) as ex:packages=list(ex.map(download,lock['packages']))
    for d,p in packages:
        out=TARGETS[d['target']];out.mkdir(parents=True,exist_ok=True)
        with zstandard.ZstdDecompressor().stream_reader(p.open('rb')) as raw,tarfile.open(fileobj=raw,mode='r|*') as t:
            for m in t:
                if m.name.startswith('.'):continue  # .PKGINFO/.MTREE/.INSTALL metadata is never extracted or run
                t.extract(m,out,filter='data')
        print(d['name'],d['version'],'hash verified')
    print('DVD player toolchain extraction complete')

if __name__=='__main__':main()
