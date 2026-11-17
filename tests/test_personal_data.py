import hashlib
import json
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from kwce import personal_data_format as fmt  # noqa: E402
from kwce import personal_data_fork as fork  # noqa: E402
from kwce import personal_data_hangul as H  # noqa: E402

CHANNEL = ROOT / 'workspace/channels/personal-data'
CONFIG = json.loads((ROOT / 'configs/personal-data-messages-v1-ko.json').read_text(encoding='utf-8'))
TEMPLATE = fork.SOURCE / 'data/title/pd_decrypted.dat'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_language(data):
    """Python port of gettext.cpp LoadLanguage/memfgets (200-byte line buffer)."""
    messages, last = {}, None
    for line in data.split(b'\n')[:-1]:  # memfgets drops text after the last newline
        if len(line) >= 200:
            raise ValueError('line overflows LoadLanguage buffer')
        if line.startswith(b'#'):
            continue
        if line.startswith(b'msgid "'):
            body = line[7:]
            end = body.rfind(b'"')
            last = body[:end].decode('utf-8') if end > 1 else None
        elif line.startswith(b'msgstr "') and last is not None:
            body = line[8:]
            end = body.rfind(b'"')
            if end > 1:
                messages[last] = body[:end].decode('utf-8')
            last = None
    return messages


class HangulModelTest(unittest.TestCase):
    def test_composition_examples(self):
        cases = {'ㅎㅏㄴㄱㅡㄹ': '한글', 'ㄷㅏㄹㄱ': '닭', 'ㄷㅏㄹㄱㅏ': '달가', 'ㅇㅗㅏ': '와',
                 'ㅅㅓㅇㅜㄹ ㅌㅡㄱㅂㅕㄹㅅㅣ': '서울 특별시', 'ㄱㅏㅂㅅ\b': '갑', 'ㅂㅜㅓㄹ\b\b': '부',
                 'ㄱ\b': '', 'ㅇㅏㄴ ㄴ\b\b': '안', 'ㄲㅗㅊ': '꽃', 'ㅇㅢ': '의'}
        for keys, expected in cases.items():
            self.assertEqual(H.type_sequence(keys), expected, keys)

    def test_length_limit_matches_keyboard_rule(self):
        text = H.type_sequence('ㄱㅏㄴㅏㄷㅏ', maxlen=3)
        self.assertEqual(text, '가낟')
        self.assertLessEqual(len(text), 2)

    def test_layout_is_two_beolsik(self):
        self.assertEqual(''.join(H.key(1, c) for c in range(10)), 'ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ')
        self.assertEqual(''.join(H.key(2, c) for c in range(9)), 'ㅁㄴㅇㄹㅎㅗㅓㅏㅣ')
        self.assertEqual(''.join(H.key(3, c) for c in range(7)), 'ㅋㅌㅊㅍㅠㅜㅡ')
        self.assertEqual(''.join(H.key(1, c, True) for c in range(10)), 'ㅃㅉㄸㄲㅆㅛㅕㅑㅒㅖ')
        self.assertIsNone(H.key(0, 0))
        self.assertIsNone(H.key(1, 10))
        self.assertIsNone(H.key(3, 7))

    def test_c_tables_follow_the_model(self):
        tables = H.c_tables()
        self.assertIn('static const unsigned short KWCE_JONG[28]', tables)
        self.assertIn('KWCE_FINAL_PAIRS[11][3]', tables)
        self.assertIn('KWCE_VOWEL_PAIRS[7][3]', tables)
        manifest = CHANNEL / 'build-v1/build-manifest.json'
        if manifest.exists():
            written = json.loads(manifest.read_text(encoding='utf-8'))['fork']['written']
            self.assertEqual(written['source/gui/kwce_hangul_tables.h'], sha256(fork.tables_header().encode()))
            self.assertEqual(written['source/gui/kwce_hangul.c'], sha256(fork.HANGUL_C.encode()))


