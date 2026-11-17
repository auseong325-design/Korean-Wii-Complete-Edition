"""Replay downloaded public country-136 files inside the isolated test NAND."""
import argparse,datetime,json,shutil,struct,subprocess,sys,time
from audit_sd import ROOT,PRIVATE,sha256
sys.path.insert(0,str(ROOT))
from kwce.channel_vff import VFF
from prepare_forecast import register
from forecast_profile import public_forecast_task,scrub_channel,validate_channel

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=int,default=2);ap.add_argument('--localized',action='store_true');ap.add_argument('--current',action='store_true');ap.add_argument('--offline',action='store_true',help='current profile only: freeze the test clock inside the saved public snapshot');ap.add_argument('--raw-english',dest='raw_english',action='store_true',help='current profile only: seed RAW English supply data (PC conversion disabled) so build-v104 proves the in-channel runtime conversion');args=ap.parse_args()
    if args.offline and not args.current:raise SystemExit('Offline mode requires the independent current profile')
    if args.raw_english and args.localized:raise SystemExit('--raw-english disables the PC conversion; do not combine it with --localized')
    if args.current and not args.localized and not args.raw_english:raise SystemExit('Current Korean profile requires the localized data overlay')
    if not args.current and(ROOT/'workspace/sandbox/forecast-v2/current-profile.json').exists():raise SystemExit('Legacy v22 profile is preserved; select --current')
    if not 2<=args.attempt<=100:raise SystemExit('Invalid replay attempt')
    if 'dolphin.exe'in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin before seeding cache')
    alias='forecast-v2'if args.current else'forecast-v1';runtime=ROOT/'workspace/sandbox'/alias
    for part in(runtime,*runtime.parents):
        if part==ROOT.parent:break
        if part.is_symlink()or part.is_junction():raise ValueError('Indirect forecast profile refused')
    register()
    if args.current:
        import launch_dolphin as launcher
        launcher.NATIVE_PROFILES['forecast-v1-user']=runtime.relative_to(ROOT).as_posix()
        from forecast_review_tasks import review_tasks
        review_tasks(profile=alias)
    p=runtime/'user/Wii/title/00010002/48414645/data/wc24dl.vff'
    for file in[p,runtime/'user/Wii/shared2/wc24/nwc24dl.bin',runtime/'user/Config/Dolphin.ini',runtime/'cache-mode.json',runtime/'cache-snapshot.json']:
        for part in(file,*file.parents):
            if part==ROOT.parent:break
            if part.is_symlink()or part.is_junction():raise ValueError('Indirect cache target refused')
    if not p.resolve().is_relative_to(runtime.resolve()):raise ValueError('Unexpected VFF target')
    backup=PRIVATE/f'forecast-{"current-"if args.current else""}before-sdk-replay-{args.attempt}'
    if backup.exists():raise SystemExit('Existing replay snapshot preserved')
    backup.mkdir();shutil.copy2(p,backup/'wc24dl.vff')
    # Explicit resolved path guards the test NAND and avoids parent ambiguity.
    dlpath=runtime/'user/Wii/shared2/wc24/nwc24dl.bin'
    shutil.copy2(dlpath,backup/'nwc24dl.bin');dl=bytearray(dlpath.read_bytes())
    empty=PRIVATE/'forecast-empty-vff-before-public-replay.bin'
    vff=VFF(empty.read_bytes())
    if vff.entries():raise ValueError('Expected saved empty experimental VFF')
    binding=None
    if args.current:
        binding=json.loads((runtime/'cache-snapshot.json'if args.offline else ROOT/'workspace/channels/forecast/references/active-public-snapshot.json').read_text())
    rows=[];now=int(time.time()//60)
    for i in range(120):
        off=2048+512*i;entry=dl[off:off+512]
        if not public_forecast_task(entry):continue
        if int.from_bytes(entry[4:8],'big')&8:raise ValueError('Encrypted cache replay is unsupported')
        url=entry[180:416].split(b'\0')[0];kind='forecast'if url.endswith(b'/forecast.bin')else'short'
        name=entry[416:480].split(b'\0')[0].decode('ascii')
        if name!=f'{i}.bin':raise ValueError('Unexpected Forecast task filename')
        from kwce.forecast_cache import public_source
        source=public_source(kind,binding);data=source.read_bytes()
        if len(data)<=320:raise ValueError('Missing WC24 envelope')
        # The pinned Dolphin KD source strips this envelope for signed,
        # unencrypted downloads. It does not implement RSA verification here.
        payload=data[320:];overlay=None
        if args.localized and kind=='forecast':
            from kwce.forecast_data import localize_forecast
            from kwce.forecast_data import forecast_mapping
            mapping=forecast_mapping()
            payload,overlay=localize_forecast(payload,mapping)
        vff=VFF(vff.add(name,payload));rows.append(dict(alias=name,kind=kind,size=len(payload),source_sha256=sha256(source),envelope_removed=320,overlay=overlay))
        struct.pack_into('>I',dl,off+48,now);struct.pack_into('>i',dl,off+32,0);struct.pack_into('>H',dl,off+26,0)
        struct.pack_into('>II',dl,128+16*i+4,now+60,now)
    if len(rows)!=2:raise ValueError('Expected two public country-136 tasks')
    image=bytearray(vff.data);date=datetime.datetime.now();fat_date=((date.year-1980)<<9)|(date.month<<5)|date.day;fat_time=(date.hour<<11)|(date.minute<<5)|(date.second//2)
    for at in range(vff.root,vff.root+4096,32):
        if image[at]==0:break
        struct.pack_into('<HH',image,at+22,fat_time,fat_date)
    p.write_bytes(image);dlpath.write_bytes(dl);scrub_channel();validate_channel()
    mode=runtime/'cache-mode.json'if args.current else ROOT/'workspace/channels/forecast/cache-mode.json'
    mode.write_text(json.dumps(dict(localized=args.localized)))
    if args.current:
        import configparser
        ini=runtime/'user/Config/Dolphin.ini';shutil.copy2(ini,backup/'Dolphin.ini')
        c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(ini,encoding='utf-8-sig')
        c['Core']['EnableCustomRTC']='True'if args.offline else'False'
        if args.offline:
            from kwce.forecast_cache import inspect_public_download,valid_at
            reports=[inspect_public_download(public_source(k,binding).read_bytes(),k)for k in ['forecast','short']]
            instant=max(datetime.datetime.fromisoformat(r['opened_utc'])for r in reports)+datetime.timedelta(seconds=30)
            if not all(valid_at(r,instant)for r in reports):raise ValueError('Saved public snapshots do not share a valid test time')
            c['Core']['CustomRTCValue']=str(int(instant.timestamp()))
        with ini.open('w',encoding='utf-8')as stream:c.write(stream)
        (runtime/'cache-snapshot.json').write_text(json.dumps(binding))
    result=dict(profile=alias,country=136,language_data=1,historical_offline=args.offline,pc_conversion_disabled=args.raw_english,method='Public snapshots in isolated replay; not emulator network success',files=rows)
    (PRIVATE/f'forecast-{"current-"if args.current else""}sdk-cache-replay-{args.attempt}.json').write_text(json.dumps(result,indent=2));print('Prepared',alias,'localized public cache; offline historical clock'if args.offline else'public cache with normal clock')

if __name__=='__main__':main()
