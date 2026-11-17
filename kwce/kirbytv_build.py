"""Assemble the Korean Kirby TV Channel title from preserved inputs.

Inputs (read only): the NUS European v257 WAD, WiiLink's public ktv_2
content-2 bsdiff and replacement TMD, the console's own 43K Korean shared
fonts and Korean HOME Menu archive (local NAND extract), and the translation
tables in configs/. Output contents:
  0 IMET names; 1 language-9 KR/KO selection; 2 WiiLink ktv_2 + KR/KO set +
  SWF Korean handling; 5 10-column network.csv; 6 + Korean HOME archive;
  8 + Korean HOME guide frame; 10 Korean shared fonts. Others unchanged.
"""
import hashlib
import json
import struct
from pathlib import Path
from .channels import ROOT, ChannelArchive, load_library, sha256
from . import bspatch, kirbytv_art, kirbytv_dol, kirbytv_swf, kirbytv_text, kirbytv_u8

BASE = ROOT / 'workspace/channels/kirbytv'
WAD = BASE / 'originals/kirbytv-europe-v257.wad'
WAD_SHA256 = 'f088cb512be135a283ec2c78ae833aaeb86ce71f0a4aea59586b0bd3d4a4535d'
PATCH = BASE / 'references/wiilink-patcher/bsdiff__ktv__ktv_2.bsdiff'
PATCH_SHA256 = '192dd767bf64f8bd197fdd7ebbba9d6dba9891c19e541038c427005e792ae5f1'
WIILINK_TMD = BASE / 'references/wiilink-patcher/ktv__ktv.tmd'
WIILINK_TMD_SHA256 = '84cab01e3fcf8368e07b3eee9c43b13a409a483aa4ae3ee654d0ea5b146f8c50'
WIILINK_CONTENT2_SHA256 = 'dadf03830f6fec72'  # prefix check; full value pinned in the manifest
FONT_TTF = ROOT / 'workspace/channels/forecast/references/NotoSansKR.ttf'
UI_TABLE = ROOT / 'configs/kirbytv-ui-v1-ko.json'
UI_TABLES = {1: UI_TABLE, 2: ROOT / 'configs/kirbytv-ui-v2-ko.json', 3: ROOT / 'configs/kirbytv-ui-v3-ko.json',
             4: ROOT / 'configs/kirbytv-ui-v4-ko.json', 5: ROOT / 'configs/kirbytv-ui-v4-ko.json',
             6: ROOT / 'configs/kirbytv-ui-v4-ko.json', 7: ROOT / 'configs/kirbytv-ui-v4-ko.json',
             8: ROOT / 'configs/kirbytv-ui-v4-ko.json', 9: ROOT / 'configs/kirbytv-ui-v4-ko.json',
             10: ROOT / 'configs/kirbytv-ui-v4-ko.json', 11: ROOT / 'configs/kirbytv-ui-v4-ko.json',
             12: ROOT / 'configs/kirbytv-ui-v5-ko.json'}  # 12: key help breaks as '<br/>' (full review)
GLYPHS = {2: ROOT / 'configs/kirbytv-swf-glyphs-v2-ko.json', 3: ROOT / 'configs/kirbytv-swf-glyphs-v3-ko.json',
          4: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json', 5: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json',
          6: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json', 7: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json',
          8: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json', 9: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json',
          10: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json', 11: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json',
          12: ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json'}
MISSING = {3: ROOT / 'configs/kirbytv-missing-v3-ko.json', 4: ROOT / 'configs/kirbytv-missing-v4-ko.json',
           5: ROOT / 'configs/kirbytv-missing-v4-ko.json', 6: ROOT / 'configs/kirbytv-missing-v4-ko.json',
           7: ROOT / 'configs/kirbytv-missing-v4-ko.json', 8: ROOT / 'configs/kirbytv-missing-v4-ko.json',
           9: ROOT / 'configs/kirbytv-missing-v4-ko.json', 10: ROOT / 'configs/kirbytv-missing-v4-ko.json',
           11: ROOT / 'configs/kirbytv-missing-v4-ko.json', 12: ROOT / 'configs/kirbytv-missing-v4-ko.json'}
SYSTEM_TABLE = ROOT / 'configs/kirbytv-system-v1-ko.json'
TITLE_ID = '0001000148434d50'
CHANGED = [0, 1, 2, 5, 6, 8, 10]
KO = kirbytv_text.KO_DIR
REVISIONS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)


