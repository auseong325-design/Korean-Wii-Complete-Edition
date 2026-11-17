"""Korean Photo Prints Channel — hardware candidate (create-once hardware-v1).

Same Korean resources as the local build, but content 1 keeps the WiiLink
Digicam_1_Japan service endpoints (cam-prod.wiilink24.com) instead of the
loopback redirect, and the WAD is fakesigned for the user's own console via
kwce.hardware.hardware_wad (which also refuses any local/loopback reference and
checks it matches the original's reference counts). Not installed anywhere.
manifest hardware_success_verified=false. Byte-identically reproducible.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.hardware import hardware_wad
from build_photoprints import build

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=10,choices=[1,3,6,9,10]);ap.add_argument('--reproduce',action='store_true');args=ap.parse_args()
    hw={1:'hardware-v1',3:'hardware-v2',6:'hardware-v3',9:'hardware-v4',10:'hardware-v5'}[args.revision]
    base=ROOT/'workspace/channels/photoprints';out=base/hw;expected=None
    original=(base/'originals/digicam-japan-v1024.wad').read_bytes()
    if args.reproduce:
        expected=(out/'photoprints-ko-hardware-test.wad').read_bytes();n=1
        while(ROOT/f'workspace/private/photoprints-hardware-{hw}-reproduce-{n}').exists():n+=1
        out=ROOT/f'workspace/private/photoprints-hardware-{hw}-reproduce-{n}'
    if out.exists():raise SystemExit('Existing Photo Prints hardware build preserved')
    korean,record=build(original,local=False,revision=args.revision)
    wad,checks=hardware_wad(korean,original)
    out.mkdir(parents=True);(out/'photoprints-ko-hardware-test.wad').write_bytes(wad)
    manifest=dict(hardware_candidate=True,hardware_success_verified=False,full_localization_complete=False,
        local_only=False,source_revision=args.revision,original_sha256=hashlib.sha256(original).hexdigest(),
        wad_sha256=hashlib.sha256(wad).hexdigest(),korean_source_sha256=record['wad_sha256'],
        service_endpoints_kept=True,local_registration_bypass=False,
        translated_brlyt=record['translated_brlyt'],executable=record['executable']['applied'],
        korean_area=record['korean_area'],font=record['font'],textures=record.get('textures'),text_fit=record.get('text_fit'),hardware_checks=checks)
    (out/'build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if expected is not None and expected!=wad:raise ValueError('Photo Prints hardware reproduction differs')
    print(('Reproduced byte-identically' if expected is not None else 'Built'),hw,'from local rev',args.revision,'; endpoints kept, fakesigned, not installed; sha',manifest['wad_sha256'][:12])
if __name__=='__main__':main()