class CatalogTest(unittest.TestCase):
    def test_every_inventory_msgid_is_translated_or_kept(self):
        inventory = json.loads((CHANNEL / 'text-inventory-v1.json').read_text(encoding='utf-8'))
        ids = {row['msgid'] for row in inventory['msgids']}
        self.assertEqual(len(ids), 42)
        self.assertEqual(set(CONFIG['messages']) | set(CONFIG['kept_english']), ids)
        self.assertFalse(set(CONFIG['messages']) & set(CONFIG['kept_english']))
        self.assertEqual(len(inventory['console_messages']), 19)

    def test_catalog_parses_like_the_device(self):
        data, count = fork.ko_catalog()
        expected = dict(CONFIG['messages'])
        expected.update(CONFIG['kwce_messages'])
        self.assertEqual(load_language(data), expected)
        self.assertEqual(count, 41)
        for msgid, text in expected.items():
            self.assertGreaterEqual(len(msgid), 2)
            self.assertNotIn('"', text)
            self.assertTrue(re.search('[\uac00-\ud7a3]', text), msgid)
            self.assertEqual(re.findall('%[a-z]', msgid), re.findall('%[a-z]', text))

    def test_no_gettext_hash_collisions(self):
        msgids = set(CONFIG['messages']) | set(CONFIG['kwce_messages']) | set(CONFIG['kept_english'])
        hashes = {}
        for msgid in msgids:
            self.assertNotIn(fork.hash_string(msgid), hashes, msgid)
            hashes[fork.hash_string(msgid)] = msgid
        # GuiText applies gettext again to translated text; it must not hit another msgid.
        for text in list(CONFIG['messages'].values()) + list(CONFIG['kwce_messages'].values()):
            self.assertNotIn(fork.hash_string(text), hashes, text)


