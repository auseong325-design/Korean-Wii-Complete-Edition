"""Assemble the Korean Internet Channel WAD from the pinned USA v1024 original.

local=True  -> emulator test build: service/update URLs and default favorites
               point at the loopback fixture server (http://127.0.0.2).
local=False -> hardware candidate resources: original URLs and favorites,
               translated titles only. The caller fakesigns via kwce.hardware.
Changed contents: 0 banner, 1 executable, 2 pages/manual/favorites, 3 save
banner, 4 Opera font (shared), 5 HOME Menu/keyboard, 6 language files,
8 system font (shared). Contents 7, 9-12 stay byte-identical.
"""
import hashlib
import io
import json

from .channels import ROOT, ChannelArchive, load_library
from . import internet_error_dialog as ed, internet_error_headings as eh, internet_exe, internet_resources as res

ORIGINAL = ROOT / 'workspace/channels/internet/originals/internet-usa-v1024.wad'
ORIGINAL_SHA256 = '5c9fee70aac2a4be562d22d3a79d25b84013ba0549c8bdb9bb83ae6860e249bd'
TITLE_ID = '0001000148414445'
CHANGED = [0, 1, 2, 3, 4, 5, 6, 8]
CONFIGS = {name: f'configs/internet-{name}-v1-ko.json' for name in ('lng', 'manual', 'ui', 'exe')}
REVISION_CONFIGS = {4: {'v4': 'configs/internet-v4-ko.json'}, 5: {'v5': 'configs/internet-v5-ko.json'},
                    6: {'v6': 'configs/internet-v6-ko.json', 'manual_images': 'configs/internet-manual-images-v6-ko.json'},
                    7: {'v7': 'configs/internet-v7-ko.json'}, 8: {'v8': 'configs/internet-v8-ko.json'}}
REVISIONS = (1, 2, 3, 4, 5, 6, 7, 8)


def config_paths(revision):
    """Config files a revision reads (recorded in build manifests)."""
    paths = dict(CONFIGS)
    for since, extra in REVISION_CONFIGS.items():
        if revision >= since:
            paths.update(extra)
    return paths


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def configs(revision=1):
    return {k: json.loads((ROOT / v).read_text(encoding='utf-8')) for k, v in config_paths(revision).items()}


def _ttf_cmap():
    load_library()
    from fontTools.ttLib import TTFont
    from .opera_font import KOREAN_SHARED
    raw = ChannelArchive(KOREAN_SHARED.read_bytes()).get('Wii-kr_Round Gothic B.ttf')
    return set(TTFont(io.BytesIO(raw)).getBestCmap())


def _rfna_codes(shared):
    from .channel_font import font_data
    arc = ChannelArchive(shared)
    codes = set()
    for name in arc.files:
        codes |= set(font_data(b'RFNT' + arc.get(name)[4:])[1])
    return codes


def _missing(texts, codes):
    import html
    out = set()
    for t in texts:
        t = html.unescape(internet_manual_placeholders(t)).replace('\\n', '')
        out |= {c for c in t if ord(c) >= 0x20 and ord(c) not in codes}
    return sorted(out)


def internet_manual_placeholders(text):
    import re
    return re.sub(r'\{\d+\}', '', text)


