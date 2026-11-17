"""Build the DVD player's HOME Menu archive (kwce/dvd_home_ui.py) as a numbered artifact.

Source: the System Menu resource used for the player banner (gc-native-v6
menu-resource.app; its HOME Menu files are the console's originals).
Output: a new workspace/channels/dvd-player/home-ui-vN/home.arc + manifest
(never overwritten). The WAD builder installs it as channel content 3; the
emulator test bed copies it to the test SD as kwce/dvd/home.arc.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce.dvd_home_ui import dvd_home_archive

RESOURCE=ROOT/'workspace/experiments/gc-native-v6/menu-resource.app'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);args=ap.parse_args()
    out=ROOT/f'workspace/channels/dvd-player/home-ui-v{args.revision}'
    if out.exists():raise SystemExit('Existing HOME Menu archive preserved')
    resource=RESOURCE.read_bytes()
    archive,record=dvd_home_archive(resource,args.revision)
    again,_=dvd_home_archive(resource,args.revision)
    if again!=archive:raise SystemExit('HOME Menu archive build is not deterministic')
    out.mkdir(parents=True);(out/'home.arc').write_bytes(archive)
    record.update(revision=args.revision,resource_sha256=hashlib.sha256(resource).hexdigest(),publish=False)
    (out/'home-ui-manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=1),encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('revision','files','bytes','sha256')}))

if __name__=='__main__':main()