def missing_units(revision):
    """[(id, unit)] Korean units for locale IDs absent from the service XML (revision 3+)."""
    if revision not in MISSING:
        return None
    config = json.loads(MISSING[revision].read_text(encoding='utf-8'))
    units = []
    for key, unit in sorted(config['units'].items()):
        fields = {k: unit[k] for k in ('message', 'title', 'label', 'badge') if k in unit}
        if not any(k in fields for k in ('message', 'title', 'label')):
            raise ValueError('Missing-ID unit without text: ' + key)
        units.append((key, fields))
    return units


def _check(path, expected):
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError(f'Input differs: {path.relative_to(ROOT).as_posix()}')
    return data


def tables(revision=1):
    ui = json.loads(UI_TABLES[revision].read_text(encoding='utf-8'))
    system = json.loads(SYSTEM_TABLE.read_text(encoding='utf-8'))
    pairs, seen = [], {}
    for row in ui['entries']:
        if row['source'] in seen:
            if seen[row['source']] != row['ko']:
                raise ValueError('Conflicting UI translation')
            continue
        seen[row['source']] = row['ko']
        pairs.append((row['source'], row['ko']))
    return ui, system, pairs


def swf_glyphs(revision, ui, system):
    """(characters, HangulSource, extend_fonts kwargs) for the SWF fonts, or None for revision 1."""
    if revision < 2:
        return None
    from .kirbytv_swf_font import HangulSource
    config = json.loads(GLYPHS[revision].read_text(encoding='utf-8'))
    source = config['source']
    raw = _check(ROOT / source['path'], source['sha256'])
    characters = config['characters']
    if len(characters) != config['count'] or list(characters) != sorted(set(characters)):
        raise ValueError('SWF glyph list is not a sorted unique set')
    needed = {c for r in ui['entries'] for c in r['ko']} | {c for v in system['error_xml'].values() for c in v[1]}
    for _, unit in missing_units(revision) or []:
        needed |= {c for k in ('message', 'title', 'label') if k in unit for c in unit[k]}
    missing = sorted(c for c in needed if 0xac00 <= ord(c) <= 0xd7a3 and c not in characters)
    if missing:
        raise ValueError('SWF glyph list misses translated text: ' + ''.join(missing))
    outline = config['outline']
    params = dict(size=outline['size_em'], condense=outline['condense'], narrow_condense=outline['condense'], bold=outline['bold_em'])
    return characters, HangulSource(raw, source['weight'], label=source['name'] + ' wght ' + str(source['weight'])), params


def wiilink_title():
    """Stock title + WiiLink ktv_2 content 2 + WiiLink TMD header fields."""
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(_check(WAD, WAD_SHA256))
    if title.tmd.title_id != TITLE_ID or title.tmd.title_version != 257 or title.tmd.boot_index != 12:
        raise ValueError('Kirby TV source identity differs')
    patch = _check(PATCH, PATCH_SHA256)
    content2 = bspatch.apply(title.get_content_by_index(2), patch)
    if sha256(content2)[:16] != WIILINK_CONTENT2_SHA256:
        raise ValueError('WiiLink ktv_2 result differs')
    title.set_content(content2, 2)
    reference = lib.title.TMD()
    reference.load(_check(WIILINK_TMD, WIILINK_TMD_SHA256))
    if reference.title_id != TITLE_ID or reference.title_version != 257:
        raise ValueError('WiiLink TMD identity differs')
    # WiiLink's TMD keeps the stock content records; only header fields differ.
    title.tmd.region = reference.region
    return title, dict(wiilink_content2_sha256=sha256(content2), wiilink_tmd_region=reference.region,
                       wiilink_patch_sha256=PATCH_SHA256, stock_wad_sha256=WAD_SHA256)


def korean_imet(content, name):
    banner = bytearray(content)
    if banner[0x80:0x84] != b'IMET':
        raise ValueError('Kirby TV banner IMET')
    encoded = name.encode('utf-16-be')
    if len(encoded) > 84:
        raise ValueError('IMET name too long')
    for i in range(10):
        at = 0x40 + 0x5c + 84 * i
        banner[at:at + 84] = encoded + bytes(84 - len(encoded))
    banner[0x630:0x640] = bytes(16)
    banner[0x630:0x640] = hashlib.md5(banner[0x40:0x640]).digest()
    return bytes(banner), dict(names=10, text=name, md5_updated=True, banner_art_unchanged=True)