class FormatTest(unittest.TestCase):
    def test_template_only_clears_fields_and_pads(self):
        upstream = TEMPLATE.read_bytes()
        plain, record = fmt.korean_template(upstream)
        self.assertEqual(len(plain), fmt.LENGTH)
        self.assertTrue(fmt.check(plain))
        self.assertEqual(plain[fmt.TEMPLATE_LENGTH:], bytes(16))
        allowed = [(a, a + s) for a, s in fmt.FIELDS.values()]
        changed = [i for i in range(len(upstream)) if upstream[i] != plain[i]]
        self.assertTrue(changed)
        self.assertTrue(all(any(a <= i < b for a, b in allowed) for i in changed))
        self.assertTrue(all(v == '' for k, v in fmt.fields(plain).items() if isinstance(v, str)))
        self.assertEqual(record['padded_bytes'], 16)

    def test_offsets_match_spd_writer(self):
        source = (fork.SOURCE / 'source/channel/pd_info.cpp').read_text(encoding='latin-1')
        offsets = {int(n) for n in re.findall(r'memcpy\(filePointer \+ (\d+),', source)}
        self.assertEqual(offsets, {at for at, _ in fmt.FIELDS.values()} | {fmt.PIN_MAGIC[0], fmt.PIN[0]})
        region = (fork.SOURCE / 'source/channel/region.c').read_text(encoding='latin-1')
        self.assertIn('"%s"' % fmt.PATH, region)

    def test_encryption_roundtrip_with_synthetic_id(self):
        plain = fmt.fictional_sample(fmt.korean_template(TEMPLATE.read_bytes())[0])
        device = 0x01020304  # synthetic; never a real console ID
        key, iv = fmt.key_iv(device)
        self.assertEqual(bytes(key[i] for i in (7, 15, 23, 31)), device.to_bytes(4, 'big'))
        self.assertEqual(iv[12:], device.to_bytes(4, 'big'))
        data = fmt.encrypt(plain, device)
        self.assertNotEqual(data, plain)
        self.assertEqual(fmt.decrypt(data, device), plain)
        self.assertNotEqual(fmt.decrypt(data, device + 1)[:5], b'PDFF\x02')
        values = fmt.fields(plain)
        self.assertEqual(values['last_name'], '홍')
        self.assertEqual(values['kana_first_name'], values['first_name'])
        self.assertTrue(values['email_address'].endswith('@example.com'))

    def test_local_feed_is_fictional_and_serves_nothing(self):
        folder = CHANNEL / 'local-feed-v1'
        if not folder.exists():
            self.skipTest('local-feed-v1 not created')
        manifest = json.loads((folder / 'fixture-manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest['local_only'] and manifest['synthetic'] and manifest['fictional'])
        for row in manifest['files']:
            self.assertEqual(sha256((folder / row['path']).read_bytes()), row['sha256'])
        self.assertEqual((folder / 'routes.tsv').read_bytes(), b'')
        self.assertEqual(manifest['values'], fmt.FICTIONAL)

    def test_reading_channels_share_the_pd_sdk(self):
        from kwce.channels import load_library
        key_text = (fork.SOURCE / 'source/channel/pd_data.h').read_text(encoding='latin-1')
        key = fmt._array(key_text, 'PERSONAL_DATA_KEY[32]')
        iv = fmt._array(key_text, 'PERSONAL_DATA_IV[16]')
        pattern = b''.join(re.escape(key[8 * i:8 * i + 7]) + b'.' for i in range(4))[:-1]
        wads = {'wiiroom': 'wiiroom/originals/wiiroom-japan-v1025.wad', 'food': 'food/originals/food-japan-v512.wad',
                'photoprints': 'photoprints/originals/digicam-japan-v1024.wad'}
        lib = load_library()
        for name, rel in wads.items():
            path = ROOT / 'workspace/channels' / rel
            if not path.exists():
                self.skipTest(name + ' original not available')
            title = lib.title.Title()
            title.load_wad(path.read_bytes())
            dol = title.get_content_by_index(1)
            if dol[:1] == b'\x11':
                from kwce.wiiroom_formats import decompress_lz11
                dol = decompress_lz11(dol)
            self.assertEqual(dol[:4], b'\x00\x00\x01\x00', name)
            self.assertEqual(len(re.findall(pattern, dol, re.S)), 1, name)
            self.assertEqual(dol.count(iv[:12]), 1, name)
            self.assertIn(fmt.PATH.encode(), dol, name)


class ForkTest(unittest.TestCase):
    def test_patches_apply_to_pinned_source_only_outside_pd_code(self):
        template = fmt.korean_template(TEMPLATE.read_bytes())[0]
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp) / 'set-personal-data'
            shutil.copytree(fork.SOURCE, tree)
            record = fork.apply(tree, b'FONT', template)
            self.assertEqual(record['patches'], len(fork.PATCHES))
            self.assertIn('CONF_LANG_KOREAN', (tree / 'source/gui/gettext.cpp').read_text(encoding='latin-1'))
            self.assertIn('kwce_hangul_type', (tree / 'source/gui/gui_keyboard.cpp').read_text(encoding='latin-1'))
            self.assertIn('KwceFieldCapacity(input)', (tree / 'source/channel/menu.cpp').read_text(encoding='latin-1'))
            self.assertIn('-Wno-error=template-id-cdtor', (tree / 'Makefile').read_text())
            self.assertFalse((tree / 'data/fonts/noto_sans_jp_regular.otf').exists())
            self.assertEqual((tree / 'data/title/pd_decrypted.dat').read_bytes(), template)
            for path in fork.UNCHANGED:
                self.assertEqual((tree / path).read_bytes(), (fork.SOURCE / path).read_bytes(), path)
            for path in ['source/gui/gui.h', 'source/gui/gui_keyboard.cpp', 'source/gui/gettext.cpp', 'source/gui/filelist.h']:
                data = (tree / path).read_bytes()
                self.assertEqual(data.count(b'\n'), data.count(b'\r\n'), path)


class LabelWidthTest(unittest.TestCase):
    """FreeTypeGX advances (advance.x >> 6, no kerning) for labels without wrapping."""

    def width(self, font, text, size):
        cmap = font.getBestCmap()
        upem = font['head'].unitsPerEm
        return sum(round(font['hmtx'][cmap[ord(c)]][0] * size / upem) for c in text)

    def test_unwrapped_labels_fit(self):
        import io
        from kwce.channels import load_library
        from kwce.personal_data_font import korean_font
        load_library()
        from fontTools.ttLib import TTFont
        font = TTFont(io.BytesIO(korean_font()[0]))
        m = CONFIG['messages']
        circle = ['Done', 'Cancel', 'PIN', 'Back', 'OK', 'Enter', 'Exit', 'Retry', 'Main Menu', 'Wii Menu', 'Demae', 'Digicam']
        for msgid in circle:  # 196 px circle buttons; main pages wrap at 196 - 30
            self.assertLessEqual(self.width(font, m[msgid], 22), 166, msgid)
        keys = [CONFIG['kwce_messages']['Backspace'], CONFIG['kwce_literals']['hangul_toggle_key'], 'Caps', 'Shift']
        for label in keys:  # 80 px medium keys at 20 px
            self.assertLessEqual(self.width(font, label, 20), 70, label)
        for jamo in ''.join(H.LAYOUT.values()) + ''.join(H.SHIFTED.values()):  # 40 px keys
            self.assertLessEqual(self.width(font, jamo, 20), 30, jamo)
        for msgid in ['Set Personal Data', 'Input PIN', 'Edit PIN', 'Email Address', 'Phone Number', 'Apartment Number']:
            self.assertLessEqual(self.width(font, m[msgid], 28), 600, msgid)
        for msgid, text in m.items():  # dialog messages wrap at spaces within 400 px
            for word in text.split(' '):
                self.assertLessEqual(self.width(font, word, 22), 400, msgid)


BUILDS = [r for r in (1, 2) if (CHANNEL / f'build-v{r}/build-manifest.json').exists()]
CHANNEL_ENTRY = 0x80003400


def read_manifest(folder):
    return json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))


