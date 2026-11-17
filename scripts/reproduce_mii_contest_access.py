"""Re-derive a Mii Contest access-build WAD from its source build and require identical bytes.

  .venv\\Scripts\\python.exe scripts\\reproduce_mii_contest_access.py --access 22

install_access_build.py has no reproduce mode and installs as a side effect. This repeats only its
pure mii-contest step (the six fixed-size NAS URL redirects to 127.0.0.2 inside content 1, then
dump_wad) from the source build named in access-build-vN/build-manifest.json, and compares the result
with the preserved access WAD, its manifest hash and its recorded redirect ranges. Nothing is
installed or written.
"""
import argparse,hashlib,json,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def derive(source_wad):
    """Same transformation as install_access_build.py applies to a mii-contest build."""
    t=load_library().title.Title();t.load_wad(source_wad)
    exe=t.get_content_by_index(1);updated=bytearray(exe);patches=[]
    sections=[(o,o+n)for o,n in zip(struct.unpack_from('>18I',exe,0),struct.unpack_from('>18I',exe,0x90))if n]
    for m in re.finditer(rb'https?://naswii\.(?:(?:test|dev)\.)?nintendowifi\.net[^\x00\s]*',exe):
        before=m.group();after=re.sub(rb'^https?://[^/]+',b'http://127.0.0.2',before)
        if len(after)>len(before)or not any(a<=m.start()<m.end()<=b for a,b in sections):raise ValueError('NAS string range')
        updated[m.start():m.end()]=after.ljust(len(before),b'\0');patches.append(dict(offset=m.start(),old_size=len(before),new_size=len(after)))
    if len(patches)!=6:raise ValueError('Expected six NAS URL constants')
    t.set_content(bytes(updated),1)
    return t.dump_wad(),patches

def check(access):
    base=ROOT/'workspace/channels/mii-contest';acc=base/f'access-build-v{access}'
    meta=json.loads((acc/'build-manifest.json').read_text())
    src=(base/meta['source_build']/'mii-contest-ko-ui-test.wad').read_bytes()
    if hashlib.sha256(src).hexdigest()!=meta['source_wad_sha256']:raise ValueError('Source build WAD differs from the access manifest')
    wad,patches=derive(src)
    if wad!=(acc/'mii-contest-local-test.wad').read_bytes()or hashlib.sha256(wad).hexdigest()!=meta['wad_sha256']or patches!=meta['nas_url_ranges']:
        raise ValueError('Access build reproduction differs')
    return meta

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--access',type=int,required=True);args=ap.parse_args()
    meta=check(args.access)
    print(f'PASS: access-build-v{args.access} reproduced byte-identically from {meta["source_build"]} '
          f'(6 NAS redirects, nothing installed); sha {meta["wad_sha256"][:12]}')
if __name__=='__main__':main()
