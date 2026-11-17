"""New raw-card cross-check; separate from the preserved GCI fixture."""
import sys,subprocess,configparser,json
from audit_sd import ROOT
sys.path.insert(0,str(ROOT))
from kwce.gc_fixture import raw_card
if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin')
user=ROOT/'workspace/sandbox/gc-v2/user';cfg=user/'Config/Dolphin.ini'
c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(cfg,encoding='utf-8')
for slot in ['A','B']:
    p=user/f'GC/native-card-{slot}.JAP.59.raw'
    with p.open('xb') as f:f.write(raw_card(slot=='A'))
    c['Core'][f'Slot{slot}']='1';c['Core'][f'Memcard{slot}Path']=str(user/f'GC/native-card-{slot}.JAP.raw')
with cfg.open('w',encoding='utf-8') as f:c.write(f)
print(json.dumps(dict(new_raw_cards=2,size_bytes=524288,synthetic_save_only=True)))
