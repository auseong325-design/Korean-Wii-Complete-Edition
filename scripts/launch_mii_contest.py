"""MiiContest-only project NAND, locale/contents/hash guards, OS network isolation."""
import argparse,json,subprocess
from audit_sd import ROOT,sha256
from prepare_mii_contest import register
import launch_dolphin as launcher
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--menu',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args()
 if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin first')
 register();user=launcher.user_path('mii-contest-v1-user');root=user.parent
 for p in root.rglob('*'):
  if p.is_symlink()or p.is_junction():raise SystemExit('Indirect MiiContest path refused')
 launcher.scrub_download_tasks('mii-contest-v1-user')
 launcher.validate('mii-contest-v1-user')
 if sha256(root/'Dolphin-x64/Dolphin.exe')!=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text())['output_sha256']:raise SystemExit('MiiContest runtime changed')
 from kwce.channels import load_library
 from kwce.channel_validation import verify_installed_title
 from kwce.dolphin_fst import inspect_fst
 wad=ROOT/'workspace/channels/mii-contest/build-v7/mii-contest-ko-ui-test.wad';meta=json.loads(wad.with_name('build-manifest.json').read_text())
 if sha256(wad)!=meta['wad_sha256']:raise SystemExit('MiiContest WAD changed')
 t=load_library().title.Title();t.load_wad(wad.read_bytes());verify_installed_title(user/'Wii','0001000148415045',t.tmd.dump());inspect_fst((user/'Wii/fst.bin').read_bytes())
 if (user/'Wii/fst.bin.xxx').exists():raise SystemExit('Pending MiiContest FST transaction')
 baseline=ROOT/'workspace/sandbox/gc-v6/user/Wii/title/00000001'
 for name in ['00000002','00000100','00000101']:
  for p in (baseline/name/'content').glob('*'):
   if p.is_file()and sha256(p)!=sha256(user/'Wii/title/00000001'/name/'content'/p.name):raise SystemExit('System content differs')
 folder=ROOT/'tools/mii-contest-sandbox/v1/bin';lock=json.loads((folder/'helper-build.json').read_text())
 for row in lock['files']:
  if sha256(ROOT/row['path'])!=row['sha256']:raise SystemExit('MiiContest helper changed')
 if args.check:print('PASS: MiiContest locale, credentials, local tasks, installed content, runtime, helper, system preservation');return
 p=launcher.popen_detached([str(folder/'AppContainerRunner.exe'),str(root),'menu'if args.menu else'mii_contest'],cwd=ROOT,env=launcher.proxy_environment());print('MiiContest capability 0 AppContainer started; helper PID',p.pid)
if __name__=='__main__':main()
