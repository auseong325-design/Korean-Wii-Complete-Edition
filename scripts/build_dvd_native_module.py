"""ASH package for the native loader. New private numbered output only."""
import argparse
import hashlib
import json
import sys
from audit_sd import ROOT
sys.path.insert(0,str(ROOT))
from kwce.formats import ash_compress,ash_decompress
from kwce.dvd_native_relocate import validate_payload,validate_ash_mapping
from kwce.ppc_patch import sections


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--player',type=int,required=True);ap.add_argument('--revision',type=int,required=True);a=ap.parse_args()
    out=ROOT/f'workspace/experiments/dvd-native-module-v{a.revision}'
    if out.exists():raise SystemExit('Existing numbered module preserved')
    player=ROOT/f'workspace/channels/dvd-player/build-v{a.player}'
    data=(player/'boot.dol').read_bytes();build=json.loads((player/'build-manifest.json').read_text())
    if hashlib.sha256(data).hexdigest()!=build['boot_dol_sha256']:raise ValueError('Player build differs')
    validate_payload(data)
    validate_ash_mapping(data)
    packed=ash_compress(data)
    if ash_decompress(packed)!=data:raise ValueError('ASH roundtrip differs')
    out.mkdir();(out/'player.ash').write_bytes(packed)
    record=dict(schema=1,source_build=a.player,source_sha256=hashlib.sha256(data).hexdigest(),
                packed_sha256=hashlib.sha256(packed).hexdigest(),bytes=len(packed),raw_bytes=len(data))
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(f'PASS native module v{a.revision}: player R{a.player}; {len(data)} -> {len(packed)} bytes; exact roundtrip')


if __name__=='__main__':main()
