"""Immutable Korean Food (Demae) local-test WAD. Console originals untouched.

Local build: service hosts (nwapi/nwpic.demae-can.com) are redirected to
http://127.0.0.2 and the API scheme is downgraded to http so the channel
reaches the in-container synthetic feed; Korean UI strings are applied in-slot
to the executable; the Korea-area bridge, Korean shared fonts, Korean HOME
Menu and Korean IMET banner names are installed. No ordering/payment code is
added. local_only=true.
"""
import argparse, hashlib, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive, sha256
from kwce.wiiroom_formats import decompress_lz11, reencode_lz11_same_size, compress_lz11_optimal

TITLE = '000100014843484a'; BOOT = 9
LOCAL = b'127.0.0.2'
WIILINK_PATCH = 'workspace/channels/food/references/wiilink-patcher/bsdiff__demae__Demae_1_Japan.bsdiff'
HOST_REDIRECTS = {
    b'nwapi.demae-can.com/nwapi.php?action=': b'127.0.0.2/nwapi.php?action=',
    b'nwapi.demae-can.com/nwapi.php': b'127.0.0.2/nwapi.php',
    b'nwpic.demae-can.com/itemimg/': b'127.0.0.2/itemimg/',
    b'nwpic.demae-can.com/logoimg2/': b'127.0.0.2/logoimg2/',
}


def apply_executable(dol, cfg):
    """In-slot UTF-16BE replacement of Korean UI strings (every occurrence)."""
    out = bytearray(dol); records = 0; strings = 0
    for src, tgt in sorted(cfg['utf16'].items(), key=lambda kv: -len(kv[0])):
        if re.findall(r'%[-+0-9.*]*[a-zA-Z]', src) != re.findall(r'%[-+0-9.*]*[a-zA-Z]', tgt):
            raise ValueError('Food format token changed: ' + repr(src[:16]))
        needle = src.encode('utf-16-be') + b'\0\0'
        payload = tgt.encode('utf-16-be') + b'\0\0'
        at = out.find(needle); hits = 0
        while at >= 0:
            if at % 2:
                at = out.find(needle, at + 2); continue
            end = at + len(src.encode('utf-16-be'))
            slot = end + 2
            while slot + 2 <= len(out) and out[slot:slot + 2] == b'\0\0':
                slot += 2
            if len(payload) > slot - at:
                raise ValueError('Food Korean string exceeds slot: ' + repr(tgt[:16]))
            out[at:slot] = payload + bytes(slot - at - len(payload))
            hits += 1; records += 1
            at = out.find(needle, at + len(payload))
        if not hits:
            raise ValueError('Food literal missing: ' + repr(src[:16]))
        strings += 1
    return bytes(out), records


def redirect_endpoints(dol):
    """Point service hosts at the loopback feed and force http (local only)."""
    out = bytearray(dol); hosts = 0
    for src, dst in HOST_REDIRECTS.items():
        at = out.find(src)
        if at < 0:
            raise ValueError('Food endpoint literal missing: ' + src.decode())
        if out.find(src, at + 1) >= 0:
            raise ValueError('Food endpoint literal not unique: ' + src.decode())
        out[at:at + len(src)] = dst + bytes(len(src) - len(dst)); hosts += 1
    # Downgrade the API-adjacent https:// to http:// (the WiiLink Japan patch
    # does the same); the 9-byte literal region keeps its length.
    scheme = out.find(b'https://\x00http://\x00')
    if scheme < 0:
        raise ValueError('Food API scheme block not found')
    out[scheme:scheme + 9] = b'http://\x00\x00'
    return bytes(out), dict(hosts=hosts, loopback='127.0.0.2', scheme='http', https_downgraded=1)