def build(*, local, revision=1):
    """revision 1: first build. revision 2: Korean text in UI pages that declare
    no charset is written as character references (encoding independent).
    revision 3: Dolphin review fixes -- per-face TTC names so the manual and web
    content render, first-run favorites import kept intact, English keyboard
    labels (the keyboard font cannot show Hangul). revision 4: keyboard input hints in
    English, local test-favorite thumbnails. revision 5: local first favorite points at
    the test index (not the Yahoo! redirect template), Korean fallback encoding (euc-kr).
    revision 6: Korean software keyboard (wbf1 'wii_name' group also loads the KS X 1001
    Hangul sheets; Korean command labels, dictionary abbreviations and input hints),
    Korean manual pictures, smaller error-page heading. revision 7: long single-sentence
    error headings carry a word-boundary line break and the error page h1 uses
    white-space: pre-line (kwce.internet_error_headings), so Opera stops ending a heading
    line inside a word. revision 8: every coded error message is re-broken for the error
    dialog's text column (dialog.html, narrower than the page heading; kwce.internet_error_dialog)
    instead of the v7 breaks; the v7 error.css pre-line stays."""
    if revision not in REVISIONS:
        raise ValueError('Unknown Internet Channel build revision')
    raw = ORIGINAL.read_bytes()
    if sha256(raw) != ORIGINAL_SHA256:
        raise ValueError('USA Internet Channel original differs')
    cfg = configs(revision)
    v4 = cfg.get('v4')
    v5 = cfg.get('v5')
    v6 = cfg.get('v6')
    v7 = cfg.get('v7')
    v8 = cfg.get('v8')
    lib = load_library()
    title = lib.title.Title()
    title.load_wad(raw)
    if title.tmd.title_id != TITLE_ID or title.tmd.title_version != 1024 or title.tmd.boot_index != 12:
        raise ValueError('Internet Channel identity differs')
    original = [title.get_content_by_index(i) for i in range(title.tmd.num_contents)]
    manifest = dict(title_id=TITLE_ID, base_region='USA', base_version=1024, source_sha256=ORIGINAL_SHA256, local_only=local,
                    full_localization_complete=False, hardware_success_verified=False)

    # 6: language files (english.lng is what language 9 loads); v4/v5 keep the
    # keyboard-only input hints in English (keyboard font group has no Hangul), v6 translates them
    c6 = ChannelArchive(original[6])
    korean_lng, manifest['language_file'] = res.korean_lng(c6.get('english.lng'), cfg['lng'],
                                                           keep_english=v4['lng_keep_english'] if v4 and not v6 else None)
    if v8:
        korean_lng, manifest['error_message_breaks'] = ed.apply_breaks(korean_lng, v8['error_breaks'])
    elif v7:
        korean_lng, manifest['error_heading_breaks'] = eh.apply_breaks(korean_lng, v7['error_heading_breaks'])
    c6 = ChannelArchive(c6.replace('english.lng', korean_lng))
    if v5:
        enc = v5['fallback_encoding']
        c6, done6 = res.prefs(c6, enc['files']['6'], enc)

    # 2: internal pages, manual, text images, favorites, copy of the language file
    c2 = ChannelArchive(original[2])
    if c2.get('english.lng') != ChannelArchive(original[6]).get('english.lng'):
        raise ValueError('Content 2 language file copy differs')
    c2 = ChannelArchive(c2.replace('english.lng', korean_lng))
    c2, manifest['pages'] = res.localize_pages(c2, cfg['ui']['html'], ncr_undeclared=revision >= 2)
    c2, manifest['manual'] = res.localize_manual(c2, cfg['manual'])
    c2, manifest['images'] = res.relabel_images(c2, cfg['ui']['images'])
    if v6:
        from .internet_manual_images import manual_images
        c2, manifest['manual_images'] = manual_images(c2, cfg['manual_images'])
        c2, manifest['error_heading'] = res.css_value(c2, v6['error_heading'])
    if v7:
        c2, manifest['error_heading_wrap'] = res.css_value(c2, v7['error_heading_css'])
    c2, manifest['favorites'] = res.favorites(c2, cfg['ui']['favorites'], local=local, keep_listing=revision >= 3)
    if v4 and local:
        c2, manifest['test_thumbnails'] = res.full_image_labels(c2, v4['local_thumbnails'])
    if v5:
        c2, done2 = res.prefs(c2, enc['files']['2'], enc)

    # 5: HOME Menu always; software keyboard labels before v3 and from v6 (v3-v5 keep
    # the original English: the keyboard font group then rendered Hangul as missing-glyph).
    translate_keyboard = revision < 3 or revision >= 6
    c5 = ChannelArchive(original[5])
    c5, manifest['home_menu'] = res.home(c5, cfg['ui']['home'])
    if translate_keyboard:
        c5, manifest['keyboard_layouts'] = res.keyboard(c5, cfg['ui'])
    else:
        manifest['keyboard_layouts'] = dict(translated=False, reason='keyboard font lacks usable Hangul; English labels kept')

    keyboard_rows = cfg['exe']['keyboard']
    if v6:
        keyboard_rows = [r for r in keyboard_rows if r['en'] not in v6['keyboard_rows_keep_english']]
    c0, manifest['banner'] = res.banner(original[0], cfg['ui']['banner'], cfg['ui']['display_name'])
    c1, manifest['executable'] = internet_exe.build_executable(original[1], cfg['exe'], local=local, translate_keyboard=translate_keyboard,
                                                               local_targets=v5['local_url_targets'] if v5 else None,
                                                               keyboard_rows=keyboard_rows if v6 else None,
                                                               utf16_rows=v6['keyboard_labels'] if v6 else None)
    c3, manifest['save_banner'] = res.save_banner(original[3], cfg['ui']['save_banner'])
    if v5:
        c3_archive, done3 = res.prefs(ChannelArchive(c3), enc['files']['3'], enc)
        c3 = c3_archive.compact()
        manifest['fallback_encoding'] = dict(section=enc['section'], key=enc['key'], value=enc['value'],
                                             files={'2': done2, '3': done3, '6': done6}, seed='content 3 operarc.nand -> save operarc')
    # v3 restores each TTC face's original name records so web content (manual,
    # remote pages) can resolve 'Wii NTLG PGothic Regular' by the font's name.
    if revision >= 3:
        from .internet_opera_font import korean_opera_font
    else:
        from .opera_font import korean_opera_font
    c4, manifest['opera_font'] = korean_opera_font(original[4])
    if v8:
        metrics = eh.Metrics(eh.opera_face(c4))
        manifest['error_message_breaks'].update(ed.check(v8['error_breaks'], cfg['lng']['translations'], metrics, c2))
    elif v7:
        metrics = eh.Metrics(eh.opera_face(c4))
        manifest['error_heading_breaks'].update(eh.check(v7['error_heading_breaks'], cfg['lng']['translations'], metrics))
    from .channel_korean_font import korean_shared_fonts
    c8, manifest['shared_fonts'] = korean_shared_fonts()
    keyboard_texts = []
    if translate_keyboard:
        keyboard_texts += [v[1] for layout in cfg['ui']['keyboard_layouts'].values() for v in layout.values()]
        keyboard_texts += [row['ko'] for row in keyboard_rows]
    if v6:
        keyboard_texts += [r['ko'] for r in v6['keyboard_labels']] + [cfg['lng']['translations'][k] for k in v6['lng_hints']]
        from .internet_keyboard_font import keyboard_font
        c8, manifest['keyboard_font'] = keyboard_font(c8, v6['keyboard_font'], keyboard_texts)

    # glyph coverage: Opera pages use the Korean TTC, keyboard/banner the system font
    ttf = _ttf_cmap()
    opera_texts = list(cfg['lng']['translations'].values()) + list(cfg['manual']['translations'].values())
    opera_texts += [v for page in cfg['ui']['html'].values() for v in page.values()]
    system_texts = [v[1] for spec in cfg['ui']['banner'].values() for v in spec['texts'].values()]
    system_texts += [cfg['ui']['display_name']]
    system_texts += keyboard_texts
    gaps = dict(opera_font=_missing(opera_texts, ttf), system_font=_missing(system_texts, _rfna_codes(c8)))
    if any(gaps.values()):
        raise ValueError(f'Korean glyphs missing: {gaps}')
    manifest['glyph_coverage'] = dict(opera_font_texts=len(opera_texts), system_font_texts=len(system_texts), missing=0)

    contents = {0: c0, 1: c1, 2: c2.compact(), 3: c3, 4: c4, 5: c5.compact(), 6: c6.compact(), 8: c8}
    for index, data in contents.items():
        title.set_content(data, index)
    title.tmd.region = 4
    wad = title.dump_wad()
    check = lib.title.Title()
    check.load_wad(wad)
    changed = [i for i in range(len(original)) if check.get_content_by_index(i) != original[i]]
    if changed != CHANGED:
        raise ValueError(f'Unexpected changed contents {changed}')
    manifest.update(changed_contents=changed, preserved_contents=[i for i in range(len(original)) if i not in changed],
                    tmd_region=4, contents=len(original), boot_index=12, ios=title.tmd.ios_tid,
                    content_sha256={str(i): sha256(check.get_content_by_index(i)) for i in changed})
    return wad, manifest
