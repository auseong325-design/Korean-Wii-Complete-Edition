"""Install a Korean channel build into its stopped local-response test NAND.

The build WAD is copied unchanged into access-build-vN (the run_channel_test
contract) and installed with libWiiPy; the previous title folder is snapshotted.
Mii Contest builds get the six fixed-size NAS URL redirects of
prepare_mii_local_nas.py (access-build-v3) applied to content 1 first.
"""
import argparse,hashlib,json,re,shutil,struct,subprocess,sys
from audit_sd import ROOT,PRIVATE
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
TITLES={'nintendo':('00010001/48415445','nintendo-ko-ui-test.wad','nintendo-test-v1'),
        'votes':('00010001/48414a45',None,'votes-test-v1'),'mii-contest':('00010001/48415045',None,'mii-contest-test-v1')}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('channel',choices=sorted(TITLES));ap.add_argument('--build',type=int,required=True);ap.add_argument('--access',type=int,required=True);ap.add_argument('--wad');args=ap.parse_args()
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
    tid,default,sandbox=TITLES[args.channel];base=ROOT/f'workspace/channels/{args.channel}'
    src=base/f'build-v{args.build}'/(args.wad or default);out=base/f'access-build-v{args.access}'
    if out.exists():raise SystemExit('Existing access build preserved')
    prev=json.loads((base/('access-build-v3'if args.channel=='mii-contest'else'access-build-v2')/'build-manifest.json').read_text())
    lib=load_library();t=lib.title.Title();t.load_wad(src.read_bytes());source_digest=hashlib.sha256(src.read_bytes()).hexdigest();extra={}
    if args.channel=='mii-contest':
        exe=t.get_content_by_index(1);updated=bytearray(exe);patches=[]
        sections=[(o,o+n)for o,n in zip(struct.unpack_from('>18I',exe,0),struct.unpack_from('>18I',exe,0x90))if n]
        for m in re.finditer(rb'https?://naswii\.(?:(?:test|dev)\.)?nintendowifi\.net[^\x00\s]*',exe):
            before=m.group();after=re.sub(rb'^https?://[^/]+',b'http://127.0.0.2',before)
            if len(after)>len(before)or not any(a<=m.start()<m.end()<=b for a,b in sections):raise ValueError('NAS string range')
            updated[m.start():m.end()]=after.ljust(len(before),b'\0');patches.append(dict(offset=m.start(),old_size=len(before),new_size=len(after)))
        if len(patches)!=6:raise ValueError('Expected six NAS URL constants')
        t.set_content(bytes(updated),1);extra=dict(nas_local_stub=True,nas_url_ranges=patches)
    wad=t.dump_wad();out.mkdir();(out/f'{args.channel}-local-test.wad').write_bytes(wad);digest=hashlib.sha256(wad).hexdigest()
    meta=dict(prev);meta.update(revision=args.access,source_build=f'build-v{args.build}',source_wad_sha256=source_digest,wad_sha256=digest,**extra)
    (out/'build-manifest.json').write_text(json.dumps(meta,indent=2))
    wii=ROOT/f'workspace/sandbox/{sandbox}/user/Wii';target=wii/'title'/tid
    shutil.copytree(target,PRIVATE/f'{args.channel}-test-before-access-v{args.access}')
    lib.nand.EmuNAND(wii).install_title(t)
    (base/'active-access.json').write_text(json.dumps(dict(revision=args.access)))
    print(json.dumps(dict(channel=args.channel,access=args.access,build=args.build,wad_sha256=digest)))
if __name__=='__main__':main()