def korean_content2(content, system, pairs, local, font_glyphs=None, dates=False, missing=None, days=False, time_zone=False,
                    tooltip=False, bitmaps=None, hs_tooltip=False):
    archive = ChannelArchive(content)
    add, replace, record = {}, {}, {}
    for path, data in kirbytv_text.korean_configs().items():
        add[path] = data
    record['configs'] = sorted(kirbytv_text.korean_configs())
    glyphs = ''.join(system['error_strings'].values()) + system['name'] + '0123456789'
    dialog, record['dialog'] = kirbytv_text.korean_dialog_bin(
        archive.get('layout/EU/EN/dialog.bin'), {k: tuple(v) for k, v in system['dialog'].items()}, glyphs, FONT_TTF)
    add[f'layout/{KO}/dialog.bin'] = dialog
    bmg, record['error_strings'] = kirbytv_text.korean_bmg(archive.get('text/EU/EN/ErrorStrings.bmg'), system['error_strings'])
    add[f'text/{KO}/ErrorStrings.bmg'] = bmg
    add[f'banner/{KO}/banner.ini'] = kirbytv_text.korean_banner_ini(archive.get('banner/EU/EN/banner.ini'), system['name'])
    add[f'banner/{KO}/banner.tpl'] = archive.get('banner/EU/EN/banner.tpl')
    add[f'banner/{KO}/icons.tpl'] = archive.get('banner/EU/EN/icons.tpl')
    record['save_banner'] = dict(title=system['name'], textures='EU/EN copy (logo artwork unchanged)')
    manual, record['manual'] = kirbytv_art.korean_manual(archive.get('hbm/EU/EN/manual.jpg'), system['manual'])
    add[f'hbm/{KO}/manual.jpg'] = manual
    xml, record['error_xml'] = kirbytv_text.korean_error_xml(archive.get('trusted/xml/gb_error_text.xml'), system['error_xml'])
    replace['trusted/xml/gb_error_text.xml'] = xml
    swf, record['swf'] = kirbytv_swf.patch(archive.get(kirbytv_swf.SWF_PATH), pairs, local, glyphs=font_glyphs, dates=dates,
                                           missing=missing, days=days, time_zone=time_zone, tooltip=tooltip, bitmaps=bitmaps,
                                           hs_tooltip=hs_tooltip)
    replace[kirbytv_swf.SWF_PATH] = swf
    result = kirbytv_u8.edit(content, add=add, replace=replace)
    record['added_files'] = sorted(add)
    record['replaced_files'] = sorted(replace)
    return result, record


def korean_home(title, system):
    lib = load_library()
    from .home_menu import KOREAN_SHARED
    record = {}
    c5 = title.get_content_by_index(5)
    csv, record['network_csv'] = kirbytv_text.network_csv_korean(
        ChannelArchive(c5).get('HomeButton3/network.csv'), *system['home_network_message'])
    c5_new = kirbytv_u8.edit(c5, replace={'HomeButton3/network.csv': csv})
    korean = ChannelArchive(KOREAN_SHARED.read_bytes())
    home_archive = korean.get('Homebutton3/LZ77_homeBtn_KOR.arc')
    c6 = title.get_content_by_index(6)
    if ChannelArchive(c6).get('HomeButton3/config.txt') != korean.get('Homebutton3/config.txt'):
        raise ValueError('Korean HOME archive generation differs')
    c6_new = kirbytv_u8.edit(c6, add={'HomeButton3/' + kirbytv_dol.HOME_ARCHIVE: home_archive})
    record['home_archive'] = dict(path='HomeButton3/' + kirbytv_dol.HOME_ARCHIVE, source='console shared1 0x17 Homebutton3/LZ77_homeBtn_KOR.arc',
                                  sha256=sha256(home_archive), bytes_unchanged=True)
    c8 = title.get_content_by_index(8)
    frame, record['home_guide_frame'] = kirbytv_art.korean_home_manual_frame(
        ChannelArchive(c8).get('HomeButton3/LZ77_homeBtn_nwm_eng.arc'), system['home_manual_frame'])
    c8_new = kirbytv_u8.edit(c8, add={'HomeButton3/' + kirbytv_dol.HOME_MANUAL: frame})
    record['home_guide_frame']['path'] = 'HomeButton3/' + kirbytv_dol.HOME_MANUAL
    return {5: c5_new, 6: c6_new, 8: c8_new}, record