def dol_sections(dol):
    rows = []
    for i in range(18):
        off, addr, size = (struct.unpack_from('>I', dol, base + 4 * i)[0] for base in (0, 0x48, 0x90))
        if size:
            rows.append((i, off, addr, size))
    return rows


def decode_branch(dol, address):
    """Independent decode of the instruction at `address`: (opcode, AA, LK, target)."""
    for i, off, addr, size in dol_sections(dol):
        if i < 7 and addr <= address < addr + size:
            word = struct.unpack_from('>I', dol, off + address - addr)[0]
            disp = word & 0x03fffffc
            if disp & 0x02000000:
                disp -= 0x04000000
            target = disp if word & 2 else (address + disp) & 0xffffffff
            return word >> 26, (word >> 1) & 1, word & 1, target
    return None


def synthetic_dol(entry=0x80003f00, words=8):
    body = struct.pack(f'>{words}I', *([0x60000000] * words))
    header = bytearray(0x100)
    struct.pack_into('>I', header, 0, 0x100)
    struct.pack_into('>I', header, 0x48, entry)
    struct.pack_into('>I', header, 0x90, len(body))
    struct.pack_into('>II', header, 0xd8, 0x80100000, 0x100)
    struct.pack_into('>I', header, 0xe0, entry)
    return bytes(header) + body


