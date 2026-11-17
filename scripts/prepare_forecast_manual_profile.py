"""Prepare an isolated 4:3 historical UI capture profile; preserve Forecast v22."""
import configparser,datetime,json,re,shutil,struct,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
from prepare_forecast import register
from forecast_profile import validate_channel
sys.path.insert(0,str(ROOT))
from kwce.forecast_cache import public_source,inspect_public_download

TARGET=ROOT/'workspace/sandbox/forecast-manual-v1'


def main():
    stopped();register();validate_channel()
    if TARGET.exists():raise SystemExit('Existing capture profile preserved')
    source=ROOT/'workspace/sandbox/forecast-v1'
    for p in source.rglob('*'):
        if p.is_symlink()or p.is_junction()or p.lstat().st_file_attributes&0x400:raise SystemExit('Indirect source path refused')
    reports=[inspect_public_download(public_source(k).read_bytes(),k)for k in ['forecast','short']]
    opened=max(datetime.datetime.fromisoformat(r['opened_utc'])for r in reports)
    closed=min(datetime.datetime.fromisoformat(r['closed_utc'])for r in reports)
    instant=opened+datetime.timedelta(seconds=30)
    if not instant<closed:raise SystemExit('Public capture snapshots have no common valid time')
    before=snapshot(source);manifest=PRIVATE/'forecast-v22-before-manual-profile.json'
    if manifest.exists():
        if json.loads(manifest.read_text())!=before:raise SystemExit('Original profile differs from preserved before manifest')
    else:manifest.write_text(json.dumps(before,indent=2))
    TARGET.mkdir()
    for folder in ['user','Dolphin-x64','Dolphin-replay-x64']:
        shutil.copytree(source/folder,TARGET/folder,ignore=shutil.ignore_patterns('Cache','Logs','ScreenShots','StateSaves'))
    shutil.copy2(source/'NetProbe.exe',TARGET/'NetProbe.exe')
    for name in ['Dolphin.ini','GFX.ini']:
        p=TARGET/'user/Config'/name;c=configparser.ConfigParser(strict=False);c.optionxform=str
        c.read_string(p.read_text(encoding='utf-8-sig').replace(str(source),str(TARGET)))
        if name=='Dolphin.ini':
            if not c.has_section('Display'):c.add_section('Display')
            c['Core']['DefaultISO']='';c['Core']['EnableCustomRTC']='True';c['Core']['CustomRTCValue']=str(int(instant.timestamp()))
            c['Display']['Fullscreen']='False';c['Display']['RenderWindowWidth']='800';c['Display']['RenderWindowHeight']='600'
        else:
            c['Settings']['AspectRatio']='2';c['Settings']['ShowFPS']='False';c['Settings']['ShowSpeed']='False'
        with p.open('w',encoding='utf-8')as stream:c.write(stream)
    p=TARGET/'user/Wii/shared2/sys/SYSCONF';data=bytearray(p.read_bytes());hits=0
    for i in range(int.from_bytes(data[4:6],'big')):
        at=int.from_bytes(data[6+2*i:8+2*i],'big');length=(data[at]&31)+1
        if data[at+1:at+1+length]==b'IPL.AR':
            if data[at]>>5!=3:raise ValueError('Unexpected aspect setting type')
            data[at+1+length]=0;hits+=1
    if hits!=1:raise ValueError('Aspect setting identity')
    p.write_bytes(data)
    controls=TARGET/'user/Config/WiimoteNew.ini';text=controls.read_text(encoding='utf-8-sig')
    for key,value in [('Buttons/B','X'),('Buttons/Home','RETURN | pulse(`Click 1`, 0.25)'),('D-Pad/Down','DOWN | pulse(`Click 2`, 0.4)'),('Shake/X',''),('Shake/Y',''),('Shake/Z','')]:
        text=re.sub(r'^'+re.escape(key)+r'\s*=.*$',key+' = '+value,text,flags=re.M)
    controls.write_text(text,encoding='utf-8')
    active=json.loads((ROOT/'workspace/channels/forecast/active-build.json').read_text())
    (TARGET/'active-build.json').write_text(json.dumps(active))
    (TARGET/'capture-profile.json').write_text(json.dumps(dict(schema=1,purpose='historical-4:3-manual-capture',historical_utc=instant.isoformat(),real_time_weather=False,original_profile_preserved=True)))
    if snapshot(source)!=before:raise ValueError('Original Forecast profile changed')
    print('Prepared separate 4:3 historical manual profile; original Forecast profile unchanged')


if __name__=='__main__':main()