def build_title(local, revision=1):
    """Return (libWiiPy Title, original WiiLink Title, record).

    revision 1: build-v1/hardware-v1 inputs (kept byte-identical).
    revision 2: + Hangul outlines in the SWF embedded fonts, Korean date order,
    UI table v2 (date placeholders without the leading space).
    revision 3: + Korean units for locale IDs the service XML lacks.
    revision 4: + txt_intro_4 unit, Korean getDaysAsText, KST for the
    unsupported-country time zone, UI table v4 (timetable date lines).
    revision 5-7: + Wii Menu banner/icon KOR group and icon '채널' word (content 0).
    revision 8: + '채널' in the Wii Menu banner logo and the in-channel logos (SWF
    bitmaps), new icon word lettering, Hangul-aware tooltip width (SWF code).
    revision 9: the tooltip width is the original width call itself (no second
    call), and '채널' in the usual top-left logo mc_logo (bitmap 1840). Content 0
    is the same as revision 8. Lead Dolphin check: the logo is fixed, the settings
    tooltips are still cut exactly as on the console.
    revision 10: revision 9 + the tooltip centerWidth setter ignores undefined/null
    (a harmless guard; Dolphin: still cut).
    revision 11: revision 10 + HSGridButton (the settings cards) sets the tooltip width with
    the same kwceTipWidth instead of text.length * 15; that later width was what the body
    and label followed while the NaN x offset froze the positions (Dolphin probe).
    Lead Dolphin check: all four settings tooltips fit.
    Content 1 (DOL) is the same in revisions 4-11.
    """
    from .channel_korean_font import korean_shared_fonts
    if revision not in REVISIONS:
        raise ValueError('Unknown Kirby TV revision')
    ui, system, pairs = tables(revision)
    glyphs = swf_glyphs(revision, ui, system)
    title, base_record = wiilink_title()
    reference, _ = wiilink_title()
    record = dict(title_id=TITLE_ID, version=257, boot_index=12, inputs=base_record,
                  ui_table_sha256=sha256(UI_TABLES[revision].read_bytes()), system_table_sha256=sha256(SYSTEM_TABLE.read_bytes()))
    if revision >= 2:
        record.update(revision=revision, ui_table=UI_TABLES[revision].relative_to(ROOT).as_posix(),
                      swf_glyphs_table=GLYPHS[revision].relative_to(ROOT).as_posix(),
                      swf_glyphs_table_sha256=sha256(GLYPHS[revision].read_bytes()))
    missing = missing_units(revision)
    if missing:
        record.update(missing_ids_table=MISSING[revision].relative_to(ROOT).as_posix(),
                      missing_ids_table_sha256=sha256(MISSING[revision].read_bytes()))
    logos = None
    if revision >= 8:
        from .kirbytv_logo import korean_logo_set
        logos = korean_logo_set(ChannelArchive(title.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH),
                                mc_logo=revision >= 9)
        record['logos'] = logos['record']
    banner = title.get_content_by_index(0)
    if revision >= 5:
        from .kirbytv_banner import korean_banner_art
        banner, record['banner_art'] = korean_banner_art(banner, style=3 if revision >= 7 else 2 if revision >= 6 else 1,
                                                         logos=logos)
    banner, record['imet'] = korean_imet(banner, system['name'])
    title.set_content(banner, 0)
    executable, record['executable'] = kirbytv_dol.patch_content(title.get_content_by_index(1))
    title.set_content(executable, 1)
    content2, record['content2'] = korean_content2(title.get_content_by_index(2), system, pairs, local,
                                                   font_glyphs=glyphs, dates=revision >= 2, missing=missing,
                                                   days=revision >= 4, time_zone=revision >= 4,
                                                   tooltip='guarded' if revision >= 10 else 'once' if revision >= 9
                                                   else revision >= 8,
                                                   bitmaps=logos['bitmaps'] if logos else None,
                                                   hs_tooltip=revision >= 11)
    title.set_content(content2, 2)
    home, record['home'] = korean_home(title, system)
    for index, data in home.items():
        title.set_content(data, index)
    fonts, record['shared_fonts'] = korean_shared_fonts()
    if set(ChannelArchive(title.get_content_by_index(10)).files) != set(ChannelArchive(fonts).files):
        raise ValueError('Shared font content layout differs')
    title.set_content(fonts, 10)
    record['ui_entries'] = len(ui['entries'])
    record['ui_distinct_sources'] = len(pairs)
    return title, reference, record


def changed_contents(title, reference):
    return [i for i in range(len(title.tmd.content_records))
            if title.get_content_by_index(i) != reference.get_content_by_index(i)]
