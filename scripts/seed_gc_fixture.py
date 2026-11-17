"""Seed new fixture paths while Dolphin is stopped; never overwrites saves."""
import sys,subprocess,configparser,json
from pathlib import Path
from audit_sd import ROOT
sys.path.insert(0,str(ROOT))
from kwce.gc_fixture import card_header,gci_fixture

if 'dolphin.exe' in subprocess.run(['tasklist','/FI','IMAGENAME eq Dolphin.exe','/FO','CSV','/NH'],capture_output=True,text=True).stdout.lower():raise SystemExit('Close Dolphin')
user=ROOT/'workspace/sandbox/gc-v2/user'
for slot in ['A','B']:
    folder=user/f'GC/Card {slot}/JPN';folder.mkdir(parents=True,exist_ok=True)
    p=folder/'MC_SYSTEM_AREA'
    with p.open('xb') as f:f.write(card_header())
    if slot=='A':
        with (folder/'00-KWCE-KWCE-SYNTH-TEST.gci').open('xb') as f:f.write(gci_fixture())
cfg=user/'Config/Dolphin.ini';c=configparser.ConfigParser(strict=False);c.optionxform=str;c.read(cfg,encoding='utf-8');c['Core']['MemoryCardSize']='0'
for slot in ['A','B']:c['Core'][f'GCIFolder{slot}PathOverride']=str(user/f'GC/Card {slot}/JPN')
with cfg.open('w',encoding='utf-8') as f:c.write(f)
print(json.dumps(dict(synthetic_cards=2,synthetic_saves=1,encoding='ANSI',real_save_data_used=False)))
