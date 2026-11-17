"""Preserve v7 art/text but derive executable translations from original code.
No loopback endpoints or local-registration bypass leave the emulator.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import load_library
from kwce.hardware import hardware_wad
from build_tvguide import executable

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    base=ROOT/'workspace/channels/tvguide';out=base/'build-v8';expected=None
    if args.reproduce:
        expected=(out/'tvguide-ko-hardware-test.wad').read_bytes();n=1
        while(ROOT/f'workspace/private/tvguide-hardware-reproduce-{n}').exists():n+=1
        out=ROOT/f'workspace/private/tvguide-hardware-reproduce-{n}'
    if out.exists():raise ValueError('Existing TV hardware build preserved')
    original=(base/'originals/tvguide-japan-original.wad').read_bytes()
    previous=(base/'build-v7/tvguide-ko-local-test.wad').read_bytes()
    prior=json.loads((base/'build-v7/build-manifest.json').read_text(encoding='utf-8'))
    strings=json.loads((ROOT/'configs/tvguide-executable-v4-ko.json').read_text(encoding='utf-8'))
    if hashlib.sha256(previous).hexdigest()!=prior['wad_sha256']or hashlib.sha256(original).hexdigest()!=strings['source_sha256']:raise ValueError('TV hardware inputs differ')
    lib=load_library();source=lib.title.Title();source.load_wad(original);title=lib.title.Title();title.load_wad(previous)
    raw=source.get_content_by_index(1);translated,record=executable(raw,strings['messages']);edited=bytearray(translated);restored=0
    for match in re.finditer(rb'https?://[^\0\s<>"\x80-\xff]{3,250}',raw):
        old=match.group()
        if b'.wapp.wii.com'in old:
            edited[match.start():match.end()]=old;restored+=1
    if restored!=record['local_endpoints']:raise ValueError('TV endpoint restoration differs')
    title.set_content(bytes(edited),1)
    wad,checks=hardware_wad(title.dump_wad(),original)
    check=lib.title.Title();check.load_wad(wad)
    for i in range(14):
        if i!=1 and check.get_content_by_index(i)!=title.get_content_by_index(i):raise ValueError('TV hardware resource differs')
    if expected is not None and expected!=wad:raise ValueError('TV hardware reproduction differs')
    out.mkdir(parents=True);(out/'tvguide-ko-hardware-test.wad').write_bytes(wad)
    manifest=dict(revision=8,hardware_candidate=True,hardware_success_verified=False,full_localization_complete=False,
        source_revision=7,source_wad_sha256=prior['wad_sha256'],original_sha256=hashlib.sha256(original).hexdigest(),
        wad_sha256=hashlib.sha256(wad).hexdigest(),local_only=False,restored_endpoints=restored,local_registration_bypass=False,
        translated_literals=record['translated_literals'],preserved_resource_contents=[0,2,3,4,5,6,7,8,9,10,11,12,13],hardware_checks=checks)
    (out/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: TV hardware v8, {restored} original endpoints, native registration, v7 resources preserved; '+('byte-identical reproduction'if expected else'not installed'))
if __name__=='__main__':main()
