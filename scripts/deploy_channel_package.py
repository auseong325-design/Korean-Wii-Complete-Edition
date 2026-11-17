"""Back up and copy channel-only files; never touches Priiloader/DVD/state/logs."""
import json,os,shutil
from pathlib import Path
from audit_sd import PRIVATE,sha256
from kwce.channel_hardware import sd_files
from deploy_dvd_package import guarded,inventory

def replace_verified(target,data):
    """Keep the existing target intact until its new sibling passes read-back."""
    target=Path(target)
    staged=target.with_name(target.name+'.kwce-new')
    with staged.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if staged.read_bytes()!=data:
        raise ValueError('Staged SD read-back differs; original target retained')
    os.replace(staged,target)

def deploy(package,card,dry_run=False,*,verifier=sd_files,extra_backup=()):
    package=Path(package).resolve();card=Path(card).resolve();_,files=verifier(package)
    plan=[(source,relative,source.read_bytes())for source,relative in files]
    for _,relative,_ in plan:
        target=guarded(card,relative)
        staged=guarded(card,relative+'.kwce-new')
        if staged.exists():raise ValueError('Existing SD staging file preserved; inspect before retry')
    changed=[(s,r,b)for s,r,b in plan if not(card/r).exists()or(card/r).read_bytes()!=b]
    extra_backup=tuple(extra_backup)
    for relative in extra_backup:guarded(card,relative)
    required=sum(len(b)+((card/r).stat().st_size if(card/r).exists()else 0)for _,r,b in changed)
    required+=sum((card/r).stat().st_size for r in extra_backup if (card/r).is_file() and r not in {x[1] for x in changed})
    if required+64*2**20>shutil.disk_usage(card).free:raise ValueError('SD free space insufficient including backups')
    if dry_run:
        print(f'PASS: package verified; {len(changed)} writes, backups first; only verifier-approved paths');return
    n=1
    while(PRIVATE/f'channel-sd-deploy-{n}').exists():n+=1
    local=PRIVATE/f'channel-sd-deploy-{n}';local.mkdir(parents=True)
    before,skipped=inventory(card);(local/'before.json').write_text(json.dumps(dict(files=before,skipped=skipped)),encoding='utf-8')
    backup_relative=f'kwce-deploy-backups/{package.name}-{n}';backup=guarded(card,backup_relative)
    if backup.exists():raise ValueError('Existing channel backup preserved')
    backup.mkdir(parents=True);old=[]
    for _,relative,_ in changed:
        target=guarded(card,relative)
        if target.exists():
            dest=guarded(card,backup_relative+'/'+relative);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,dest)
            if sha256(dest)!=sha256(target):raise ValueError('Channel backup verify failed')
            old.append(dict(path=relative,sha256=sha256(target)))
    for relative in extra_backup:
        target=guarded(card,relative)
        if target.is_file() and not any(x['path']==relative for x in old):
            dest=guarded(card,backup_relative+'/'+relative);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,dest)
            if sha256(dest)!=sha256(target):raise ValueError('Settings backup verify failed')
            old.append(dict(path=relative,sha256=sha256(target)))
    (backup/'backup-manifest.json').write_text(json.dumps(dict(package=package.name,files=old),indent=2),encoding='utf-8')
    for _,relative,data in changed:
        target=guarded(card,relative);target.parent.mkdir(parents=True,exist_ok=True)
        replace_verified(target,data)
    for _,relative,data in plan:
        if(card/relative).read_bytes()!=data:raise ValueError('Channel SD read-back verify failed')
    after,after_skipped=inventory(card)
    # FAT32 is case-insensitive: an existing WAD/ directory may be requested
    # as wad/. Compare canonicalized names, while rejecting ambiguous aliases.
    def folded(rows):
        result={}
        for name,value in rows.items():
            key=name.casefold()
            if key in result:raise ValueError('Ambiguous case-insensitive SD paths')
            result[key]=value
        return result
    before_folded,after_folded=folded(before),folded(after)
    allowed={r.casefold() for _,r,_ in changed}
    backup_prefix=backup_relative.casefold()+'/'
    if skipped!=after_skipped or any(r not in after_folded for r in before_folded)or any(before_folded[r]!=after_folded[r]for r in before_folded if r not in allowed)or any(r not in before_folded and r not in allowed and not r.startswith(backup_prefix)for r in after_folded):raise ValueError('Unexpected SD change; private evidence retained')
    result=dict(package=package.name,written_files=len(changed),verified_files=len(plan),backed_up_files=len(old),backup=backup_relative,original_files_missing=0,unplanned_changes=0,console_executed=False)
    (local/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'PASS: {package.name} copied; {len(changed)} written, {len(old)} backed up, {len(plan)} verified, missing0/unplanned0')
    print('SD backup: '+backup_relative)
