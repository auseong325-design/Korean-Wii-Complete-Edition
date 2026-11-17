"""Korean Food (Demae) hardware candidate. Not installed anywhere.

Starts from the stock executable with WiiLink's public Demae_1_Japan service
patch applied (keeps the live food.wiilink24.com endpoints, WiiLink content
signature and English protocol tokens), then applies the Korean UI strings by
SEARCH (not stock offsets, because the WiiLink DOL is uncompressed and
shifted), the Korea-area bridge, Korean shared fonts, Korean HOME Menu and
Korean IMET banner. Content 1 is re-compressed to LZ11 (the stock loader's
expected format). Fakesigned through kwce.hardware.hardware_wad; no loopback
addresses are introduced. hardware_success_verified=false (needs the lead's
real-console test).
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce.channels import load_library, ChannelArchive, sha256
from kwce.wiiroom_formats import decompress_lz11, compress_lz11_optimal
from kwce import bspatch
from kwce.hardware import hardware_wad
from build_food import apply_executable, apply_executable_v3

TITLE = '000100014843484a'; BOOT = 9
PATCH = 'workspace/channels/food/references/wiilink-patcher/bsdiff__demae__Demae_1_Japan.bsdiff'
# hardware-vN -> content/translation revision (hardware-v5 carries the build-v6 content; build-v5 is diagnostic only)
CONTENT_REVISION = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 13, 13: 14}
EXEC_TABLES = {3: 'configs/food-executable-v3-ko.json', 4: 'configs/food-executable-v4-ko.json',
               6: 'configs/food-executable-v6-ko.json', 7: 'configs/food-executable-v7-ko.json',
               8: 'configs/food-executable-v7-ko.json',   # content rev 8 = v7 strings + Korean save-data banner
               9: 'configs/food-executable-v7-ko.json',   # content rev 9 = rev 8 + Korean address card
               10: 'configs/food-executable-v7-ko.json',  # content rev 10 = rev 9 + phone-check patch + order-flow textures/labels
               11: 'configs/food-executable-v7-ko.json',  # content rev 11 = rev 10 + more order-flow textures/BRLYT labels (content 2 only)
               12: 'configs/food-executable-v7-ko.json',  # content rev 12 = rev 11 + confirm-card words/order strings + rc7b content 2
               13: 'configs/food-executable-v7-ko.json',  # content rev 13 = rev 12 + category photo tiles/단골 from stock (content 2 only)
               14: 'configs/food-executable-v7-ko.json'}  # content rev 14 = rev 13 + overlay panes moved onto the Korean blank runs (content 2 only)


def _apply_v3(wl_dol, revision=3):
    cfg3 = json.loads((ROOT / EXEC_TABLES[revision]).read_text(encoding='utf-8'))
    if sha256(wl_dol) != cfg3['source_sha256']:
        raise ValueError('WiiLink executable hash differs from the v3 translation table')
    return apply_executable_v3(wl_dol, cfg3)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--reproduce', action='store_true')
    ap.add_argument('--revision', type=int, default=6, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]); args = ap.parse_args()
    rev = CONTENT_REVISION[args.revision]
    base = ROOT / 'workspace/channels/food'; out = base / f'hardware-v{args.revision}'; expected = None
    if args.reproduce:
        expected = (out / 'food-ko-hardware-test.wad').read_bytes(); n = 1
        while (ROOT / f'workspace/private/food-hardware-reproduce-v{args.revision}-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/food-hardware-reproduce-v{args.revision}-{n}'
    if out.exists():
        raise ValueError('Existing Food hardware build preserved')
    cfg = json.loads((ROOT / 'configs/food-executable-v1-ko.json').read_text(encoding='utf-8'))
    source = (base / 'originals/food-japan-v512.wad').read_bytes()
    lib = load_library(); title = lib.title.Title(); title.load_wad(source)
    if title.tmd.title_id != TITLE or title.tmd.boot_index != BOOT:
        raise ValueError('Food source identity differs')
    original = [title.get_content_by_index(i) for i in range(title.tmd.num_contents)]
    patch = (ROOT / PATCH).read_bytes()
    wl_dol = bspatch.apply(original[1], patch)          # WiiLink uncompressed DOL
    if b'food.wiilink24.com' not in wl_dol or wl_dol[:4] != b'\x00\x00\x01\x00':
        raise ValueError('WiiLink Demae patch did not produce the expected DOL')
    dol, n_strings = (apply_executable(wl_dol, cfg) if rev < 3 else _apply_v3(wl_dol, rev))  # Korean strings by search
    from kwce.food_compat import patch_korean_area
    dol, area = patch_korean_area(dol)
    card_rec = None
    if rev >= 9:
        from kwce.food_address_card import patch_address_card
        dol, card_rec = patch_address_card(dol)
    phone_rec = None
    if rev >= 10:
        from kwce.food_phone import patch_phone_check
        dol, phone_rec = patch_phone_check(dol)
    confirm_rec = strings_rec = None
    if rev >= 12:
        from kwce.food_confirm_card import patch_confirm_card, patch_order_strings
        dol, confirm_rec = patch_confirm_card(dol)
        dol, strings_rec = patch_order_strings(dol)
    if b'127.0.0' in dol or b'localhost' in dol:
        raise ValueError('Hardware build must not contain loopback endpoints')
    packed = compress_lz11_optimal(dol)
    if decompress_lz11(packed) != dol:
        raise ValueError('Food hardware LZ11 roundtrip failed')
    title.set_content(packed, 1)
    from kwce.channel_korean_font import korean_shared_fonts
    fonts, font_rec = korean_shared_fonts(); title.set_content(fonts, 3)
    from kwce.home_menu import korean_home_menu, KOREAN_SHARED, SOURCES
    home, home_rec = korean_home_menu(original[4], fix_dialogs=True, all_dialog_languages=True)
    home = ChannelArchive(home); korean = ChannelArchive(KOREAN_SHARED.read_bytes())
    for folder, path in SOURCES.items():
        name = folder + '/LZ77_homeBtn.arc'
        if name in home.files:
            home = ChannelArchive(home.replace(name, korean.get(path)))
    title.set_content(home.compact(), 4)
    from kwce.food_banner import korean_banner
    content0, art_rec = original[0], None
    if rev >= 6:
        from kwce.food_menu_art import korean_menu_art, YUME_KO, YUME_KO_V7
        content0, art_rec = korean_menu_art(content0, YUME_KO_V7 if rev >= 7 else YUME_KO, bold=rev >= 10)
    banner, banner_rec = korean_banner(content0); title.set_content(banner, 0)
    res_rec = None
    if rev >= 2:
        from kwce.food_resources import korean_content2
        content2, res_rec = korean_content2(original[2], revision=min(rev, 13))
        if rev >= 14:
            # Real-console photos (2026-11-16): A button/heart/minutes drawn over the next letter.
            from kwce import food_overlay_align, food_textfit
            content2, overlay_rec = food_overlay_align.align(content2, original[2], food_textfit.stock_metrics(original[3]),
                                                             food_textfit.korean_metrics())
            res_rec = dict(res_rec, overlay_alignment=overlay_rec)
        title.set_content(content2, 2)
    title.tmd.region = 4
    built = title.dump_wad()
    wad, checks = hardware_wad(built, source)
    check = lib.title.Title(); check.load_wad(wad)
    changed = [i for i in range(title.tmd.num_contents) if check.get_content_by_index(i) != original[i]]
    if changed != ([0, 1, 3, 4] if rev == 1 else [0, 1, 2, 3, 4]):
        raise ValueError('Unexpected Food hardware content change: ' + str(changed))
    if rev >= 6 and check.tmd.region != 4:
        raise ValueError('Food hardware TMD region must be 4 (KOR) for the Korean Wii Menu')
    out.mkdir(parents=True)
    (out / 'food-ko-hardware-test.wad').write_bytes(wad)
    manifest = dict(revision=args.revision, channel='food', hardware_candidate=True, title_id=title.tmd.title_id,
                    boot_index=BOOT, wad_sha256=sha256(wad), original_sha256=sha256(source),
                    wiilink_patch='Demae_1_Japan.bsdiff', wiilink_patch_sha256=sha256(patch),
                    service_host='food.wiilink24.com', translated_executable_strings=n_strings,
                    korean_area_bridge=area, shared_fonts=font_rec, korean_home=home_rec, banner=banner_rec,
                    changed_contents=changed, hardware_checks=checks, local_only=False,
                    full_localization_complete=False, hardware_success_verified=False)
    if res_rec is not None:
        manifest['content2'] = res_rec
    if art_rec is not None:
        manifest.update(content_revision=rev, source_local_build='build-v%d' % rev, menu_art=art_rec, tmd_region=check.tmd.region)
    if card_rec is not None:
        manifest['address_card_executable'] = card_rec
    if phone_rec is not None:
        manifest['phone_check_executable'] = phone_rec
    if confirm_rec is not None:
        manifest['confirm_card_executable'] = confirm_rec; manifest['order_strings_executable'] = strings_rec
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if expected is not None and expected != wad:
        raise ValueError('Food hardware reproduction differs')
    print(('Reproduced byte-identically' if expected is not None else 'Built'),
          'Food hardware candidate: strings', n_strings, 'host food.wiilink24.com kept, area',
          area['source_area'], '->', area['resource_area'], 'wad', sha256(wad)[:12], '(not installed)')


if __name__ == '__main__':
    main()
