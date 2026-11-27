"""Copy a KWCE hardware package onto the user's SD card (explicit drive only).

Writes only: apps/kwce-installer/, kwce/<channel>/ WADs, kwce/packages.txt,
KWCE-README-ko.txt, package-manifest.json, and rewrites
apps/Priiloader/hacks_hash.ini (first backed up as hacks_hash.ini.before-kwce) as the
sections the installed Priiloader can parse plus the KWCE sections.
kwce/state/ and kwce/log.txt (restore records from the console) are never
touched; nothing on the card is deleted. Every written file is re-read and
hash-checked. --dry-run lists the actions only.

DVD-only packages use isolated app/data paths and their own manifest/README;
every overwrite is backed up before copying and the existing SD inventory is
checked for unintended changes. The legacy all-channel layout is unchanged.
"""
import argparse,hashlib,json,shutil,re
from pathlib import Path
from audit_sd import ROOT
import sys
sys.path.insert(0,str(ROOT))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('package');ap.add_argument('--drive',required=True);ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
    if not re.fullmatch(r'[a-z0-9-]+',args.package):raise SystemExit('Invalid package name')
    src=ROOT/'workspace/hardware'/args.package
    if args.package in ('kwce-dvd-player-trace-v1','kwce-dvd-player-trace-v2','kwce-dvd-player-trace-v3','kwce-dvd-player-trace-v4','kwce-dvd-player-trace-v5','kwce-dvd-player-trace-v6'):
        from kwce.dvd_player_trace_sd import verify_card, sd_files as verify_trace
        from deploy_channel_package import deploy
        card=Path(args.drive).resolve()
        verify_card(src,card)
        deploy(src,card,args.dry_run,verifier=verify_trace)
        return
    if args.package in ('kwce-dvd-forwarder-v1','kwce-dvd-forwarder-v2'):
        from kwce.dvd_forwarder_sd import verify_card, sd_files as verify_forwarder
        from deploy_channel_package import deploy
        card=Path(args.drive).resolve()
        verify_card(src,card)
        deploy(src,card,args.dry_run,verifier=verify_forwarder)
        return
    if args.package.startswith('kwce-priiloader-0-10-0-sd-v'):
        from kwce.priiloader_update_sd import verify_card, sd_files as verify_priiloader
        from deploy_channel_package import deploy
        card = Path(args.drive).resolve()
        verify_card(src, card)
        deploy(src, card, args.dry_run, verifier=verify_priiloader)
        return
    if args.package == 'kwce-dvd-integrated-v1':
        from kwce.dvd_integrated_sd import verify_card, sd_files as verify_integrated
        from deploy_channel_package import deploy
        card = Path(args.drive).resolve()
        verify_card(src, card)
        deploy(src, card, args.dry_run, verifier=verify_integrated)
        return
    if args.package == 'kwce-dvd-read-control-v1':
        raise SystemExit('Withdrawn DVD candidate: native61 retains the reproduced SD ownership violation; keep DVD hack OFF')
    if args.package == 'kwce-dvd-icon-cache-v1':
        raise SystemExit('Withdrawn DVD candidate: native60 reproduced a hardware settings freeze after its DVD thumbnail appeared; keep DVD hack OFF')
    if args.package == 'kwce-dvd-stock-thumbnail-v1':
        from kwce.dvd_thumbnail_trial_sd import verify_card, sd_files as verify_thumbnail
        from deploy_channel_package import deploy
        card = Path(args.drive).resolve()
        verify_card(src, card)
        deploy(src, card, args.dry_run, verifier=verify_thumbnail)
        return
    if args.package == 'kwce-dvd-deferred-prefetch-v1':
        raise SystemExit('Withdrawn DVD candidate: native58 reproduced hardware freezes; keep DVD hack OFF')
    if re.fullmatch(r'kwce-dvd-probe-sd-v[0-9]+', args.package):
        from kwce.gc_card_encoding_sd import wii_mount
        from kwce.dvd_probe import sd_files as verify_dvd_probe
        from deploy_channel_package import deploy
        card = Path(args.drive).resolve()
        wii_mount(card)
        deploy(src, card, args.dry_run, verifier=verify_dvd_probe)
        return
    if re.fullmatch(r'kwce-key-probe-sd-v[0-9]+', args.package):
        from kwce.gc_card_encoding_sd import wii_mount
        from kwce.key_probe import sd_files as verify_key_probe
        from deploy_channel_package import deploy
        card = Path(args.drive).resolve()
        wii_mount(card)
        deploy(src, card, args.dry_run, verifier=verify_key_probe)
        return
    if args.package == 'kwce-gc-card-encoding-v1':
        from kwce.gc_card_encoding_sd import deploy as deploy_gc_encoding
        deploy_gc_encoding(src,args.drive,args.dry_run)
        return
    if args.package == 'kwce-gcmce-boot-recovery-v1':
        from kwce.gcmce_boot_recovery import deploy as deploy_gcmce_boot
        deploy_gcmce_boot(src,args.drive,args.dry_run)
        return
    if args.package == 'kwce-gcmce-recovery-v1':
        from kwce.gcmce_recovery import deploy as deploy_gcmce
        deploy_gcmce(src,args.drive,args.dry_run)
        return
    if re.fullmatch(r'kwce-news-trace-sd-v[0-9]+',args.package):
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('News trace requires an explicit removable drive')
        if not (card/'apps/Priiloader/hacks_hash.ini').is_file() or not (card/'kwce-rc/versions.txt').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.news_branch_diagnostic import sd_files as verify_news_trace
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_news_trace)
        return
    if re.fullmatch(r'kwce-account-linker-sd-v[0-9]+',args.package):
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Account Linker deployment requires an explicit removable drive')
        if not (card/'apps/Priiloader/hacks_hash.ini').is_file() or not (card/'kwce-rc/versions.txt').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.account_linker_package import sd_files as verify_account_linker
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_account_linker)
        return
    if re.fullmatch(r'kwce-sntp-sd-v[0-9]+',args.package):
        # Linux only: the mounted Wii SD (same guard as the RC packages); adds apps/sntp, never deletes.
        if sys.platform!='linux':raise SystemExit('sntp package deployment is implemented for Linux')
        from kwce.gc_card_encoding_sd import wii_mount
        card=Path(args.drive).resolve()
        if card.is_relative_to(ROOT):raise SystemExit('Refusing a project folder as the SD card')
        try:wii_mount(card)
        except ValueError as error:raise SystemExit(f'sntp deployment requires the mounted Wii SD: {error}')
        if not (card/'apps').is_dir() or not (card/'kwce-rc/versions.txt').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.sntp_package import sd_files as verify_sntp
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_sntp)
        return
    if re.fullmatch(r'kwce-disc-diagnostic-sd-v[0-9]+',args.package):
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Disc diagnostic requires an explicit removable drive')
        if not (card/'apps/Priiloader/hacks_hash.ini').is_file():raise SystemExit('Expected Priiloader SD file missing')
        from kwce.disc_diagnostic import sd_files as verify_disc
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_disc)
        return
    if re.fullmatch(r'kwce-news-network-sd-v[0-9]+',args.package):
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('News diagnostic requires an explicit removable drive')
        if not (card/'apps/Priiloader/hacks_hash.ini').is_file() or not (card/'kwce-rc/versions.txt').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.news_network_diagnostic import sd_files as verify_news_diagnostic
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_news_diagnostic)
        return
    if args.package=='kwce-photo-region-sd-v1':
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Photo trial requires a removable drive')
        if not (card/'apps/some-yawmm-mod/boot.dol').is_file() or not (card/'apps/Priiloader/hacks_hash.ini').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.photoprints_sd_v6 import sd_files as verify_photo
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_photo)
        return
    if args.package=='kwce-remaining-sd-v1':
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Remaining-channel deployment requires a removable drive')
        if not (card/'apps/some-yawmm-mod/boot.dol').is_file() or not (card/'apps/Priiloader/hacks_hash.ini').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.remaining_hardware import sd_files as verify_remaining
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_remaining)
        return
    if re.fullmatch(r'kwce-diagnostic-sd-v[0-9]+',args.package):
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Diagnostic deployment requires a removable drive')
        if not (card/'apps/Priiloader/hacks_hash.ini').is_file() or not (card/'kwce/packages.txt').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.unified_diagnostics import sd_files as verify_diagnostic
        from kwce.unified_hardware import verify_card
        verify_card(card,ROOT)
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_diagnostic)
        return
    if re.fullmatch(r'kwce-unified-sd-v[0-9]+',args.package):
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/')) or card.is_relative_to(ROOT) or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Unified deployment requires an explicit removable drive')
        if not (card/'apps/Priiloader/hacks_hash.ini').is_file() or not (card/'kwce/news/original.wad').is_file():raise SystemExit('Expected Wii SD prerequisites missing')
        from kwce.unified_hardware import sd_files as verify_unified, verify_card
        verify_card(card,ROOT)
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_unified,extra_backup=('apps/vbagx/settings.xml',))
        return
    if args.package=='kwce-loading-news20-room51-v1':
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/'))or card.is_relative_to(ROOT)or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Loading deployment requires an explicit removable drive')
        required=['apps/Priiloader/hacks_hash.ini','apps/kwce-installer/boot.dol','kwce/news/original.wad','kwce/wiiroom/original.wad','kwce-wiiroom/wiiroom/original.wad']
        if not all((card/p).is_file()for p in required):raise SystemExit('Existing Wii channel/Room SD prerequisites missing')
        from export_loading_update import sd_files as verify_loading
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_loading)
        return
    if args.package=='kwce-wiiroom-r47-v1':
        import ctypes
        card=Path(args.drive.rstrip('\\/')+'\\').resolve()
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/'))or card.is_relative_to(ROOT)or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Room deployment requires an explicit removable drive')
        if not(card/'apps').is_dir()or not(card/'apps/Priiloader/hacks_hash.ini').is_file():raise SystemExit('Not the expected Wii SD card')
        from export_wiiroom_update import sd_files as verify_room
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_room)
        return
    if re.fullmatch(r'kwce-rc-sd-v\d+',args.package):
        if sys.platform=='linux':
            # Linux: an explicit mount point of the unique removable FAT Wii SD (same guard as the
            # forwarder/card-encoding deliveries); never a project folder or the GCMCE card.
            from kwce.gc_card_encoding_sd import wii_mount
            card=Path(args.drive).resolve()
            if card.is_relative_to(ROOT):raise SystemExit('Refusing a project folder as the SD card')
            try:wii_mount(card)
            except ValueError as error:raise SystemExit(f'RC deployment requires the mounted Wii SD: {error}')
        else:
            import ctypes
            card=Path(args.drive.rstrip('\\/')+'\\').resolve()
            if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/'))or card.is_relative_to(ROOT)or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('RC deployment requires an explicit removable drive')
        if not(card/'apps').is_dir():raise SystemExit('Not the expected Wii SD card (apps missing)')
        # RC1/RC2 deliver KWCE-only disc profiles under kwce-rc/priiloader/. RC3+ (priiloader_merge)
        # also get two COMPLETE profiles built here from the card's own hacks_hash.ini, which this
        # tool only READS: every non-KWCE hack keeps its bytes/order and only the KWCE disc sections
        # differ. The installer switches the active file on the console after its own backup.
        from kwce.rc_hardware import sd_files as verify_rc,merge_disc_profile,FRAGMENT
        from deploy_channel_package import deploy
        record=json.loads((src/'package-manifest.json').read_text(encoding='utf-8'))
        verifier=verify_rc
        if record.get('priiloader_merge'):
            current=card/'apps/Priiloader/hacks_hash.ini'
            if not current.is_file():raise SystemExit('RC3+ needs the card Priiloader file apps/Priiloader/hacks_hash.ini')
            from audit_sd import PRIVATE
            n=1
            while(PRIVATE/f'rc-priiloader-{args.package}-{n}').exists():n+=1
            stage=PRIVATE/f'rc-priiloader-{args.package}-{n}';stage.mkdir(parents=True)
            base=current.read_bytes();(stage/'card-hacks_hash.ini').write_bytes(base)
            generated=[]
            for mode in('gc-only','gc-dvd'):
                merged=merge_disc_profile(base,(src/'kwce-rc/priiloader'/FRAGMENT.format(mode)).read_bytes())
                (stage/f'{mode}.ini').write_bytes(merged)
                generated.append((stage/f'{mode}.ini',f'kwce-rc/priiloader/{mode}.ini'))
                print(f'  Priiloader {mode}: {len(merged)} B (card file {len(base)} B, its other hacks kept)')
            print(f'  stage: {stage.relative_to(ROOT).as_posix()}')
            def verifier(package):
                rec,files=verify_rc(package)
                return rec,files+generated
        deploy(src,card,args.dry_run,verifier=verifier)
        return
    if not(src/'package-manifest.json').exists():raise SystemExit('Unknown package')
    card=Path(args.drive.rstrip('\\/')+'\\').resolve()
    if card.is_relative_to(ROOT):raise SystemExit('Refusing a project folder as the SD card')
    if not(card/'apps').is_dir()or not(card/'apps/Priiloader/hacks_hash.ini').is_file():raise SystemExit('Not the expected Wii SD card (apps/Priiloader missing)')
    metadata=json.loads((src/'package-manifest.json').read_text(encoding='utf-8'))
    if metadata.get('kind')=='korean-vwii-channels-v1':
        import ctypes
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/'))or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('vWii deployment requires an explicit removable drive')
        from kwce.vwii_hardware import sd_files as verify_vwii
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run,verifier=verify_vwii)
        return
    if metadata.get('kind')=='channel-only-v1':
        import ctypes
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/'))or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('Channel deployment requires an explicit removable drive')
        from deploy_channel_package import deploy
        deploy(src,card,args.dry_run)
        return
    if metadata.get('kind')in {'dvd-only-r19','dvd-only-r20','dvd-only-r21','dvd-only-r24','dvd-only-r25','dvd-only-r26','dvd-only-r27'}:
        import ctypes
        if not re.fullmatch(r'[D-Zd-z]:',args.drive.rstrip('\\/'))or ctypes.windll.kernel32.GetDriveTypeW(str(card)+'\\')!=2:raise SystemExit('DVD deployment requires an explicit removable drive')
        from deploy_dvd_package import deploy
        deploy(src,card,args.dry_run)
        return
    plan=[]
    for item in sorted((src/'apps/kwce-installer').iterdir()):plan.append((item,card/'apps/kwce-installer'/item.name))
    for item in sorted((src/'kwce').rglob('*')):
        if item.is_file():plan.append((item,card/'kwce'/item.relative_to(src/'kwce')))
    for name in['KWCE-README-ko.txt','package-manifest.json']:plan.append((src/name,card/name))
    need=sum(s.stat().st_size for s,_ in plan)-sum(d.stat().st_size for _,d in plan if d.exists())
    free=shutil.disk_usage(card).free
    print(f'{len(plan)} files, net {need//2**20} MB, free {free//2**20} MB')
    if need>free-64*2**20:raise SystemExit('Not enough free space on the card')
    hacks=card/'apps/Priiloader/hacks_hash.ini';backup=hacks.with_name('hacks_hash.ini.before-kwce')
    original=(backup if backup.exists()else hacks).read_bytes()
    if b'[KWCE GC'in original:raise SystemExit('Backup already contains KWCE hacks')
    # The console's Priiloader rejects newer-format sections (and comments), which hides
    # every hack: keep its compatible sections, then the KWCE ones.
    from kwce.priiloader_hacks import legacy_sections
    compatible,dropped=legacy_sections(original.decode('latin1'))
    merged=(compatible+(src/'priiloader/kwce-hacks.ini').read_bytes().decode('ascii').replace('\r\n','\n')).replace('\n','\r\n').encode('latin1')
    if args.dry_run:
        for s,d in plan:print('copy',d)
        print('update',hacks,'(backup',backup.name,'exists'if backup.exists()else'new',f') keeps {compatible.count(chr(10)+"[")+1} sections, drops {len(dropped)}');return
    for s,d in plan:
        d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(s,d)
        if digest(d)!=digest(s):raise SystemExit(f'Verify failed: {d}')
    if not backup.exists():shutil.copyfile(hacks,backup)
    if digest(backup)!=hashlib.sha256(original).hexdigest():raise SystemExit('Backup verify failed')
    hacks.write_bytes(merged)
    if hacks.read_bytes()!=merged:raise SystemExit('hacks_hash.ini verify failed')
    record=dict(package=args.package,files=len(plan),hacks_backup=backup.name,hacks_kept=compatible.count('\n['),hacks_dropped=len(dropped),state_records=sorted(p.name for p in(card/'kwce/state').glob('*.txt'))if(card/'kwce/state').exists()else[])
    print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
