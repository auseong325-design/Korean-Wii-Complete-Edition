"""Select a reproducible UI fixture in the stopped review profile only."""
import argparse,configparser,datetime,json,shutil,struct,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped
sys.path.insert(0,str(ROOT))
from kwce.forecast_scenarios import SCENARIOS,fixture,public_city_key
from kwce.forecast_cache import public_source,inspect_public_download
from kwce.forecast_data import localize_forecast,forecast_mapping
from kwce.channel_vff import VFF


def main():
    ap=argparse.ArgumentParser();ap.add_argument('scenario',choices=SCENARIOS);args=ap.parse_args();stopped()
    runtime=ROOT/'workspace/sandbox/forecast-review-v1';user=runtime/'user'
    binding=json.loads((ROOT/'configs/forecast-cache-profiles.lock.json').read_text())['profiles'][runtime.name]
    out=ROOT/'workspace/channels/forecast/local-feed-v2'
    if not out.exists():
        out.mkdir();records={}
        long_payload,_=localize_forecast(public_source('forecast',binding).read_bytes()[320:],forecast_mapping())
        missing_key=public_city_key(long_payload)
        for scenario in SCENARIOS:
            files={}
            for kind in ('forecast','short'):
                raw=public_source(kind,binding).read_bytes();payload=raw[320:]
                if kind=='forecast':payload,_=localize_forecast(payload,forecast_mapping())
                result=fixture(payload,kind,scenario,missing_key=missing_key);p=out/f'{scenario}-{kind}.bin';p.write_bytes(result)
                files[kind]=dict(file=p.name,sha256=sha256(p))
            record=inspect_public_download(public_source('forecast',binding).read_bytes(),'forecast')
            instant=datetime.datetime.fromisoformat(record['opened_utc'])+datetime.timedelta(seconds=30,
                minutes=720 if scenario=='clock-pm'else 120 if scenario=='expired'else 0)
            records[scenario]=dict(files=files,rtc=int(instant.timestamp()),synthetic=scenario!='public')
        (out/'manifest.json').write_text(json.dumps(dict(schema=1,source_binding=binding,scenarios=records,
            purpose='Local UI verification only; historical or synthetic data, no live weather or emulator network success'),indent=2))
    manifest=json.loads((out/'manifest.json').read_text());row=manifest['scenarios'][args.scenario]
    if manifest['source_binding']!=binding:raise ValueError('Fixture source binding changed')
    for info in row['files'].values():
        if sha256(out/info['file'])!=info['sha256']:raise ValueError('Immutable fixture changed')
    vffpath=user/'Wii/title/00010002/48414645/data/wc24dl.vff';ini=user/'Config/Dolphin.ini'
    n=1
    while (PRIVATE/f'forecast-review-before-scenario-{n}').exists():n+=1
    backup=PRIVATE/f'forecast-review-before-scenario-{n}';backup.mkdir()
    shutil.copy2(vffpath,backup/'wc24dl.vff');shutil.copy2(ini,backup/'Dolphin.ini')
    active=runtime/'active-scenario.json'
    if active.exists():shutil.copy2(active,backup/'active-scenario.json')
    vff=VFF((PRIVATE/'forecast-empty-vff-before-public-replay.bin').read_bytes())
    if vff.entries():raise ValueError('Expected preserved empty VFF template')
    for name,kind in [('3.bin','forecast'),('4.bin','short')]:vff=VFF(vff.add(name,(out/row['files'][kind]['file']).read_bytes()))
    vffpath.write_bytes(vff.data)
    c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(ini,encoding='utf-8-sig')
    c['Core']['EnableCustomRTC']='True';c['Core']['CustomRTCValue']=str(row['rtc'])
    with ini.open('w',encoding='utf-8')as stream:c.write(stream)
    active.write_text(json.dumps(dict(feed=out.name,scenario=args.scenario,manifest_sha256=sha256(out/'manifest.json'))))
    print('Prepared review-only',args.scenario,'fixture; prior runtime cache/config preserved as attempt',n)


if __name__=='__main__':main()