class ChannelEntryTest(unittest.TestCase):
    """ES/Dolphin start a NAND title's boot DOL at 0x80003400 (real mode), not at the DOL entry."""

    def assert_channel_entry(self, dol, linked_entry):
        covering = [s for s in dol_sections(dol) if s[0] < 7 and s[2] <= CHANNEL_ENTRY < s[2] + s[3]]
        self.assertEqual(len(covering), 1, 'one text section must cover 0x80003400')
        opcode, absolute, link, target = decode_branch(dol, CHANNEL_ENTRY)
        self.assertEqual((opcode, absolute, link), (18, 0, 0), 'relative, non-linking branch (valid in real mode)')
        self.assertEqual(target, linked_entry)
        self.assertTrue(any(s[0] < 7 and s[2] <= target < s[2] + s[3] for s in dol_sections(dol) if s != covering[0]))
        from kwce.personal_data_boot import channel_entry
        self.assertEqual(int(channel_entry(dol)['branch_target'], 16), linked_entry)

    def test_stub_on_synthetic_dol(self):
        from kwce.dvd_channel_boot import channel_boot
        from kwce.personal_data_boot import channel_entry
        linked = synthetic_dol()
        with self.assertRaises(ValueError):
            channel_entry(linked)
        dol, record = channel_boot(linked)
        self.assertTrue(record['required'])
        self.assert_channel_entry(dol, 0x80003f00)
        self.assertEqual(struct.unpack_from('>I', dol, 0xe0)[0], CHANNEL_ENTRY)

    def test_build_v2_branches_to_linked_entry(self):
        if 2 not in BUILDS:
            self.skipTest('build-v2 not built')
        from kwce.channels import load_library
        from build_personal_data import WAD_NAME
        build = CHANNEL / 'build-v2'
        m = read_manifest(build)
        dol = (build / 'boot.dol').read_bytes()
        linked_entry = int(m['channel_boot']['linked_entry'], 16)
        self.assert_channel_entry(dol, linked_entry)
        title = load_library().title.Title()
        title.load_wad((build / WAD_NAME).read_bytes())
        self.assertEqual(title.get_content_by_index(title.tmd.boot_index), dol)
        self.assertEqual(sha256(dol), m['dol_sha256'])
        if 1 in BUILDS:
            v1 = (CHANNEL / 'build-v1/boot.dol').read_bytes()
            self.assertEqual(sha256(v1), m['linked_dol_sha256'])
            self.assertEqual(struct.unpack_from('>I', v1, 0xe0)[0], linked_entry)
            stub = [s for s in dol_sections(dol) if s[2] == CHANNEL_ENTRY]
            self.assertEqual(len(stub), 1)
            self.assertEqual(stub[0][3], 32)
            self.assertEqual({(a, s): v1[o:o + s] for _, o, a, s in dol_sections(v1)},
                             {(a, s): dol[o:o + s] for _, o, a, s in dol_sections(dol) if a != CHANNEL_ENTRY})

    def test_preserved_v1_has_no_channel_entry(self):
        if 1 not in BUILDS:
            self.skipTest('build-v1 not built')
        from kwce.personal_data_boot import channel_entry
        v1 = (CHANNEL / 'build-v1/boot.dol').read_bytes()
        self.assertIsNone(decode_branch(v1, CHANNEL_ENTRY))  # the Dolphin IntCPU panic of 2026-10-28
        with self.assertRaises(ValueError):
            channel_entry(v1)


