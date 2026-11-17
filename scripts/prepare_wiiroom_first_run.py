"""Archive this synthetic test title's data and clear its host-FST children.

Only the stopped, registered project Room profile is accepted. No original,
hardware NAND, system title, SD or other channel's data is changed.
"""
import argparse,json,shutil,struct
from audit_sd import ROOT,PRIVATE
from prepare_channel_access import stopped
from prepare_wiiroom_test import PROFILE,register
import launch_dolphin as launcher
from kwce.dolphin_fst import inspect_fst

def empty_title_data_fst(data):
    inspect_fst(data);cursor=0;removed=0
    def visit(parent):
        nonlocal cursor,removed
        at=cursor;row=bytearray(data[at*32:(at+1)*32]);cursor+=1
        name=row[:12].split(b'\0')[0].decode('ascii');path='/'if name=='/'else parent.rstrip('/')+'/'+name
        children=struct.unpack_from('>I',row,28)[0];parts=[visit(path)for _ in range(children)]
        if path=='/title/00010001/4843494a/data':
            removed=sum(len(p)//32 for p in parts);struct.pack_into('>I',row,28,0);parts=[]
        return bytes(row)+b''.join(parts)
    result=visit('');inspect_fst(result)
    if not removed:raise ValueError('Expected existing synthetic Room save')
    return result,removed

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restore',type=int);args=parser.parse_args()
    stopped();register();user=launcher.user_path(PROFILE)
    expected=(ROOT/'workspace/sandbox/wiiroom-test-v1/user').resolve()
    if user.resolve()!=expected:raise ValueError('Unexpected test profile')
    target=user/'Wii/title/00010001/4843494a/data';fst=user/'Wii/fst.bin'
    for part in [target,*target.parents]:
        if part.is_symlink()or part.is_junction():raise ValueError('Indirect synthetic data path')
        if part==user:break
    if target.is_symlink()or target.is_junction()or not target.is_dir():raise ValueError('Unexpected synthetic data')
    if args.restore is not None:
        if not 1<=args.restore<=100:raise ValueError('Backup number bounds')
        backup=PRIVATE/f'wiiroom-before-first-run-{args.restore}'
        meta=json.loads((backup/'scope.json').read_text())
        if meta.get('profile')!='wiiroom-test-v1'or not meta.get('title_data_only'):raise ValueError('Backup scope')
        result=backup/'test-result-data'
        if result.exists()or not(backup/'data').is_dir():raise ValueError('Backup already restored or missing')
        if not target.resolve().is_relative_to(expected)or not result.resolve().is_relative_to(PRIVATE.resolve()):raise ValueError('Unsafe data move')
        target.rename(result);shutil.copytree(backup/'data',target);shutil.copy2(backup/'fst.bin',fst)
        print('Prior synthetic Room data/FST restored; first-run result archived');return
    rebuilt,count=empty_title_data_fst(fst.read_bytes());number=1
    while(PRIVATE/f'wiiroom-before-first-run-{number}').exists():number+=1
    backup=PRIVATE/f'wiiroom-before-first-run-{number}';backup.mkdir()
    if not target.resolve().is_relative_to(expected)or not backup.resolve().is_relative_to(PRIVATE.resolve()):raise ValueError('Unsafe first-run data move')
    shutil.copy2(fst,backup/'fst.bin');target.rename(backup/'data');target.mkdir();fst.write_bytes(rebuilt)
    (backup/'scope.json').write_text(json.dumps(dict(profile='wiiroom-test-v1',title_data_only=True,removed_fst_records=count)))
    print('Synthetic Room first-run state prepared; prior data/FST archived, other title data untouched')
if __name__=='__main__':main()
