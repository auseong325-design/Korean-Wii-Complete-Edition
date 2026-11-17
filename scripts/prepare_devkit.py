"""Project-only extraction of official devkitPro binary packages.

No registry, PATH, pacman database, system folders or post-install scripts change.
devkitPro officially supports pacman installation; this is an isolated Phase 0
inspection/smoke-test toolchain, not a replacement distribution.
"""
from __future__ import annotations
import hashlib, io, json, tarfile, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import zstandard

ROOT=Path(__file__).resolve().parents[1]
WINDOWS='https://pkg.devkitpro.org/packages/windows/x86_64/'
LIBS='https://downloads.devkitpro.org/packages/'
NAMES=['devkitPPC','devkitppc-binutils','devkitppc-mn10200-binutils','devkitppc-gcc','devkitppc-newlib','devkitppc-rules','devkitppc-crtls','general-tools','gamecube-tools','libogc','libfat-ogc','wii-examples']

def main():
    lock=ROOT/'configs/devkit.lock.json'
    if not lock.exists():raise SystemExit('Missing reviewed devkit lock; refusing implicit latest package resolution')
    selected=json.loads(lock.read_text())
    stage=ROOT/'tools/packages';stage.mkdir(parents=True,exist_ok=True)
    out=ROOT/'tools/devkitpro-root';out.mkdir(parents=True,exist_ok=True)
    def download(d):
        p=stage/d['url'].rsplit('/',1)[1]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=d['sha256']:
            req=urllib.request.Request(d['url'],headers={'User-Agent':'Phase0-project-local'})
            with urllib.request.urlopen(req,timeout=90) as r,p.open('wb') as f:
                while b:=r.read(1024*1024):f.write(b)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=d['sha256']:raise ValueError('Package hash mismatch: '+d['name'])
        return d,p
    with ThreadPoolExecutor(max_workers=4) as ex:packages=list(ex.map(download,selected))
    for d,p in packages:
        raw=zstandard.ZstdDecompressor().stream_reader(p.open('rb')) if p.name.endswith('.zst') else p.open('rb')
        with raw,tarfile.open(fileobj=raw,mode='r|*') as t:
            # data filter prevents escaping destination; never execute .INSTALL.
            t.extractall(out,filter='data')
        print(d['name'],d['version'],'hash verified')
    print('Project-local devkitPro package extraction complete')

if __name__=='__main__':main()
