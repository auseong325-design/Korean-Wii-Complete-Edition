"""Install the Korean Set Personal Data title and a FICTIONAL pd.dat into the
isolated Food test profile so Demae's address checks pass in local review.

Demae requires the SPD title 00010008-4843434a (HCCJ) to be installed (it
queries the installed TMD version) and reads
/title/00010008/4843434a/data/nocopy/pd.dat (home address, name kana, phone).
This script reuses, read-only, the personal-data worker's ACTIVE Korean SPD
local build and kwce/personal_data_format. pd.dat is encrypted for Dolphin's
public DEFAULT_DEVICE_ID; launch_dolphin.validate() refuses any profile that
holds keys.bin, so no real console ID can apply. No real personal data is read.

  --variant korean-spd      fictional Korean sample exactly as the Korean SPD writes it (default since
                            wave 2: kana == name for family and given; Demae shows "길동 홍 님")
  --variant korean          v4 test-only order fix (given field = full name, family empty); Demae
                            refuses it with the missing-reading dialog - kept for the record only
  --variant jp-compatible   fictional Shift-JIS-encodable values (isolates SJIS issues)
  --clear                   remove pd.dat (SPD title stays installed)
"""
import argparse, json, sys
from audit_sd import ROOT, PRIVATE, sha256
from prepare_channel_access import stopped
from prepare_gc_v6 import snapshot
from prepare_food_test import register, PROFILE, BASE
import launch_dolphin as launcher
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library
from kwce import personal_data_format as fmt
from kwce import food_personal_data as fpd

LOCK = ROOT / 'configs/food-runtime.lock.json'
STATE = ROOT / 'workspace/channels/food/personal-data-state.json'


def spd_wad():
    active = json.loads((fpd.PD_CHANNEL / 'active-build.json').read_text(encoding='utf-8'))
    rev = active['revision']; wad = fpd.PD_CHANNEL / f'build-v{rev}/personal-data-ko-local-test.wad'
    meta = json.loads(wad.with_name('build-manifest.json').read_text(encoding='utf-8'))
    if sha256(wad) != meta['wad_sha256'] or meta['wad_sha256'] != active['wad_sha256']:
        raise ValueError('Korean SPD build identity differs from its manifest/active record')
    if meta.get('title_id', fpd.SPD_TITLE).lower() != fpd.SPD_TITLE:
        raise ValueError('SPD build is not 00010008-4843434a')
    return rev, wad, meta


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--variant', choices=['korean-spd', 'korean', 'jp-compatible'], default='korean-spd')
    g.add_argument('--clear', action='store_true')
    args = ap.parse_args(); stopped(); register()
    n = 1
    while (PRIVATE / f'food-before-personal-data-{n}.json').exists():
        n += 1
    (PRIVATE / f'food-before-personal-data-{n}.json').write_text(json.dumps(snapshot(BASE / 'user'), indent=2))
    lib = load_library()
    rev, wad, meta = spd_wad()
    title = lib.title.Title(); title.load_wad(wad.read_bytes())
    if title.tmd.title_id.lower() != fpd.SPD_TITLE:
        raise ValueError('SPD WAD title differs')
    lib.nand.EmuNAND(BASE / 'user/Wii').install_title(title)
    launcher.scrub_download_tasks(PROFILE); launcher.validate(PROFILE)  # refuses keys.bin
    target = BASE / 'user/Wii' / fpd.PD_PATH.lstrip('/')
    lock = json.loads(LOCK.read_text())
    record = dict(spd_title=fpd.SPD_TITLE, spd_revision=rev, spd_wad_sha256=meta['wad_sha256'],
                  spd_title_version=title.tmd.title_version, pd_path=fpd.PD_PATH)
    if args.clear:
        if target.exists():
            target.unlink()
        record.update(pd_installed=False)
    else:
        plain = fpd.variant(args.variant)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fmt.encrypt(plain, fmt.DOLPHIN_DEFAULT_DEVICE_ID))
        if fmt.decrypt(target.read_bytes(), fmt.DOLPHIN_DEFAULT_DEVICE_ID) != plain:
            raise ValueError('pd.dat encryption roundtrip failed')
        record.update(pd_installed=True, pd_variant=args.variant, pd_sha256=sha256(target),
                      device_id='Dolphin public DEFAULT_DEVICE_ID', fictional=True, **{'fields': fpd.summary(plain)})
    lock['personal_data'] = record
    LOCK.write_text(json.dumps(lock, indent=2))
    STATE.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
    print('Food profile: Korean SPD build', rev, 'installed;',
          ('pd.dat removed' if args.clear else f'fictional pd.dat ({args.variant}) installed') + '; runtime lock updated')


if __name__ == '__main__':
    main()
