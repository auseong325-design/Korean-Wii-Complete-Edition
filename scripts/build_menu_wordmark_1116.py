"""Wii Menu title choices of 2026-11-16 (font candidate sheet), content 0 only.

  python scripts/build_menu_wordmark_1116.py --channel mii-contest|nintendo|internet [--reproduce]

mii-contest build-v33 -> build-v34: banner syllables no longer overlap (1-A), icon 'Mii / 콘테스트 / 채널'
    in the Japanese layout with the banner's block face (2-A). kwce/mii_contest_menu_v34.py
nintendo build-v20 -> build-v21: banner letters heavier and larger (3-B), icon one line + mirror like the
    US bitmap (4 'A + reflection'). kwce/nintendo_menu_art_v9.py STYLES[16]
internet hardware-v8 -> hardware-v12 (v9-v11 are defective, see PINS): KOR menu title 1.38x; the banner carries an
    outlined copy of the system typeface, the icon thickens the system font with four offset copies made
    from the unused other-language title boxes (5-B).
    kwce/internet_title_font.py
Each build first checks that its generator reproduces the parent's current menu art.
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive

PINS = {'mii-contest': ('build-v33', 'build-v34', 'mii-contest-ko-ui-test.wad'),
        'nintendo': ('build-v20', 'build-v21', 'nintendo-ko-ui-test.wad'),
        'internet': ('hardware-v8', 'hardware-v12', 'internet-ko-hardware-candidate.wad'),
        # defective, kept only for --reproduce (Dolphin halted with a dialog on the channel grid):
        # v9 gave the menu archives a '.' U8 root; v10 fixed that but its icon.bin (font inside, 118.5 KB
        # unpacked) is over the Wii Menu's icon size limit (~102.4 KB).
        'internet-v9': ('hardware-v8', 'hardware-v9', 'internet-ko-hardware-candidate.wad'),
        'internet-v10': ('hardware-v8', 'hardware-v10', 'internet-ko-hardware-candidate.wad'),
        # v11 kept the icon under the size but added four child text boxes; the menu still halted
        'internet-v11': ('hardware-v8', 'hardware-v11', 'internet-ko-hardware-candidate.wad')}
DEFECTIVE = {'internet-v9': dict(keep_u8_root=False, icon_mode='font'), 'internet-v10': dict(keep_u8_root=True, icon_mode='font'),
             'internet-v11': dict(keep_u8_root=True, icon_mode='copies')}


def _content0(path):
    t = load_library().title.Title(); t.load_wad(path.read_bytes()); return t.get_content_by_index(0)


def menu_content(channel, parent0, defective=False):
    base = ROOT / f'workspace/channels/{channel}'
    if channel == 'mii-contest':
        from kwce import mii_contest_menu_v34 as m
        us0 = _content0(base / 'originals/mii-contest-usa-wiilink-archive.wad')
        if m.banner_member(us0, 6)[0] != ChannelArchive(parent0[0x640:]).get('meta/banner.bin'):
            raise ValueError('Generator does not reproduce the v33 banner')
        c0, sizes = m.content0(parent0, us0, overlap=0)
        return c0, dict(sheet='1-A overlap 0, 2-A three-row icon', banner_overlap=0, banner=m.BANNER, icon_texture=m.ICON_TEXTURE,
                        icon_format='RGB5A3', icon_size=list(m.ICON_SIZE), uncompressed=sizes)
    if channel == 'nintendo':
        from kwce import nintendo_menu_art_v9 as nm
        v4 = _content0(base / 'build-v4/nintendo-ko-ui-test.wad')
        if nm.korean_menu_art(v4, 15)[0] != parent0:
            raise ValueError('Style 15 does not reproduce the v20 menu art')
        c0, records = nm.korean_menu_art(v4, 16)
        return c0, dict(sheet='3-B banner, 4 one line + reflection (the US icon bitmap has one)', style=16,
                        style_values={k: v for k, v in nm.STYLES[16].items()}, menu_art=records, opening='unchanged (style 15)')
    from kwce import internet_title_font as f
    c0, record = f.content0(parent0, **(defective or {}))
    return c0, dict(record, sheet='5-B system typeface 1.38x + outline')


def build(channel):
    parent, child, name = PINS[channel]
    src = ROOT / f'workspace/channels/{channel.split("-v")[0]}/{parent}'
    meta = json.loads((src / 'build-manifest.json').read_text(encoding='utf-8'))
    raw = (src / name).read_bytes(); pinned = meta.get('wad_sha256') or meta['wads']['ui']['sha256']
    if hashlib.sha256(raw).hexdigest() != pinned: raise ValueError('Parent WAD differs')
    lib = load_library(); title = lib.title.Title(); title.load_wad(raw)
    count = len(title.tmd.content_records); original = [title.get_content_by_index(i) for i in range(count)]
    c0, record = menu_content(channel.split('-v')[0] if channel in DEFECTIVE else channel, original[0], DEFECTIVE.get(channel))
    title.set_content(c0, 0); wad = title.dump_wad()
    check = lib.title.Title(); check.load_wad(wad)
    if [i for i in range(count) if check.get_content_by_index(i) != original[i]] != [0]: raise ValueError('Unexpected content change')
    meta = dict(meta)
    if isinstance(meta.get('content_sha256'), dict): meta['content_sha256'] = dict(meta['content_sha256'], **{'0': hashlib.sha256(c0).hexdigest()})
    meta.update(revision=int(child.rsplit('v', 1)[1]), parent_revision=int(parent.rsplit('v', 1)[1]), parent_wad_sha256=pinned,
                wad_sha256=hashlib.sha256(wad).hexdigest(), changed_from_parent=[0], runtime_verified=False, menu_choice_1116=record)
    if 'wad_size' in meta: meta['wad_size'] = len(wad)
    return child, name, wad, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--channel', choices=sorted(PINS), required=True)
    ap.add_argument('--reproduce', action='store_true'); a = ap.parse_args()
    child, name, wad, meta = build(a.channel); out = ROOT / f'workspace/channels/{a.channel.split("-v")[0]}/{child}'
    if a.channel in DEFECTIVE and not a.reproduce: raise SystemExit(f'{child} is defective; reproduce only')
    if a.reproduce:
        if (out / name).read_bytes() != wad: raise SystemExit('reproduction differs')
        print(f'PASS: {a.channel} {child} reproduced byte-identically'); return
    if out.exists(): raise SystemExit('Existing build preserved')
    out.mkdir(parents=True); (out / name).write_bytes(wad)
    (out / 'build-manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {a.channel} {child}, content 0 only, wad {meta["wad_sha256"][:16]}')


if __name__ == '__main__': main()
