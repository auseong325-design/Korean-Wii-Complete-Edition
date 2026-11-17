"""News-only project NAND, locale/contents/hash guards, OS network isolation."""
import argparse,json,subprocess
from audit_sd import ROOT,sha256
from prepare_news import register
import launch_dolphin as launcher
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--menu',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--cache-preview',action='store_true',help='keep the public News task so the seeded local cache is read; network stays blocked');args=ap.parse_args()
 if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
 register();user=launcher.user_path('news-v1-user');root=user.parent
 for p in root.rglob('*'):
  if p.is_symlink()or p.is_junction():raise SystemExit('Indirect News path refused')
 if not args.check and not args.cache_preview:launcher.scrub_download_tasks('news-v1-user')
 try:launcher.validate('news-v1-user')
 except SystemExit as error:
  if not args.cache_preview or str(error)!='A scheduled task must be scrubbed before launch':raise
  # Only the channel's own public News task may stay unscrubbed in preview mode.
  import struct
  dl=(user/'Wii/shared2/wc24/nwc24dl.bin').read_bytes()
  for i in range(120):
   e=dl[2048+512*i:2560+512*i]
   if not int.from_bytes(e[12:16],'big'):continue
   url=e[180:416].split(b'\0')[0]
   if url.startswith(b'http://127.0.0.1:9/'):continue
   if set(struct.unpack_from('>II',e,8))!={0x00010002,0x48414745}or url not in(b'http://news.wiilink.ca/v2/1/136/news.bin',b'http://news.wiilink.ca/v2/1/049/news.bin',((root/'local-feed').resolve().as_uri()+'/v2/1/136/news.bin').encode()):raise SystemExit('Unexpected unscrubbed task')
 if sha256(root/'Dolphin-x64/Dolphin.exe')!=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text())['output_sha256']:raise SystemExit('News runtime changed')
 from kwce.channels import load_library
 from kwce.channel_validation import verify_installed_title
 from kwce.dolphin_fst import inspect_fst
 marker=ROOT/'workspace/channels/news/active-build.json';active=json.loads(marker.read_text())if marker.exists()else dict(revision=1)
 folder=ROOT/f"workspace/channels/news/build-v{active['revision']}";meta=json.loads((folder/'build-manifest.json').read_text(encoding='utf-8'))
 row=meta['wads'][active['variant']]if 'wads'in meta else dict(file='news-ko-personal-test.wad',sha256=meta['wad_sha256'])
 wad=folder/row['file']
 if sha256(wad)!=row['sha256']:raise SystemExit('News WAD changed')
 t=load_library().title.Title();t.load_wad(wad.read_bytes());verify_installed_title(user/'Wii','0001000248414745',t.tmd.dump());inspect_fst((user/'Wii/fst.bin').read_bytes())
 if (user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending News FST transaction')
 baseline=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00000001'
 for name in ['00000002','00000100','00000101']:
  for p in (baseline/name/'content').glob('*'):
   if p.is_file()and sha256(p)!=sha256(user/'Wii/title/00000001'/name/'content'/p.name):raise SystemExit('System content differs')
 folder=ROOT/'tools/news-sandbox/v1/bin';lock=json.loads((folder/'helper-build.json').read_text())
 for row in lock['files']:
  if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('News helper changed')
 if args.check:print('PASS: News locale, credentials, local tasks, installed content, runtime, helper, system preservation');return
 p=launcher.popen_detached([str(folder/'AppContainerRunner.exe'),str(root),'menu'if args.menu else'news'],cwd=ROOT,env=launcher.proxy_environment());print('News capability 0 AppContainer started; helper PID',p.pid)
if __name__=='__main__':main()
