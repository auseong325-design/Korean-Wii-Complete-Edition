"""Create one sanitized mail UI preview with no registration-capable DOL."""
import configparser,json,os,shutil,subprocess,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
sys.path.insert(0,str(ROOT))
import launch_dolphin as launcher
PROFILE='mail-test-v1-user';BASE=ROOT/'workspace/sandbox/mail-test-v1';HELPER=ROOT/'tools/mail-sandbox/v1/bin'

def register():
    launcher.NATIVE_PROFILES[PROFILE]='workspace/sandbox/mail-test-v1'
    if PROFILE not in launcher.PROFILES:launcher.PROFILES=(*launcher.PROFILES,PROFILE)

def main():
    stopped();candidate=ROOT/'workspace/hardware/mail-candidate-v3';manifest=json.loads((candidate/'candidate-manifest.json').read_text())
    if manifest.get('preview_write_symbols_absent')is not True:raise ValueError('Mail preview is not verified incapable')
    if BASE.exists()or HELPER.exists():raise SystemExit('Existing mail preview preserved')
    template=ROOT/'workspace/sandbox/votes-test-v1';before=snapshot(template);(PRIVATE/'mail-template-before-v1.json').write_text(json.dumps(before,indent=2))
    BASE.mkdir(parents=True)
    for name in ['Dolphin-x64','user']:shutil.copytree(template/name,BASE/name,ignore=shutil.ignore_patterns('Logs','Cache','ScreenShots','StateSaves'))
    shutil.copy2(template/'NetProbe.exe',BASE/'NetProbe.exe');shutil.copy2(candidate/'preview.dol',BASE/'preview.dol')
    cfg=BASE/'user/Config/Dolphin.ini';data=configparser.ConfigParser(strict=False);data.optionxform=str;data.read(cfg,encoding='utf-8-sig')
    for section in data.sections():
        for key,value in data[section].items():data[section][key]=value.replace(str(template),str(BASE)).replace(template.as_posix(),BASE.as_posix())
    data['Core']['DefaultISO']='';data['Core']['EnableWiiLink']='False'
    for key in ['WiiSDCard','WiiSDCardEnableFolderSync','WiiSDCardAllowWrites']:data['Core'][key]='False'
    with cfg.open('w',encoding='utf-8')as file:data.write(file)
    cfg=BASE/'user/Config/WiimoteNew.ini';data=configparser.ConfigParser(strict=False);data.optionxform=str;data.read(cfg,encoding='utf-8-sig');data['Wiimote1'].pop('Buttons/Plus',None);data['Wiimote1']['Buttons/+']='E'
    with cfg.open('w',encoding='utf-8')as file:data.write(file)
    register();launcher.scrub_download_tasks(PROFILE);launcher.validate(PROFILE)
    text=(ROOT/'scripts/FeedRunner.cs').read_text();text=text.replace('class FeedRunner','class MailPreviewRunner')
    old='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","news-v1"),StringComparison.OrdinalIgnoreCase);'
    new='bool approved=String.Equals(root,Path.Combine(project,"workspace","sandbox","mail-test-v1"),StringComparison.OrdinalIgnoreCase);'
    start=text.index('   if(args.Length!=3||args[2]!="0001000248414745"');end=text.index('   File.WriteAllText(Path.Combine(root,"child-exit.json")')
    block='''   if(args.Length!=2||args[1]!="preview")throw new Exception("Only incapable mail preview is supported");
   string exe=Path.Combine(root,"Dolphin-x64","Dolphin.exe");string user=Path.Combine(root,"user");
   string dol=Path.Combine(root,"preview.dol");if(!File.Exists(dol))throw new Exception("Preview missing");
   int childCode=Run(sid,exe,"--user "+Quote(user)+" --exec "+Quote(dol),Path.GetDirectoryName(exe));
'''
    if text.count(old)!=1:raise ValueError('Mail helper source guard differs')
    text=text[:start].replace(old,new)+block+text[end:];HELPER.mkdir(parents=True)
    source=HELPER/'MailPreviewRunner.cs';source.write_text(text,encoding='utf-8');compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(HELPER/'MailPreviewRunner.exe'),str(source)],check=True,capture_output=True)
    locked=[BASE/'Dolphin-x64/Dolphin.exe',BASE/'NetProbe.exe',BASE/'preview.dol',source,HELPER/'MailPreviewRunner.exe']
    (ROOT/'configs/wii-mail-preview.lock.json').write_text(json.dumps(dict(profile=PROFILE,capability_count=0,external_registration_allowed=False,files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256(p))for p in locked]),indent=2))
    catalog=ROOT/'configs/channels.catalog.json';data=json.loads(catalog.read_text(encoding='utf-8'));data['test_beds'].append(dict(profile='mail-test-v1',purpose='incapable Korean mail tool preview; no registration/config writes'))
    catalog.write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    if snapshot(template)!=before:raise ValueError('Mail preview template changed')
    print('Prepared incapable mail preview: sanitized profile, capability zero, no SD or registration, template preserved')
if __name__=='__main__':main()
