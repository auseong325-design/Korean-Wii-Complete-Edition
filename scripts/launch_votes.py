"""Votes-only project NAND, locale/contents/hash guards, OS network isolation."""
import argparse,json,subprocess
from audit_sd import ROOT,sha256
from prepare_votes import register
import launch_dolphin as launcher
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--menu',action='store_true');ap.add_argument('--check',action='store_true');ap.add_argument('--diagnostic-metadata',action='store_true');ap.add_argument('--diagnostic-ui',action='store_true');ap.add_argument('--diagnostic-repack',action='store_true');args=ap.parse_args()
 if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
 register();user=launcher.user_path('votes-v1-user');root=user.parent
 for p in root.rglob('*'):
  if p.is_symlink()or p.is_junction():raise SystemExit('Indirect Votes path refused')
 launcher.scrub_download_tasks('votes-v1-user')
 launcher.validate('votes-v1-user')
 if sha256(root/'Dolphin-x64/Dolphin.exe')!=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text())['output_sha256']:raise SystemExit('Votes runtime changed')
 from kwce.channels import load_library
 from kwce.channel_validation import verify_installed_title
 from kwce.dolphin_fst import inspect_fst
 wad=ROOT/'workspace/channels/votes/build-v10/votes-ko-ui-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
 if args.diagnostic_metadata:
  wad=ROOT/'workspace/channels/votes/build-v1/votes-ko-metadata-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
 if args.diagnostic_ui:
  wad=ROOT/'workspace/channels/votes/build-v2/votes-ko-ui-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
 if args.diagnostic_repack:
  wad=ROOT/'workspace/channels/votes/diagnostic-repack/test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
 if sha256(wad)!=meta['wad_sha256']:raise SystemExit('Votes WAD changed')
 t=load_library().title.Title();t.load_wad(wad.read_bytes());verify_installed_title(user/'Wii','0001000148414a45',t.tmd.dump());inspect_fst((user/'Wii/fst.bin').read_bytes())
 if (user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending Votes FST transaction')
 baseline=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00000001'
 for name in ['00000002','00000100','00000101']:
  for p in (baseline/name/'content').glob('*'):
   if p.is_file()and sha256(p)!=sha256(user/'Wii/title/00000001'/name/'content'/p.name):raise SystemExit('System content differs')
 folder=ROOT/'tools/votes-sandbox/v1/bin';lock=json.loads((folder/'helper-build.json').read_text())
 for row in lock['files']:
  if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('Votes helper changed')
 if args.check:print('PASS: Votes locale, credentials, local tasks, installed content, runtime, helper, system preservation');return
 p=launcher.popen_detached([str(folder/'AppContainerRunner.exe'),str(root),'menu'if args.menu else'votes'],cwd=ROOT,env=launcher.proxy_environment());print('Votes capability 0 AppContainer started; helper PID',p.pid)
if __name__=='__main__':main()
