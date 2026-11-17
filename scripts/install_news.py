"""Install one News build variant into the stopped isolated News NAND."""
import argparse,json,shutil,subprocess,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_news import register
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,required=True);ap.add_argument('--variant',choices=['test-feed','personal'],default='test-feed');args=ap.parse_args()
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before News update')
    register();wii=launcher.user_path('news-v1-user')/'Wii';target=(wii/'title/00010002/48414745').resolve()
    if not target.is_relative_to((ROOT/'workspace/sandbox/news-v1/user/Wii').resolve()):raise SystemExit('Unsafe News target')
    backup=PRIVATE/f'news-before-install-v{args.revision}-{args.variant}'
    if backup.exists():raise SystemExit('Existing update snapshot preserved')
    shutil.copytree(target,backup)
    folder=ROOT/f'workspace/channels/news/build-v{args.revision}';meta=json.loads((folder/'build-manifest.json').read_text(encoding='utf-8'))
    row=meta['wads'][args.variant];wad=folder/row['file']
    if sha256(wad)!=row['sha256']:raise ValueError('Build hash mismatch')
    title=load_library().title.Title();title.load_wad(wad.read_bytes())
    if title.tmd.title_id!='0001000248414745':raise ValueError('Refusing other title')
    load_library().nand.EmuNAND(wii).install_title(title)
    (ROOT/'workspace/channels/news/active-build.json').write_text(json.dumps(dict(revision=args.revision,variant=args.variant,wad_sha256=row['sha256'])))
    print(json.dumps(dict(installed=True,revision=args.revision,variant=args.variant)))
if __name__=='__main__':main()
