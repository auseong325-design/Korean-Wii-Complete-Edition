"""Crop native 4:3 local captures; retain sources and record HUD composites."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kwce.channels import sha256,load_library


def main():
    load_library()
    from PIL import Image
    source=ROOT/'workspace/private/evidence/forecast-manual-v23'
    target=ROOT/'workspace/channels/forecast/work/manual-captures/v23'
    if target.exists():raise SystemExit('Existing captures preserved')
    target.mkdir()
    entries=[]
    choices={
        'current':('current-clean',None),
        'nearby-weather':('nearby-weather','nearby-weather-bars'),
        'nearby-temp':('nearby-temp-selected','nearby-temp-bars'),
        'other-city':('other-city',None),
        'regional-zoom':('regional-zoom-bars',None),
        'globe-world':('globe-world',None),
        'globe-screen':('globe-screen-bars',None),
        'settings':('settings',None),
    }
    for name,(base,bars)in choices.items():
        paths=[source/(stem+'.jpg')for stem in [base,bars]if stem]
        pictures=[]
        for p in paths:
            im=Image.open(p).convert('RGB')
            if im.size!=(642,512):raise ValueError('Unexpected native capture dimensions')
            pictures.append(im.crop((1,31,641,511)))
        result=pictures[0]
        if bars:
            # Same UI state and map: expose the genuine control bars without
            # the OS pointer that was over the map in the second capture.
            for box in [(0,0,640,70),(0,414,640,480)]:result.paste(pictures[1].crop(box),box[:2])
        result.save(target/(name+'.png'))
        entries.append(dict(file=name+'.png',sha256=sha256((target/(name+'.png')).read_bytes()),crop=[1,31,641,511],size=[640,480],sources=[dict(alias=p.name,sha256=sha256(p.read_bytes()))for p in paths],hud_bands=[[0,0,640,70],[0,414,640,480]]if bars else []))
    (target/'capture-manifest.json').write_text(json.dumps(dict(schema=1,runtime_revision=22,historical_utc='2026-10-23T05:00:30+00:00',real_time_weather=False,entries=entries),indent=2))
    config=ROOT/'configs/forecast-manual-ko.json'
    snapshot=ROOT/'workspace/channels/forecast/forecast-manual-ko_v22_snapshot.json'
    if snapshot.exists():raise SystemExit('Existing config snapshot preserved')
    snapshot.write_bytes(config.read_bytes())
    data=json.loads(config.read_text(encoding='utf-8'))
    for spec in data['images'].values():
        for shot in spec.get('shots',[]):shot['capture']='v23/'+Path(shot['capture']).stem+'.png'
    data['captures']='private native 640x480 4:3 Dolphin v22 UI captures; historical 2026-10-23T05:00:30Z cache preview; v23/capture-manifest.json'
    config.write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print('Prepared 8 native 4:3 captures; preserved v22 config and all source captures')


if __name__=='__main__':main()
