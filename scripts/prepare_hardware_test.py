"""Emulator test bed for the real-console installer (stopped Dolphin only).

Creates workspace/sandbox/hardware-test-v1 (new, never overwritten) from the
stopped votes-test-v1 runtime + NAND, a capability-zero helper that only
boots sd-sync/apps/kwce-installer/boot.dol, and a Dolphin SD sync folder.
`--package kwce-alpha-vN` (re)copies a package into the SD folder while
Dolphin is stopped. The test NAND is a sanitized emulator copy; nothing here
touches a console.
"""
import argparse,configparser,json,os,shutil,subprocess
from pathlib import Path
from audit_sd import ROOT,sha256
from prepare_channel_access import stopped

SANDBOX=ROOT/'workspace/sandbox/hardware-test-v1'
TEMPLATE=ROOT/'workspace/sandbox/votes-test-v1'
HELPER=ROOT/'tools/hardware-test/v1/bin'

def build_helper():
    if HELPER.exists():return
    HELPER.mkdir(parents=True)
    text=(ROOT/'scripts/FeedRunner.cs').read_text()
    text=text.replace('class FeedRunner','class HardwareTestRunner')
    old='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    new='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","hardware-test-v1"),StringComparison.OrdinalIgnoreCase);'
    start=text.index('   if(args.Length!=3||args[2]!="0001000248414745"');end=text.index('   File.WriteAllText(Path.Combine(root,"child-exit.json")')
    block='''   if(args.Length!=2||args[1]!="dol")throw new Exception("Only the installer DOL mode is supported");
   string exe=Path.Combine(root,"Dolphin-x64","Dolphin.exe");string user=Path.Combine(root,"user");
   string dol=Path.Combine(root,"sd-sync","apps","kwce-installer","boot.dol");if(!File.Exists(dol))throw new Exception("Installer DOL missing");
   int childCode=Run(sid,exe,"--user "+Quote(user)+" --exec "+Quote(dol),Path.GetDirectoryName(exe));
'''
    if old not in text:raise SystemExit('FeedRunner layout changed')
    text=text[:start].replace(old,new)+block+text[end:]
    source=HELPER/'HardwareTestRunner.cs';source.write_text(text,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(HELPER/'HardwareTestRunner.exe'),str(source)],check=True,capture_output=True)
    (HELPER/'helper-build.json').write_text(json.dumps(dict(source='scripts/FeedRunner.cs',sha256=sha256(HELPER/'HardwareTestRunner.exe')),indent=2))

def create():
    if SANDBOX.exists():return
    SANDBOX.mkdir()
    shutil.copytree(TEMPLATE/'Dolphin-x64',SANDBOX/'Dolphin-x64');shutil.copy2(TEMPLATE/'NetProbe.exe',SANDBOX/'NetProbe.exe')
    shutil.copytree(TEMPLATE/'user',SANDBOX/'user',ignore=shutil.ignore_patterns('Logs','Cache','ScreenShots'))
    ini=SANDBOX/'user/Config/Dolphin.ini';config=configparser.ConfigParser(strict=False);config.optionxform=str;config.read(ini,encoding='utf-8-sig')
    config['Core']['WiiSDCard']='True';config['Core']['WiiSDCardEnableFolderSync']='True';config['Core']['WiiSDCardAllowWrites']='True'
    config['Core']['WiiSDCardFilesize']=str(2*1024**3)  # the auto size (820 MiB) is reported invalid
    # A clean stop writes the SD sync folder back (state/ and log.txt), so no stop prompt.
    if 'Interface' not in config:config['Interface']={}
    config['Interface']['ConfirmStop']='False'
    if 'General' not in config:config['General']={}
    config['General']['WiiSDCardSyncFolder']=str(SANDBOX/'sd-sync').replace('\\','/')+'/'
    for section in config.sections():  # template-absolute paths (GC memory cards) move to this test bed
        for key,value in config[section].items():
            if 'votes-test-v1' in value:config[section][key]=value.replace('votes-test-v1','hardware-test-v1')
    with ini.open('w',encoding='utf-8')as f:config.write(f,space_around_delimiters=True)
    (SANDBOX/'sd-sync').mkdir()

def copy_package(name):
    src=ROOT/'workspace/hardware'/name
    if not(src/'package-manifest.json').exists():raise SystemExit('Unknown package')
    sd=SANDBOX/'sd-sync'
    for sub in['apps','kwce']:
        if(sd/sub).exists()and sub=='apps':shutil.rmtree(sd/sub)
    shutil.copytree(src/'apps',sd/'apps')
    (sd/'kwce').mkdir(exist_ok=True)
    for item in(src/'kwce').iterdir():  # keep state/ and log.txt from earlier test runs
        target=sd/'kwce'/item.name
        if item.is_dir():
            if target.exists():shutil.rmtree(target)
            shutil.copytree(item,target)
        else:shutil.copy2(item,target)
    print('package copied to SD sync folder:',name)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package');args=ap.parse_args()
    stopped();build_helper();create()
    if args.package:copy_package(args.package)
    print('hardware test bed ready:',SANDBOX.relative_to(ROOT))

if __name__=='__main__':main()
