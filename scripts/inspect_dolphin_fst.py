"""Project-only read-only FST/rename diagnostics; scalar output only."""
import argparse,json,sys
from pathlib import Path
from audit_sd import ROOT,PRIVATE
sys.path.insert(0,str(ROOT))
from kwce.dolphin_fst import inspect_fst

def inspect_profile(profile):
    if profile not in ['gc-native-v5-user','gc-native-v6-user']:raise ValueError('Unsupported FST diagnostic profile')
    rev=profile.split('-')[2];runtime=ROOT/f'workspace/sandbox/gc-{rev}';wii=runtime/'user/Wii'
    result=inspect_fst((wii/'fst.bin').read_bytes())
    temp=wii/'fst.bin.xxx';result['temporary_fst_exists']=temp.exists()
    if temp.exists():result['temporary_fst']=inspect_fst(temp.read_bytes())
    log=runtime/'user/Logs/dolphin.log';counts=dict(rename_access_denied=0,rename_other_error=0,final_rename_failure=0,fst_parse_errors=0)
    if log.exists():
        for line in log.read_text(encoding='utf-8',errors='replace').splitlines():
            if 'FileUtil.cpp' in line and 'failed:' in line and 'fst.bin' in line:
                counts['rename_access_denied' if 'Access is denied.' in line else 'rename_other_error']+=1
            if 'Failed to parse FST' in line:counts['fst_parse_errors']+=1
            if 'Failed to rename temporary FST file' in line:counts['final_rename_failure']+=1
    return dict(profile=profile,fst=result,log_counts=counts,read_only=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--profile',choices=['gc-native-v5-user','gc-native-v6-user'],default='gc-native-v6-user');args=ap.parse_args()
    result=inspect_profile(args.profile);PRIVATE.mkdir(exist_ok=True)
    (PRIVATE/f'{args.profile}-fst-inspection.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__':main()
