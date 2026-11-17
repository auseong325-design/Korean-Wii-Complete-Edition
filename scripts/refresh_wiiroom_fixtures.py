"""Refresh synthetic Room fixtures only when stopped; keep every prior revision."""
import argparse,json
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_wiiroom_test import fixtures
from kwce.channels import load_library

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video',action='store_true');parser.add_argument('--guest',action='store_true');args=parser.parse_args()
    stopped();load_library();base=ROOT/'workspace/sandbox/wiiroom-test-v1';feed=base/'local-feed';revision=1
    while((base/f'local-feed-v{revision}').exists()or(base/f'local-feed-next-v{revision+1}').exists()or(PRIVATE/f'wiiroom-runtime-before-fixture-{revision+1}.json').exists()):revision+=1
    backup=base/f'local-feed-v{revision}'
    stage=base/f'local-feed-next-v{revision+1}'
    if feed.resolve().parent!=base.resolve()or backup.resolve().parent!=base.resolve():raise ValueError('Fixture move outside approved experiment')
    lock=ROOT/'configs/wiiroom-runtime.lock.json';snapshot=PRIVATE/f'wiiroom-runtime-before-fixture-{revision+1}.json'
    if snapshot.exists():raise SystemExit('Prior lock snapshot preserved')
    # Complete and verify the new set before moving the current usable feed.
    video=None
    if args.video:
        runtime=ROOT/'workspace/sandbox/wiiroom-video-v2';record=json.loads((runtime/'video-manifest.json').read_text())
        if not record['synthetic']or record['external_media']or record['capability_count']!=0 or not record['decode_completed']:raise ValueError('Only own decoded synthetic video')
        for row in record['files']:
            if sha256(ROOT/row['path'])!=row['sha256']:raise ValueError('Video runtime differs')
        video=runtime/'sample.mov'
    count=fixtures(stage,video=video,guest=args.guest);snapshot.write_bytes(lock.read_bytes());feed.rename(backup);stage.rename(feed);d=json.loads(lock.read_text())
    for row in d['files']:
        if row['path'].endswith('/local-feed/fixture-manifest.json'):row['sha256']=sha256(feed/'fixture-manifest.json')
    lock.write_text(json.dumps(d,indent=2));print('Preserved earlier fixture; generated local fixture revision',revision+1,'with',count,'routes')

if __name__=='__main__':main()