def apply_executable_v3(dol, cfg):
    """Whole-literal (previous halfword 0) in-slot replacement for revision >= 3."""
    out = bytearray(dol); records = 0
    for src, tgt in sorted(cfg['utf16'].items(), key=lambda kv: -len(kv[0])):
        if re.findall(r'%[-+0-9.*]*[a-zA-Z]', src) != re.findall(r'%[-+0-9.*]*[a-zA-Z]', tgt):
            raise ValueError('Food format token changed: ' + repr(src[:16]))
        needle = src.encode('utf-16-be') + b'\0\0'; payload = tgt.encode('utf-16-be') + b'\0\0'
        at = out.find(needle); hits = 0
        while at >= 0:
            if at % 2 == 0 and (at < 2 or out[at - 2:at] == b'\0\0'):
                slot = at + len(needle)
                while slot + 2 <= len(out) and out[slot:slot + 2] == b'\0\0':
                    slot += 2
                if len(payload) > slot - at:
                    raise ValueError('Food Korean string exceeds slot: ' + repr(tgt[:16]))
                out[at:slot] = payload + bytes(slot - at - len(payload)); hits += 1; records += 1
                at = out.find(needle, at + len(payload))
            else:
                at = out.find(needle, at + 1)
        if not hits:
            raise ValueError('Food literal missing: ' + repr(src[:16]))
    return bytes(out), records


WIILINK_HOST = b'food.wiilink24.com'
# Translation table per content revision (5 is the diagnostic build, scripts/build_food_diagnostic.py).
EXEC_TABLES = {3: 'configs/food-executable-v3-ko.json', 4: 'configs/food-executable-v4-ko.json',
               6: 'configs/food-executable-v6-ko.json', 7: 'configs/food-executable-v7-ko.json',
               8: 'configs/food-executable-v7-ko.json',   # rev 8 = v7 strings + Korean save-data banner
               9: 'configs/food-executable-v7-ko.json',   # rev 9 = rev 8 + Korean address card (kwce.food_address_card)
               10: 'configs/food-executable-v7-ko.json',  # rev 10 = rev 9 + phone-check patch + order-flow textures/labels
               11: 'configs/food-executable-v7-ko.json',  # rev 11 = rev 10 + more order-flow textures/BRLYT labels (content 2 only)
               12: 'configs/food-executable-v7-ko.json',  # rev 12 = rev 11 + confirm-card words/order strings (kwce.food_confirm_card) + rc7b content 2
               13: 'configs/food-executable-v7-ko.json'}  # rev 13 = rev 12 + category photo tiles/단골 redrawn from stock (content 2 only)


