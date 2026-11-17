"""Select a verified DVD image in the stopped integrated test bed; preserve prior media."""
import argparse,json,shutil,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped

def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--disc',type=int);group.add_argument('--user-disc',type=int);args=parser.parse_args()
    revision=args.disc if args.disc is not None else args.user_disc
    if revision<1:raise ValueError('DVD media revision must be positive')
    stopped();target=ROOT/'workspace/sandbox/dvd-test-v2/sd-sync/kwce/dvd'
    if args.disc is not None:
        source=ROOT/f'workspace/test-media/dvd/kwce-dvd-test-v{revision}.iso';meta=json.loads(source.with_suffix('.json').read_text(encoding='utf-8'))
        if not meta['synthetic']or sha256(source)!=meta['sha256']:raise ValueError('Unverified synthetic DVD')
        selected=dict(kind='synthetic',revision=revision,sha256=meta['sha256'],size=source.stat().st_size)
    else:
        source=PRIVATE/f'dvd-user-test-v{revision}/test-disc.iso';meta=json.loads(source.with_name('import-manifest.json').read_text(encoding='utf-8'))
        if not meta['user_provided']or not meta['source_unchanged']or meta['transcoded']or sha256(source)!=meta['iso_sha256']:raise ValueError('Unverified user DVD')
        selected=dict(kind='user-provided',revision=revision,sha256=meta['iso_sha256'],size=source.stat().st_size)
    n=1
    while(PRIVATE/f'dvd-test-v2-media-before-{n}').exists():n+=1
    backup=PRIVATE/f'dvd-test-v2-media-before-{n}';backup.mkdir()
    for name in ['test-disc.iso','current-media.json']:
        if(target/name).exists():shutil.copy2(target/name,backup/name)
    shutil.copy2(source,target/'test-disc.iso')
    if sha256(target/'test-disc.iso')!=selected['sha256']:raise ValueError('DVD media copy differs')
    (target/'current-media.json').write_text(json.dumps(selected,indent=2),encoding='utf-8')
    print('PASS: integrated DVD media selected:',selected['kind'],revision,'; previous image preserved')

if __name__=='__main__':main()
