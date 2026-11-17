"""Freeze a numbered internal-service menu candidate. No hardware installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce.dvd_integrated_hook import patch,SOURCE
from kwce.gc_native import patch_gc_native
from kwce.gc_card_encoding import patch_card_encodings


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision',type=int,required=True)
    ap.add_argument('--player',type=int,default=51)
    ap.add_argument('--module',type=int,default=10)
    ap.add_argument('--source-revision',type=int,choices=(37,38),default=37)
    args=ap.parse_args()
    out=ROOT/f'workspace/experiments/dvd-native-hook-v{args.revision}'
    if args.revision<63 or out.exists():raise ValueError('New integrated revision required')
    original=(ROOT/'workspace/console-baseline/menu-original-43K.dol').read_bytes()
    base=patch_gc_native(original,japanese_cards=True,japanese_comments=True)[0]
    module=ROOT/f'workspace/experiments/dvd-native-module-v{args.module}'
    module_record=json.loads((module/'manifest.json').read_text())
    player_path=ROOT/f'workspace/channels/dvd-player/build-v{args.player}/boot.dol'
    forwarder=module_record.get('kind')=='forwarder'
    if forwarder:
        # The resident payload is the small forwarder; the player stays on SD.
        if (module_record['source_build']!=args.player or args.source_revision!=37 or
            hashlib.sha256(player_path.read_bytes()).hexdigest()!=module_record['player_sha256']):
            raise ValueError('Forwarder module is pinned to a different player')
        payload=module/'forwarder.dol'
    else:payload=player_path
    assets=[(ROOT/p).read_bytes() for p in (
        payload,
        f'workspace/experiments/dvd-native-module-v{args.module}/player.ash',
        'workspace/experiments/dvd-native-banner-v2/menu.arc',
        'workspace/experiments/dvd-native-icon-v1/icon.arc')]
    source=ROOT/f'homebrew/kwce-disc-menu/native-v{args.source_revision}'
    data,record=patch(base,*assets,source_revision=args.source_revision)
    if patch(base,*assets,source_revision=args.source_revision)!=(data,record):raise ValueError('Byte reproducibility failed')
    out.mkdir();shutil.copytree(source,out/'source')
    record.update(revision=args.revision,player_revision=args.player,module_revision=args.module,
                  banner_revision=2,sha256=hashlib.sha256(data).hexdigest(),
                  hardware_qualification_required=True,
                  **(dict(forwarder=True,sd_player_path=module_record['sd_player_path'],
                          sd_player_sha256=module_record['player_sha256'],
                          sd_player_bytes=module_record['player_bytes']) if forwarder else {}),
                  sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()})
    (out/'menu.dol').write_bytes(data)
    (out/'menu-with-card-encoding.dol').write_bytes(patch_card_encodings(data)[0])
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'revision':args.revision,'code_bytes':record['code_bytes'],
                      'bundle_size':record['bundle_size'],'reproducible':True,
                      'hardware_qualified':False}))


if __name__=='__main__':main()