def redirect_wiilink_endpoints(dol):
    """Local only: WiiLink's four service literals -> 127.0.0.2 (already http)."""
    out = bytearray(dol); hosts = 0; at = out.find(WIILINK_HOST)
    while at >= 0:
        if out[at - 1] != 0 or b'/' not in out[at:at + 40]:
            raise ValueError('Unexpected food.wiilink24.com context')
        end = out.index(b'\0', at); old = bytes(out[at:end]); new = LOCAL + old[len(WIILINK_HOST):]
        out[at:end] = new + bytes(len(old) - len(new)); hosts += 1; at = out.find(WIILINK_HOST, at + 1)
    if hosts != 4 or b'wiilink24' in out or b'demae-can' in out:
        raise ValueError('Food WiiLink endpoint redirect identity')
    if b'https://\0' in out[out.find(LOCAL) - 64:out.find(LOCAL)]:
        raise ValueError('Food API scheme is not http')
    return bytes(out), dict(hosts=hosts, loopback='127.0.0.2', scheme='http', base='WiiLink Demae_1_Japan')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--revision', type=int, default=7, choices=[1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13])
    ap.add_argument('--reproduce', action='store_true'); args = ap.parse_args()
    base = ROOT / 'workspace/channels/food'; out = base / f'build-v{args.revision}'; expected = None
    if args.reproduce:
        expected = (out / 'food-ko-local-test.wad').read_bytes(); n = 1
        while (ROOT / f'workspace/private/food-reproduce-v{args.revision}-{n}').exists():
            n += 1
        out = ROOT / f'workspace/private/food-reproduce-v{args.revision}-{n}'
    if out.exists():
        raise SystemExit('Existing Food build preserved')
    cfg = json.loads((ROOT / 'configs/food-executable-v1-ko.json').read_text(encoding='utf-8'))
    source = (base / 'originals/food-japan-v512.wad').read_bytes()
    lib = load_library(); title = lib.title.Title(); title.load_wad(source)
    if title.tmd.title_id != TITLE or title.tmd.boot_index != BOOT:
        raise ValueError('Food source identity differs')
    original = [title.get_content_by_index(i) for i in range(title.tmd.num_contents)]
    if args.revision >= 3:
        from kwce import bspatch
        cfg = json.loads((ROOT / EXEC_TABLES[args.revision]).read_text(encoding='utf-8'))
        dol = bspatch.apply(original[1], (ROOT / WIILINK_PATCH).read_bytes())
        if sha256(dol) != cfg['source_sha256']:
            raise ValueError('WiiLink executable hash differs from the translation table')
        dol, n_strings = apply_executable_v3(dol, cfg)
        dol, ep = redirect_wiilink_endpoints(dol)
    else:
        dol = decompress_lz11(original[1])
        if sha256(dol) != cfg['source_sha256']:
            raise ValueError('Food executable hash differs from translation table')
        dol, n_strings = apply_executable(dol, cfg)
        dol, ep = redirect_endpoints(dol)
    from kwce.food_compat import patch_korean_area
    dol, area = patch_korean_area(dol)
    card_rec = None
    if args.revision >= 9:
        from kwce.food_address_card import patch_address_card
        dol, card_rec = patch_address_card(dol)
    phone_rec = None
    if args.revision >= 10:
        from kwce.food_phone import patch_phone_check
        dol, phone_rec = patch_phone_check(dol)
    confirm_rec = strings_rec = None
    if args.revision >= 12:
        from kwce.food_confirm_card import patch_confirm_card, patch_order_strings
        dol, confirm_rec = patch_confirm_card(dol)
        dol, strings_rec = patch_order_strings(dol)
    try:
        packed = reencode_lz11_same_size(original[1], dol); size_mode = 'same-size'
    except Exception:
        packed = compress_lz11_optimal(dol); size_mode = 'optimal'
    if decompress_lz11(packed) != dol:
        raise ValueError('Food LZ11 re-encode roundtrip failed')
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
    if args.revision >= 6:
        from kwce.food_menu_art import korean_menu_art, YUME_KO, YUME_KO_V7
        content0, art_rec = korean_menu_art(content0, YUME_KO_V7 if args.revision >= 7 else YUME_KO, bold=args.revision >= 10)
    banner, banner_rec = korean_banner(content0); title.set_content(banner, 0)
    res_rec = None
    if args.revision >= 2:
        from kwce.food_resources import korean_content2
        content2, res_rec = korean_content2(original[2], revision=args.revision); title.set_content(content2, 2)
    title.tmd.region = 4
    wad = title.dump_wad(); check = lib.title.Title(); check.load_wad(wad)
    changed = [i for i in range(title.tmd.num_contents) if check.get_content_by_index(i) != original[i]]
    if changed != ([0, 1, 3, 4] if args.revision == 1 else [0, 1, 2, 3, 4]):
        raise ValueError('Unexpected Food content change: ' + str(changed))
    out.mkdir(parents=True)
    (out / 'food-ko-local-test.wad').write_bytes(wad)
    manifest = dict(revision=args.revision, channel='food', title_id=title.tmd.title_id, boot_index=BOOT,
                    wad_sha256=sha256(wad), source_sha256=cfg['source_sha256'], changed_contents=changed,
                    translated_executable_strings=n_strings, endpoints=ep, korean_area_bridge=area,
                    shared_fonts=font_rec, korean_home=home_rec, banner=banner_rec, lz11=size_mode,
                    local_only=True, full_localization_complete=False, hardware_success_verified=False)
    if res_rec is not None:
        manifest['content2'] = res_rec
    if art_rec is not None:
        manifest['menu_art'] = art_rec; manifest['tmd_region'] = title.tmd.region
    if card_rec is not None:
        manifest['address_card_executable'] = card_rec
    if phone_rec is not None:
        manifest['phone_check_executable'] = phone_rec
    if confirm_rec is not None:
        manifest['confirm_card_executable'] = confirm_rec; manifest['order_strings_executable'] = strings_rec
    manifest['executable_base'] = 'WiiLink Demae_1_Japan' if args.revision >= 3 else 'stock (LZ11)'
    (out / 'build-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if expected is not None and expected != wad:
        raise ValueError('Food reproduction differs')
    print(('Reproduced byte-identically' if expected is not None else 'Built'),
          'Food local revision', args.revision, ': strings', n_strings, 'endpoints', ep['hosts'],
          'area', area['source_area'], '->', area['resource_area'], 'wad', sha256(wad)[:12])


if __name__ == '__main__':
    main()