class ArtifactTest(unittest.TestCase):
    def setUp(self):
        if not BUILDS:
            self.skipTest('no personal-data build')
        self.build = CHANNEL / f'build-v{BUILDS[-1]}'
        self.manifest = read_manifest(self.build)

    def test_local_build_identity(self):
        from build_personal_data import WAD_NAME, wiilink_title
        from kwce.channels import load_library
        original, contents = wiilink_title()
        catalog, _ = fork.ko_catalog()
        template = fmt.korean_template(TEMPLATE.read_bytes())[0]
        for rev in BUILDS:
            with self.subTest(revision=rev):
                build = CHANNEL / f'build-v{rev}'
                m = read_manifest(build)
                self.assertEqual(m['revision'], rev)
                self.assertTrue(m['local_only'])
                self.assertFalse(m['full_localization_complete'])
                self.assertFalse(m['hardware_success_verified'])
                wad = (build / WAD_NAME).read_bytes()
                dol = (build / 'boot.dol').read_bytes()
                self.assertEqual(sha256(wad), m['wad_sha256'])
                title = load_library().title.Title()
                title.load_wad(wad)
                self.assertEqual(title.tmd.title_id, '000100084843434a')
                self.assertEqual((title.tmd.ios_tid, title.tmd.region, title.tmd.title_version, title.tmd.boot_index, title.tmd.access_rights),
                                 ('000000010000003a', 3, 512, 1, 3))
                self.assertEqual(title.get_content_by_index(0), contents[0])
                self.assertEqual(title.get_content_by_index(1), dol)
                self.assertIn(catalog, dol)
                self.assertIn(template, dol)
                for local in (b'127.0.0', b'localhost'):
                    self.assertEqual(dol.count(local), 0)

    def test_font_is_deterministic_and_covers_ui(self):
        from kwce.personal_data_font import korean_font, coverage
        font, record = korean_font()
        self.assertEqual(record['sha256'], self.manifest['font']['sha256'])
        self.assertIn(font, (self.build / 'boot.dol').read_bytes())
        text = ''.join(CONFIG['messages'].values()) + ''.join(CONFIG['kwce_messages'].values()) + CONFIG['kwce_literals']['hangul_toggle_key']
        text += ''.join(H.LAYOUT.values()) + ''.join(H.SHIFTED.values()) + ''.join(fmt.FICTIONAL.values())
        self.assertEqual(coverage(font, text), [])
        self.assertEqual(record['hangul_syllables'], 11172)
        self.assertEqual(record['license'], 'OFL-1.1')

    def test_hardware_candidates_match_local_builds(self):
        from kwce.channels import load_library
        from build_personal_data import WAD_NAME
        lib = load_library()
        checked = 0
        for rev in BUILDS:
            hardware = CHANNEL / f'hardware-v{rev}'
            if not (hardware / 'build-manifest.json').exists():
                continue
            with self.subTest(revision=rev):
                m = read_manifest(hardware)
                self.assertFalse(m['hardware_success_verified'])
                self.assertFalse(m['installed_anywhere'])
                wad = (hardware / 'personal-data-ko-hardware-candidate.wad').read_bytes()
                self.assertEqual(sha256(wad), m['wad_sha256'])
                a, b = lib.title.Title(), lib.title.Title()
                a.load_wad((CHANNEL / f'build-v{rev}' / WAD_NAME).read_bytes())
                b.load_wad(wad)
                self.assertTrue(b.get_is_fakesigned())
                for i in range(2):
                    self.assertEqual(a.get_content_by_index(i), b.get_content_by_index(i))
                if rev >= 2:
                    self.assertEqual(m['hardware_checks']['channel_entry']['address'], hex(CHANNEL_ENTRY))
                    self.assertEqual(decode_branch(b.get_content_by_index(1), CHANNEL_ENTRY)[0], 18)
                checked += 1
        if not checked:
            self.skipTest('no hardware candidate built')

    def test_hardware_guard_refuses_other_titles_and_missing_entry(self):
        from kwce.personal_data_hardware import hardware_wad
        from build_personal_data import wiilink_title, WAD_NAME
        wiilink = wiilink_title()[0]
        other = ROOT / 'workspace/channels/tvguide/originals/tvguide-japan-original.wad'
        if other.exists():
            with self.assertRaises(ValueError):
                hardware_wad(other.read_bytes(), wiilink)
        if 1 in BUILDS:
            with self.assertRaises(ValueError):  # no code at 0x80003400
                hardware_wad((CHANNEL / 'build-v1' / WAD_NAME).read_bytes(), wiilink)


if __name__ == '__main__':
    unittest.main()
