"""DVD-only branch of deploy_to_sd.py; existing SD files are never deleted."""
import json,os,shutil
from pathlib import Path
from audit_sd import ROOT,PRIVATE,sha256
from kwce.dvd_hardware import sd_files,merge_hacks

def guarded(card,relative):
    card=Path(card).resolve();target=card/relative
    if not target.resolve().is_relative_to(card):raise ValueError('DVD SD target escapes card')
    p=target
    while p!=card:
        if p.exists() and (p.is_symlink() or p.is_junction() or getattr(p.lstat(),'st_file_attributes',0)&0x400):raise ValueError('Refusing DVD SD reparse path')
        p=p.parent
    return target

def inventory(card):
    result={};skipped=[]
    def inaccessible(error):skipped.append(str(error.filename))
    for base,dirs,files in os.walk(card,onerror=inaccessible):
        for name in dirs:
            p=Path(base)/name
            if p.is_symlink() or p.is_junction():raise ValueError('Refusing SD reparse inventory')
        for name in files:
            p=Path(base)/name
            if p.is_symlink() or p.is_junction():raise ValueError('Refusing SD reparse inventory')
            s=p.stat();result[p.relative_to(card).as_posix()]=[s.st_size,s.st_mtime_ns]
    return result,skipped

def deploy(package,card,dry_run=False):
    package=Path(package).resolve();card=Path(card).resolve();record,files=sd_files(package)
    if record.get('kind')in {'dvd-only-r25','dvd-only-r26'}:
        raise ValueError('R25/R26 SD deployment withdrawn: legacy Priiloader loses patch bytes; use R27')
    if (card/'kwce/dvd/test-disc.iso').exists():raise ValueError('An SD test ISO would override the optical DVD path; card preserved')
    hack_relative='apps/Priiloader/hacks_hash.ini';hack=guarded(card,hack_relative)
    merged=merge_hacks(hack.read_bytes(),(package/'priiloader/kwce-hacks.ini').read_bytes())
    plan=[(source,relative,source.read_bytes())for source,relative in files]
    plan.append((None,hack_relative,merged))
    for _,relative,_ in plan:guarded(card,relative)
    changed=[(source,relative,data)for source,relative,data in plan if not(card/relative).exists()or(card/relative).read_bytes()!=data]
    required=sum(len(data)+(card/relative).stat().st_size if(card/relative).exists()else len(data)for _,relative,data in changed)
    if required+64*2**20>shutil.disk_usage(card).free:raise ValueError('Insufficient SD free space including backups')
    if dry_run:
        print(f'PASS: DVD package verified; {len(changed)} SD writes, isolated DVD app/data, backup before overwrite')
        for _,relative,_ in changed:print('write '+relative)
        return
    number=1
    while(PRIVATE/f'dvd-sd-deploy-{number}').exists():number+=1
    local=PRIVATE/f'dvd-sd-deploy-{number}';local.mkdir()
    before,skipped=inventory(card);(local/'before.json').write_text(json.dumps(dict(files=before,skipped=skipped)),encoding='utf-8')
    backup_relative=f'kwce-deploy-backups/{package.name}-{number}'
    backup=guarded(card,backup_relative)
    if backup.exists():raise ValueError('Existing SD deployment backup preserved')
    backup.mkdir(parents=True)
    old=[]
    # Save every overwritten file before performing the first payload write.
    for _,relative,data in changed:
        target=guarded(card,relative)
        if target.exists():
            dest=guarded(card,backup_relative+'/'+relative);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,dest)
            if sha256(dest)!=sha256(target):raise ValueError('DVD SD backup verification failed')
            old.append(dict(path=relative,sha256=sha256(target),bytes=target.stat().st_size))
    (backup/'backup-manifest.json').write_text(json.dumps(dict(package=package.name,files=old),indent=2),encoding='utf-8')
    for source,relative,data in changed:
        target=guarded(card,relative);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb'if target.exists()else'xb')as f:f.write(data)
        if target.read_bytes()!=data:raise ValueError('DVD SD read-back verification failed')
    # Validate the whole destination payload, including unchanged files.
    for _,relative,data in plan:
        if (card/relative).read_bytes()!=data:raise ValueError('DVD SD payload verification failed')
    after,after_skipped=inventory(card);allowed={relative for _,relative,_ in changed}
    if after_skipped!=skipped:raise ValueError('SD inventory readability changed during deployment')
    missing=[p for p in before if p not in after]
    unexpected=[p for p in before if p in after and before[p]!=after[p] and p not in allowed]
    added=[p for p in after if p not in before and p not in allowed and not p.startswith(backup_relative+'/')]
    if missing or unexpected or added:raise ValueError('Unexpected SD file change; private evidence retained')
    result=dict(package=package.name,written_files=len(changed),verified_files=len(plan),backed_up_files=len(old),backup=backup_relative,original_files_inventoried=len(before),original_files_missing=0,unplanned_changes=0,unreadable_inventory_paths=len(skipped),protected_existing_files_preserved=True,console_executed=False,drive=str(card))
    (local/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'PASS: {package.name} copied and read-back verified; files {len(changed)}, backups {len(old)}, missing 0, unplanned changes 0')
    print('SD backup: '+backup_relative)
