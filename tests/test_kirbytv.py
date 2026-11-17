"""Unit tests for the Kirby TV Channel Korean localization (no Dolphin)."""
import hashlib
import json
import math
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, ChannelArchive
from kwce import (bspatch, kirbytv_u8, kirbytv_swf, kirbytv_dol, kirbytv_text,
                  kirbytv_fixtures, kirbytv_build, kirbytv_swf_font)
from kwce.wiiroom_formats import decompress_lz11

WAD = ROOT / 'workspace/channels/kirbytv/originals/kirbytv-europe-v257.wad'
PATCH = ROOT / 'workspace/channels/kirbytv/references/wiilink-patcher/bsdiff__ktv__ktv_2.bsdiff'


def _title():
    lib = load_library()
    t = lib.title.Title()
    t.load_wad(WAD.read_bytes())
    return t


class TestInputs(unittest.TestCase):
    def test_source_hashes(self):
        self.assertEqual(hashlib.sha256(WAD.read_bytes()).hexdigest(), kirbytv_build.WAD_SHA256)
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), kirbytv_build.PATCH_SHA256)


class TestBspatch(unittest.TestCase):
    def test_ktv2_applies(self):
        t = _title()
        new = bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes())
        a, b = ChannelArchive(t.get_content_by_index(2)), ChannelArchive(new)
        self.assertEqual(len(a.files), 163)
        self.assertEqual(len(b.files), 191)
        self.assertEqual(hashlib.sha256(new).hexdigest()[:16], kirbytv_build.WIILINK_CONTENT2_SHA256)


class TestU8(unittest.TestCase):
    def test_identity(self):
        t = _title()
        for i in (5, 6, 7, 8, 9, 10, 11):
            c = t.get_content_by_index(i)
            self.assertEqual(kirbytv_u8.edit(c), c)

    def test_add_and_replace(self):
        t = _title()
        c = t.get_content_by_index(2)
        edited = kirbytv_u8.edit(c, add={'config/KR/KO/x.pcf': b'hello\n'})
        a = ChannelArchive(edited)
        self.assertEqual(a.get('config/KR/KO/x.pcf'), b'hello\n')
        self.assertEqual(set(a.files), set(ChannelArchive(c).files) | {'config/KR/KO/x.pcf'})


class TestDol(unittest.TestCase):
    def test_deterministic_and_bounded(self):
        t = _title()
        c1 = t.get_content_by_index(1)
        packed_a, rec_a = kirbytv_dol.patch_content(c1)
        packed_b, rec_b = kirbytv_dol.patch_content(c1)
        self.assertEqual(packed_a, packed_b)
        self.assertEqual(len(decompress_lz11(packed_a)), len(decompress_lz11(c1)))
        self.assertEqual(rec_a['korean_language'], 9)
        self.assertTrue(rec_a['other_languages_unchanged'])
        self.assertEqual(len(rec_a['hooks']), 4)


class TestSwf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = _title()
        cls.c2 = bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes())
        cls.swf = ChannelArchive(cls.c2).get(kirbytv_swf.SWF_PATH)
        ui = json.loads((ROOT / 'configs/kirbytv-ui-v1-ko.json').read_text(encoding='utf-8'))
        seen = {}
        cls.pairs = []
        for row in ui['entries']:
            if row['source'] in seen:
                continue
            seen[row['source']] = 1
            cls.pairs.append((row['source'], row['ko']))

    def test_roundtrip_all_blocks(self):
        _, _, data = kirbytv_swf.unpack(self.swf)
        self.assertEqual(kirbytv_swf.replace_tags(data, {}), data)
        for code, pos, head, length in kirbytv_swf.tags(data):
            if code in (12, 59):
                raw = data[pos + head:pos + head + length]
                body = raw[2:] if code == 59 else raw
                acts = kirbytv_swf.parse(body)
                self.assertEqual(kirbytv_swf.serialize(acts), body)

    def test_local_and_hardware(self):
        local, _ = kirbytv_swf.patch(self.swf, self.pairs, local=True)
        hard, _ = kirbytv_swf.patch(self.swf, self.pairs, local=False)
        self.assertEqual(local, kirbytv_swf.patch(self.swf, self.pairs, local=True)[0])
        self.assertIn('127.0.0.2', kirbytv_swf.service_hosts(local))
        self.assertNotIn('127.0.0.2', kirbytv_swf.service_hosts(hard))
        self.assertIn('kirby.wiilink24.com', kirbytv_swf.service_hosts(hard))


class TestText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = _title()
        cls.c2 = ChannelArchive(bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes()))
        cls.sys = json.loads((ROOT / 'configs/kirbytv-system-v1-ko.json').read_text(encoding='utf-8'))

    def test_bmg_all_translated(self):
        out, rec = kirbytv_text.korean_bmg(self.c2.get('text/EU/EN/ErrorStrings.bmg'), self.sys['error_strings'])
        rows = kirbytv_text.bmg_messages(out)
        self.assertEqual(len(rows), 61)
        self.assertEqual(rec['distinct'], 4)
        self.assertTrue(all(any('\uac00' <= c <= '\ud7a3' for c in r) for r in rows))
        self.assertEqual(rows[60], '비밀번호를 입력해 주세요.')

    def test_error_xml_adds_ko(self):
        out, rec = kirbytv_text.korean_error_xml(self.c2.get('trusted/xml/gb_error_text.xml'), self.sys['error_xml'])
        root = ET.fromstring(out.decode('utf-8-sig'))
        ids = {u.attrib['id'] for u in root.iter('trans_unit')}
        self.assertIn('server_error_ko', ids)
        self.assertIn('server_error_en', ids)

    def test_configs_parse(self):
        files = kirbytv_text.korean_configs()
        self.assertEqual(len(files), 5)
        for name, data in files.items():
            self.assertTrue(data.endswith(b'\r\n'))
            self.assertIn(b'korean_uhc', files['config/KR/KO/config.koKR.pcf'])

    def test_network_csv_ten_columns(self):
        import re
        out, rec = kirbytv_text.network_csv_korean(
            ChannelArchive(_title().get_content_by_index(5)).get('HomeButton3/network.csv'), *self.sys['home_network_message'])
        cells = re.findall(r'"([^"]*)"', out[2:].decode('utf-16-be'))
        self.assertEqual(len(cells), 10)
        self.assertEqual(cells[9], self.sys['home_network_message'][1])


class TestFixtures(unittest.TestCase):
    def test_xml_wellformed(self):
        root = ET.fromstring(kirbytv_fixtures.gb_config_xml())
        self.assertEqual(root.attrib['code'], 'HCMP')
        self.assertEqual(len(root.find('episode_data').findall('item')), kirbytv_fixtures.EPISODE_COUNT)
        self.assertEqual(len(root.find('help_data').findall('item')), 4)

    def test_routes_are_local(self):
        for line in kirbytv_fixtures.routes().decode().splitlines():
            self.assertTrue(line.startswith('GET /kctv2/'))


class TestBuildArtifacts(unittest.TestCase):
    def test_local_build_reproducible(self):
        out = ROOT / 'workspace/channels/kirbytv/build-v1'
        if not (out / 'kirbytv-ko-local-test.wad').exists():
            self.skipTest('build-v1 not present')
        manifest = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        title, reference, _ = kirbytv_build.build_title(local=True)
        self.assertEqual(kirbytv_build.changed_contents(title, reference), kirbytv_build.CHANGED)
        self.assertEqual(hashlib.sha256(title.dump_wad()).hexdigest(), manifest['wad_sha256'])
        self.assertFalse(manifest['full_localization_complete'])
        self.assertFalse(manifest['hardware_success_verified'])

    def test_v2_build_reproducible_with_hangul_fonts(self):
        out = ROOT / 'workspace/channels/kirbytv/build-v2'
        if not (out / 'kirbytv-ko-local-test.wad').exists():
            self.skipTest('build-v2 not present')
        manifest = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        title, reference, record = kirbytv_build.build_title(local=True, revision=2)
        self.assertEqual(hashlib.sha256(title.dump_wad()).hexdigest(), manifest['wad_sha256'])
        swf = ChannelArchive(title.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH)
        _, _, data = kirbytv_swf.unpack(swf)
        ui = json.loads((ROOT / 'configs/kirbytv-ui-v2-ko.json').read_text(encoding='utf-8'))
        needed = {ord(c) for r in ui['entries'] for c in r['ko'] if ord(c) >= 32}
        fonts = zones = 0
        for code, pos, head, length in kirbytv_swf.tags(data):
            payload = data[pos + head:pos + head + length]
            if code == 75:
                font = kirbytv_swf_font.parse_font3(payload)
                self.assertFalse(needed - set(font['codes']), 'every translated character has a glyph')
                self.assertEqual(font['codes'], sorted(font['codes']))
                fonts += 1
            elif code == 73:
                self.assertEqual((length - 3) % 10, 0)
                zones += 1
        self.assertEqual((fonts, zones), (2, 2))
        dates = kirbytv_swf.init_actions(data)['__Packages.gb.time.DateManager'][2]
        self.assertIn('일'.encode('utf-8'), dates)
        self.assertIn(b'kwceDay', dates)


class TestSwfFont(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = _title()
        c2 = bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes())
        _, _, cls.fws = kirbytv_swf.unpack(ChannelArchive(c2).get(kirbytv_swf.SWF_PATH))
        cls.source = kirbytv_swf_font.HangulSource(ROOT / 'workspace/channels/forecast/references/NotoSansKR.ttf', 800, label='noto')

    def test_font3_identity(self):
        for code, pos, head, length in kirbytv_swf.tags(self.fws):
            if code == 75:
                payload = self.fws[pos + head:pos + head + length]
                self.assertEqual(kirbytv_swf_font.build_font3(kirbytv_swf_font.parse_font3(payload)), payload)

    def test_shape_roundtrip(self):
        contours = [[(0, 0), (100, 0), ((150, 50), (100, 100)), (0, 100), (0, 0)]]
        shape = kirbytv_swf_font.write_shape(contours)
        decoded = kirbytv_swf_font.read_shape(shape, 0)
        self.assertEqual(decoded['fills'], [('f0', 1)])
        self.assertEqual(decoded['contours'], contours)

    def test_union_removes_overlaps(self):
        contours, _ = self.source.contours('가')
        self.assertGreater(kirbytv_swf_font.overlap_area(contours), 4)
        merged = kirbytv_swf_font.union_outline(contours, 0.8)
        self.assertLessEqual(kirbytv_swf_font.overlap_area(merged), 4)
        self.assertLess(kirbytv_swf_font.coverage_mismatch(contours, merged), 0.01)

    def test_extend_fonts_adds_glyphs_and_zones(self):
        new, record = kirbytv_swf_font.extend_fonts(self.fws, '가나다', self.source)
        added = {}
        for code, pos, head, length in kirbytv_swf.tags(new):
            payload = new[pos + head:pos + head + length]
            if code == 75:
                font = kirbytv_swf_font.parse_font3(payload)
                added[font['id']] = len(font['codes'])
                self.assertTrue({0xac00, 0xb098, 0xb2e4} <= set(font['codes']))
            elif code == 73:
                fid = int.from_bytes(payload[:2], 'little')
                self.assertEqual((length - 3) // 10, added[fid])
        self.assertEqual(record['fonts']['Alor 0513']['added'], 3)


class TestDatePatch(unittest.TestCase):
    def test_only_revision2_changes_dates(self):
        t = _title()
        swf = ChannelArchive(bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes())).get(kirbytv_swf.SWF_PATH)
        pairs = [('OK', '확인')]
        v1, _ = kirbytv_swf.patch(swf, pairs, local=True)
        v2, record = kirbytv_swf.patch(swf, pairs, local=True, dates=True)
        for data, expected in ((v1, False), (v2, True)):
            _, _, fws = kirbytv_swf.unpack(data)
            code = kirbytv_swf.init_actions(fws)['__Packages.gb.time.DateManager'][2]
            self.assertEqual(b'kwceDay' in code, expected)
        self.assertEqual(record['DateManager']['korean_date_order'], 'month day일')


class TestMissingIds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = _title()
        cls.swf = ChannelArchive(bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes())).get(kirbytv_swf.SWF_PATH)

    def test_fallback_only_with_missing_units(self):
        units = kirbytv_build.missing_units(3)
        ids = {k for k, _ in units}
        self.assertIn('txt_optin_4', ids)
        self.assertNotIn('txt_delay', ids)   # a present txt_delay would start the interrupt screen
        plain, _ = kirbytv_swf.patch(self.swf, [('OK', '확인')], local=True)
        fixed, record = kirbytv_swf.patch(self.swf, [('OK', '확인')], local=True, missing=units)
        self.assertEqual(record['LocaleManager']['missing_ids'], len(units))
        for data, expected in ((plain, False), (fixed, True)):
            _, _, fws = kirbytv_swf.unpack(data)
            code = kirbytv_swf.init_actions(fws)['__Packages.gb.locale.LocaleManager'][2]
            self.assertEqual(b'kwceKoMissing' in code, expected)
            self.assertEqual('삭제하시겠습니까'.encode('utf-8') in code, expected)

    def test_service_ids_not_shadowed(self):
        import xml.etree.ElementTree as ET
        wiilink_like = ET.fromstring(kirbytv_fixtures.gb_config_xml())
        present = {u.attrib['id'] for u in wiilink_like.iter('trans_unit') if 'id' in u.attrib}
        self.assertFalse(present & {k for k, _ in kirbytv_build.missing_units(3)})


class TestFeedV2(unittest.TestCase):
    def test_sdk_audio_track(self):
        feed = ROOT / 'workspace/channels/kirbytv/local-feed-v2'
        if not (feed / 'sample.mo').exists():
            self.skipTest('local-feed-v2 not present')
        sys.path.insert(0, str(ROOT / 'scripts'))
        from build_kirbytv_feed import header_tags, SDK_AUDIO_TAGS
        tags = [t for t, _ in header_tags((feed / 'sample.mo').read_bytes())]
        self.assertIn(b'A9', tags)
        self.assertNotIn(b'AP', tags)
        self.assertTrue(set(tags) & set(SDK_AUDIO_TAGS))
        self.assertEqual(tags[-1], b'HE')
        manifest = json.loads((feed / 'fixture-manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(manifest['synthetic'] and manifest['local_only'] and not manifest['real_episodes'])


class TestBuildV3(unittest.TestCase):
    def test_v3_reproducible_and_covered(self):
        out = ROOT / 'workspace/channels/kirbytv/build-v3'
        if not (out / 'kirbytv-ko-local-test.wad').exists():
            self.skipTest('build-v3 not present')
        manifest = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        title, reference, record = kirbytv_build.build_title(local=True, revision=3)
        self.assertEqual(hashlib.sha256(title.dump_wad()).hexdigest(), manifest['wad_sha256'])
        ui = json.loads((ROOT / 'configs/kirbytv-ui-v3-ko.json').read_text(encoding='utf-8'))
        rows = {r['id']: r['ko'] for r in ui['entries']}
        self.assertIn('Wii 알림판', rows['txt_optin_1'])
        self.assertEqual(rows['txt_date_current'], '방영 중')
        swf = ChannelArchive(title.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH)
        _, _, data = kirbytv_swf.unpack(swf)
        needed = {ord(c) for r in ui['entries'] for c in r['ko'] if '\uac00' <= c <= '\ud7a3'}
        for _, unit in kirbytv_build.missing_units(3):
            needed |= {ord(c) for k in ('message', 'title', 'label') if k in unit for c in unit[k] if '\uac00' <= c <= '\ud7a3'}
        for code, pos, head, length in kirbytv_swf.tags(data):
            if code == 75:
                font = kirbytv_swf_font.parse_font3(data[pos + head:pos + head + length])
                self.assertFalse(needed - set(font['codes']))


class _Sim:
    """Run patched SWF classes in kwce.avm1_sim with Wii/service mocks (no Dolphin)."""

    CLASSES = ['nintendo.sugar.utils.StringTools', 'gb.time.GBCountryTimeZone', 'gb.locale.LocaleManager',
               'gb.time.DateManager', 'gb.data.EpisodeState', 'gb.data.EpisodeData', 'gb.data.EpisodeStateMachine',
               'gb.buttons.TLGridButton', 'gb.buttons.ESGridButton', 'gb.buttons.GBTitleCardButton']
    COUNTRIES = dict(AUSTRALIA=65.0, NEW_ZEALAND=94.0, GERMANY=78.0, UNITED_KINGDOM=110.0, KOREA=136.0)

    def __init__(self, classes, language=9, country=136.0, supported=False):
        from kwce import avm1_sim as V
        self.V = V
        vm = self.vm = V.VM(now_ms=V.date_ms(2026, 10, 28, 3))
        system = vm.obj(LANG_JAPANESE=0.0, LANG_ENGLISH=1.0, LANG_GERMAN=2.0, LANG_KOREAN=9.0)
        system.props['getLanguage'] = vm.native(lambda *_: float(language), 'getLanguage')
        system.props['getUID'] = vm.native(lambda *_: 'UID', 'getUID')
        wii = vm.path('nintendo.vodf.wii.system', create=True)
        vm.set(wii, 'WiiSystem', system)
        vm.set(wii, 'WiiCountryCode', vm.obj(**self.COUNTRIES))
        vm.globals.props['ApplicationController'] = vm.obj(REMOTE_PATH='http://127.0.0.2/kctv2/')
        for name in self.CLASSES:
            vm.run_class(classes['__Packages.' + name][2])
        self.LM, self.DM = vm.path('gb.locale.LocaleManager'), vm.path('gb.time.DateManager')
        self.lm = V.Obj(vm.get(self.LM, 'prototype'), {'_transUnits': vm.obj()})
        self.lm.props['isCountryCodeSupported'] = vm.native(lambda *_: supported, 'isCountryCodeSupported')
        self.lm.props['__get__wiiCountryCode'] = vm.native(lambda *_: country, 'wiiCountryCode')
        self.LM.props['_instance'] = self.lm
        self.dm = V.Obj(vm.get(self.DM, 'prototype'))
        self.DM.props['_instance'] = self.dm
        self.dm.props['setCurrentDate'] = vm.native(lambda _vm, this, args: this.props.__setitem__(
            '_currentDate', V.DateObj(vm.get(this, '_serverDate').ms, vm.date_proto)), 'setCurrentDate')
        dc = vm.obj(dateManager=self.dm)
        vm.path('gb.data.DataController', create=True).props['getInstance'] = vm.native(lambda *_: dc, 'getInstance')

    def call(self, owner, name, *args, this=None):
        return self.vm.call(self.vm.get(owner, name), self.V.UNDEF if this is None else this, list(args))

    def text(self, unit):
        get = self.vm.get
        return get(get(get(unit, 'message'), 'target'), 'data')

    def xml(self, element):
        vm, V = self.vm, self.V
        obj = vm.obj()
        if element.attrib:
            obj.props['attributes'] = vm.obj(**{k.split('}')[-1]: v for k, v in element.attrib.items()})
        if (element.text or '').strip():
            obj.props['data'] = element.text
        groups = {}
        for child in element:
            groups.setdefault(child.tag, []).append(self.xml(child))
        for tag, items in groups.items():
            obj.props[tag] = items[0] if len(items) == 1 else V.Arr(items, vm.array_proto)
        return obj

    def load_feed(self, xml_bytes):
        """XML -> kwceKo overlay -> LocaleManager.initFromXML, then the pinned server/expiry dates."""
        vm, get = self.vm, self.vm.get
        doc = vm.obj(data=self.xml(ET.fromstring(xml_bytes)))
        self.call(self.LM, 'kwceKo', doc)
        self.call(self.lm, 'initFromXML', doc, this=self.lm)
        settings = get(get(doc, 'data'), 'settings')
        self.call(self.dm, '__set__serverDate', get(get(get(settings, 'override'), 'server_date'), 'data'), this=self.dm)
        self.dm.props['_expiryDate'] = self.call(self.DM, 'getDateFromString', get(get(settings, 'expiry_date'), 'data'))
        return doc

    def timetable(self, doc):
        vm, get = self.vm, self.vm.get
        machine = vm.construct(vm.path('gb.data.EpisodeStateMachine'), [])
        rows = []
        for item in get(get(get(doc, 'data'), 'episode_data'), 'item').items:
            ed = vm.construct(vm.path('gb.data.EpisodeData'), [])
            attrs = get(item, 'attributes')
            path = get(get(item, 'video'), 'attributes').props['path']
            ed.props.update(episodeNumber=get(get(item, 'episode_number'), 'data'), episodeTitle='',
                            episodeVideoPath=('http://127.0.0.2/kctv2/' + path) if path else '')
            self.call(ed, 'setStartDateFromString', attrs.props['start_date'], this=ed)
            self.call(ed, 'setEndDateFromString', attrs.props['end_date'], this=ed)
            self.call(machine, 'addEpisode', ed, this=machine)
            texts = []
            for cls in ('TLGridButton', 'ESGridButton', 'GBTitleCardButton'):
                button = self.V.Obj(get(vm.path('gb.buttons.' + cls), 'prototype'),
                                    {'_ed': ed, '_episodeState': get(ed, 'episodeState')})
                texts.append(vm.to_str(self.call(button, 'getDateText', this=button)))
            rows.append((int(get(ed, 'episodeNumber')), get(ed, 'episodeState'), texts))
        return rows


def _wiilink_swf():
    t = _title()
    return ChannelArchive(bspatch.apply(t.get_content_by_index(2), PATCH.read_bytes())).get(kirbytv_swf.SWF_PATH)


def _classes(swf):
    _, _, fws = kirbytv_swf.unpack(swf)
    return kirbytv_swf.init_actions(fws)


class TestAvm1Sim(unittest.TestCase):
    def test_small_program(self):
        from kwce import avm1_sim as V
        S = kirbytv_swf
        skip = S.Label()
        items = [S.push(2), S.push(3), S.op('Less2'), S.op('Not'), S.branch('if', skip),
                 S.push('x', 'ok'), S.op('Add2'), S.op('Return'), skip, S.push('bad'), S.op('Return')]
        acts = []
        S.splice(acts, 0, items)
        raw = S.serialize(acts)
        self.assertEqual(V.VM().run_class(raw), 'xok')

    def test_original_english_behaviour_is_reproduced(self):
        sim = _Sim(_classes(_wiilink_swf()), language=1)
        dates = [(28.0, 9.0), (31.0, 9.0), (3.0, 10.0), (22.0, 11.0)]
        months = {9.0: 'OCT', 10.0: 'NOV', 11.0: 'DEC'}
        sim.lm.props['getLocaleInfoByID'] = sim.vm.native(lambda _vm, this, args: sim.vm.obj(message=sim.vm.obj(
            target=sim.vm.obj(data=months[float(args[0][len('txt_month_'):])]))), 'stub')
        sim.lm.props['__get__wiiLanguageCode'] = sim.vm.native(lambda *_: 1.0, 'lang')
        out = [sim.vm.to_str(sim.call(sim.DM, 'getDateAbbrev', d)) + ' ' + sim.call(sim.DM, 'getShortMonth', m) for d, m in dates]
        self.assertEqual(out, ['28th OCT', '31st OCT', '3rd NOV', '22nd DEC'])


class TestWave3Swf(unittest.TestCase):
    """Revision-4 SWF edits, executed in the AVM1 evaluator."""

    @classmethod
    def setUpClass(cls):
        cls.swf = _wiilink_swf()
        _, _, cls.pairs = kirbytv_build.tables(4)
        cls.units = kirbytv_build.missing_units(4)
        cls.v4, cls.record = kirbytv_swf.patch(cls.swf, cls.pairs, local=True, dates=True, missing=cls.units,
                                               days=True, time_zone=True)
        cls.classes = _classes(cls.v4)

    def test_new_options_off_keep_revision3_bytes(self):
        _, _, pairs3 = kirbytv_build.tables(3)
        units3 = kirbytv_build.missing_units(3)
        a, _ = kirbytv_swf.patch(self.swf, pairs3, local=True, dates=True, missing=units3)
        b, _ = kirbytv_swf.patch(self.swf, pairs3, local=True, dates=True, missing=units3, days=False, time_zone=False)
        self.assertEqual(a, b)
        self.assertEqual(self.record['DateManager']['time_zone']['korean_utc_offset_hours'], 9)

    def test_final_week_intro_unit(self):
        units = dict(self.units)
        self.assertIn('[number_days]', units['txt_intro_4']['message'])
        for language, expected in ((9, units['txt_intro_4']['message']), (1, None)):
            sim = _Sim(self.classes, language=language)
            unit = sim.call(sim.lm, 'getLocaleInfoByID', 'txt_intro_4', this=sim.lm)
            self.assertEqual(sim.text(unit) if expected else unit, expected if expected else sim.V.UNDEF)
        sim = _Sim(self.classes)
        sim.lm.props['_transUnits'].props['txt_intro_4'] = sim.vm.obj(message=sim.vm.obj(target=sim.vm.obj(data='SERVICE')))
        self.assertEqual(sim.text(sim.call(sim.lm, 'getLocaleInfoByID', 'txt_intro_4', this=sim.lm)), 'SERVICE')

    def test_days_text(self):
        sim = _Sim(self.classes)
        self.assertEqual([sim.call(sim.lm, 'getDaysAsText', n, this=sim.lm) for n in (9.0, 1.0, 0.0)], ['9일', '1일', '1일 미만'])
        english = _Sim(self.classes, language=1)
        units = english.vm.obj(day=english.vm.obj(single=english.vm.obj(data='[number] day'), plural=english.vm.obj(data='[number] days')),
                               mod=english.vm.obj(less_than=english.vm.obj(data='less than [number] [time_unit]')))
        xml = english.vm.obj(dataXMLObj=english.vm.obj(data=english.vm.obj(locale=english.vm.obj(time_units=units))))
        english.vm.path('gb.data.DataController').props['getInstance'] = english.vm.native(lambda *_: xml, 'getInstance')
        self.assertEqual(english.call(english.lm, 'getDaysAsText', 9.0, this=english.lm), '9 days')

    def test_time_zone(self):
        def offset(**kw):
            sim = _Sim(self.classes, **kw)
            sim.dm.props['_currentDate'] = sim.V.DateObj(sim.V.date_ms(2026, 10, 28, 3), sim.vm.date_proto)
            return sim.call(sim.dm, '__get__countryTimeZoneOffset', this=sim.dm)
        self.assertEqual(offset(language=9), 9.0)
        self.assertEqual(offset(language=1), 0.0)
        # A supported country keeps the channel's own table (Germany +1, DST rule untouched).
        self.assertEqual(offset(language=9, country=78.0, supported=True), offset(language=1, country=78.0, supported=True))
        self.assertIn(offset(language=9, country=78.0, supported=True), (1.0, 2.0))

    def test_schedule_feed_timetable_lines(self):
        expected = {
            3: [(1, 'state_unlocked', '상시 방영'), (2, 'state_locked_expired', '방영 종료'),
                (3, 'state_limited_24', '24시간도 남지 않았습니다!'), (4, 'state_limited_time', '곧 종료! 10월 30일'),
                (5, 'state_unlocked', '방영 기한: 11월 6일'), (6, 'state_new', '새로 공개! 방영 기한: 11월 9일'),
                (7, 'state_locked_future', '공개일: 10월 31일'), (8, 'state_locked_future', '공개일: 11월 3일'),
                (9, 'state_unavailable', '')],
            4: [(1, 'state_unlocked', '상시 방영'), (2, 'state_locked_expired', '방영 종료'),
                (3, 'state_limited_24', '24시간도 남지 않았습니다!'), (4, 'state_limited_time', '곧 종료! 11월 26일'),
                (5, 'state_unlocked', '방영 기한: 12월 3일'), (6, 'state_new', '새로 공개! 방영 기한: 12월 6일'),
                (7, 'state_locked_future', '공개일: 11월 27일'), (8, 'state_locked_future', '공개일: 11월 30일'),
                (9, 'state_unavailable', '')],
        }
        for revision, rows in expected.items():
            sim = _Sim(self.classes)
            got = sim.timetable(sim.load_feed(kirbytv_fixtures.gb_config_xml(revision)))
            self.assertEqual([(n, s, t[0]) for n, s, t in got], [(n, s, '\n' + text) for n, s, text in rows], revision)
            unavailable = [t for n, s, t in got if s == 'state_unavailable'][0]
            self.assertEqual(unavailable[1:], ['볼 수 없는 에피소드', '볼 수 없는 에피소드'])
            plan = kirbytv_fixtures.scenario(revision)
            self.assertEqual([e['expected_state'] for e in plan['episodes']],
                             [s[len('state_'):].upper() for n, s, t in got])

    def test_final_weeks_only_in_scenario4(self):
        """DataController: isFinalWeek = new Date(expiry - now) in January with getUTCDate() <= 14."""
        for revision, final, days in ((3, False, None), (4, True, '9일')):
            sim = _Sim(self.classes)
            sim.load_feed(kirbytv_fixtures.gb_config_xml(revision))
            left = sim.vm.get(sim.dm, '_expiryDate').ms - sim.vm.get(sim.dm, '_currentDate').ms
            span = sim.V._dt(left)
            self.assertEqual(span.month == 1 and span.day <= 14, final, revision)
            if final:
                text = sim.call(sim.lm, 'getDaysAsText', float(span.day), this=sim.lm)
                self.assertEqual(text, days)
                intro = sim.call(sim.vm.path('nintendo.sugar.utils.StringTools'), 'searchAndReplace',
                                 dict(self.units)['txt_intro_4']['message'], '[number_days]', text)
                self.assertIn('9일 남았습니다.', intro)


class TestScheduleFeeds(unittest.TestCase):
    def test_feed_revisions_1_2_unchanged(self):
        for n in (1, 2):
            feed = ROOT / f'workspace/channels/kirbytv/local-feed-v{n}/gb_config_en.xml'
            if feed.exists():
                self.assertEqual(feed.read_bytes(), kirbytv_fixtures.gb_config_xml())

    def test_scenario_xml(self):
        for revision in kirbytv_fixtures.SCENARIOS:
            root = ET.fromstring(kirbytv_fixtures.gb_config_xml(revision))
            items = root.find('episode_data').findall('item')
            self.assertEqual(len(items), len(kirbytv_fixtures.SCENARIO_EPISODES))
            self.assertEqual(root.find('settings/expiry_date').text, '2026 12 03 00 00 00')
            self.assertRegex(root.find('settings/override/server_date').text, r'^\w{3}, \d\d \w{3} 2026 03:00:00 GMT$')
            paths = [i.find('video').attrib['path'] for i in items]
            self.assertEqual(set(paths), {kirbytv_fixtures.VIDEO, ''})
            present = {u.attrib['id'] for u in root.iter('trans_unit') if 'id' in u.attrib}
            self.assertFalse(present & {k for k, _ in kirbytv_build.missing_units(4)})

    def test_episode_text_has_glyphs(self):
        glyphs = set(json.loads((ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json').read_text(encoding='utf-8'))['characters'])
        text = ''.join(e['title'] + e['synopsis'] for r in kirbytv_fixtures.SCENARIOS for e in kirbytv_fixtures.scenario(r)['episodes'])
        text += kirbytv_swf.DAY_SUFFIX + kirbytv_swf.LESS_THAN_A_DAY
        self.assertFalse({c for c in text if '\uac00' <= c <= '\ud7a3'} - glyphs)

    def test_built_feeds(self):
        for revision in (3, 4):
            feed = ROOT / f'workspace/channels/kirbytv/local-feed-v{revision}'
            if not (feed / 'fixture-manifest.json').exists():
                continue
            manifest = json.loads((feed / 'fixture-manifest.json').read_text(encoding='utf-8'))
            self.assertTrue(manifest['synthetic'] and manifest['local_only'] and not manifest['real_episodes'])
            self.assertEqual((feed / 'gb_config_en.xml').read_bytes(), kirbytv_fixtures.gb_config_xml(revision))
            self.assertEqual((feed / 'sample.mo').read_bytes(),
                             (ROOT / 'workspace/channels/kirbytv/local-feed-v2/sample.mo').read_bytes())
            for row in manifest['files']:
                self.assertEqual(hashlib.sha256((feed / row['path']).read_bytes()).hexdigest(), row['sha256'])


class TestResetSave(unittest.TestCase):
    def test_move_and_restore(self):
        import tempfile
        sys.path.insert(0, str(ROOT / 'scripts'))
        import reset_kirbytv_save as R
        with tempfile.TemporaryDirectory() as tmp:
            data, private = Path(tmp) / 'data', Path(tmp) / 'private'
            data.mkdir()
            private.mkdir()
            (data / 'shrdobjs.vff').write_bytes(b'\x01' * 64)
            (data / 'banner.bin').write_bytes(b'\x02' * 32)
            backup, rows = R.move_save(data, private)
            self.assertEqual(backup.name, 'kirbytv-save-backup-1')
            self.assertEqual(sorted(r['path'] for r in rows), ['banner.bin', 'shrdobjs.vff'])
            self.assertEqual(list(data.iterdir()), [])
            self.assertEqual(R.move_save(data, private), (None, []))
            (data / 'shrdobjs.vff').write_bytes(b'new')
            with self.assertRaises(SystemExit):
                R.restore_save(data, private, 1)
            (data / 'shrdobjs.vff').unlink()
            R.restore_save(data, private, 1)
            self.assertEqual((data / 'shrdobjs.vff').read_bytes(), b'\x01' * 64)
            (data / 'other.bin').write_bytes(b'')
            with self.assertRaises(ValueError):
                R.move_save(data, private)


class TestBuildV4(unittest.TestCase):
    def test_v4_reproducible_and_covered(self):
        out = ROOT / 'workspace/channels/kirbytv/build-v4'
        if not (out / 'kirbytv-ko-local-test.wad').exists():
            self.skipTest('build-v4 not present')
        manifest = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        title, reference, record = kirbytv_build.build_title(local=True, revision=4)
        self.assertEqual(hashlib.sha256(title.dump_wad()).hexdigest(), manifest['wad_sha256'])
        self.assertEqual(kirbytv_build.changed_contents(title, reference), kirbytv_build.CHANGED)
        swf = ChannelArchive(title.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH)
        _, _, data = kirbytv_swf.unpack(swf)
        classes = kirbytv_swf.init_actions(data)
        self.assertIn('[number_days] 남았습니다'.encode('utf-8'), classes['__Packages.gb.locale.LocaleManager'][2])
        self.assertIn(kirbytv_swf.LESS_THAN_A_DAY.encode('utf-8'), classes['__Packages.gb.locale.LocaleManager'][2])
        glyphs = set(json.loads((ROOT / 'configs/kirbytv-swf-glyphs-v4-ko.json').read_text(encoding='utf-8'))['characters'])
        for code, pos, head, length in kirbytv_swf.tags(data):
            if code == 75:
                font = kirbytv_swf_font.parse_font3(data[pos + head:pos + head + length])
                self.assertFalse({ord(c) for c in glyphs} - set(font['codes']))
        sim = _Sim(classes)
        rows = sim.timetable(sim.load_feed(kirbytv_fixtures.gb_config_xml(3)))
        self.assertEqual(rows[0][2][0], '\n상시 방영')
        self.assertFalse(manifest['full_localization_complete'] or manifest['hardware_success_verified'])


class TestTooltipWidth(unittest.TestCase):
    """Revision 8: GumballButtonToolTip bubble width, executed in the AVM1 evaluator."""

    @classmethod
    def setUpClass(cls):
        _, _, fws = kirbytv_swf.unpack(_wiilink_swf())
        index, sid, code = kirbytv_swf.init_actions(fws)['__Packages.gb.buttons.GumballButtonToolTip']
        acts = kirbytv_swf.parse(code)
        cls.record = kirbytv_swf.korean_tooltip_width(acts, kirbytv_swf.pool(acts))
        cls.code = kirbytv_swf.serialize(acts)

    def _vm(self, language):
        from kwce import avm1_sim as V
        vm = V.VM()
        system = vm.obj(LANG_JAPANESE=0.0, LANG_ENGLISH=1.0, LANG_KOREAN=9.0)
        system.props['getLanguage'] = vm.native(lambda *_: float(language), 'getLanguage')
        vm.set(vm.path('nintendo.vodf.wii.system', create=True), 'WiiSystem', system)
        vm.set(vm.path('nintendo.sugar.core', create=True), 'WiiSugarApplication',
               vm.obj(__get__isWidescreen=vm.native(lambda *_: True, 'isWidescreen')))
        vm.run_class(self.code)
        return V, vm, vm.path('gb.buttons.GumballButtonToolTip')

    def test_helper_widths(self):
        V, vm, cls = self._vm(9)
        width = lambda s: vm.call(vm.get(cls, 'kwceTipWidth'), V.UNDEF, [s])
        # settings tooltips (configs/kirbytv-ui-v4-ko.json L442/L454/L484/L508): Hangul 20px, others 14px, + 10
        self.assertEqual([width(s) for s in ('채널 소개', '에피소드 편성표 안내', '열쇠 알아보기', '새 에피소드 소식 설정')],
                         [104.0, 218.0, 144.0, 232.0])
        self.assertEqual(width('About The Channel'), 17 * 14 + 10.0)   # no Hangul: original formula
        # needed width at 23px (Hangul 19.04px, space 7.84px, 2px text-field gutters) stays below the bubble
        for text in ('채널 소개', '에피소드 편성표 안내', '열쇠 알아보기', '새 에피소드 소식 설정'):
            hangul = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
            self.assertLess(hangul * 16957 / 20480 * 23 + (len(text) - hangul) * 6980 / 20480 * 23 + 4, width(text))

    def test_setter_only_changes_korean_consoles(self):
        for language, expected in ((9, [164.0, 218.0]), (1, [164.0])):
            V, vm, cls = self._vm(language)
            proto = vm.get(cls, 'prototype')
            calls = []
            tip = V.Obj(proto, {'_dynamicProps': True, '_labelText': '', '_x': 300.0, 'base_Center': vm.obj(_width=50.0)})
            tip.props['__set__centerWidth'] = vm.native(lambda _vm, this, args: calls.append(args[0]), 'centerWidth')
            tip.props['__set__xOffset'] = vm.native(lambda *_: None, 'xOffset')
            vm.call(vm.get(proto, '__set__labelText'), tip, ['에피소드 편성표 안내'])
            self.assertEqual(calls, expected, language)
        self.assertEqual(self.record['hangul_width_px'], kirbytv_swf.TOOLTIP_HANGUL_WIDTH)


SETTINGS_TIPS = ('채널 소개', '에피소드 편성표 안내', '열쇠 알아보기', '새 에피소드 소식 설정')


def _tooltip_vm(first_width_only, language=9):
    """AVM1 evaluator running the real UIButtonToolTip/GumballButtonToolTip code on mock clips.

    Adds what the plain evaluator lacks for these classes: `super` (DefineFunction2 PreloadSuper)
    and display properties. Display rule as in Flash: undefined/null/NaN assignments to _x/_y/
    _width/... are ignored. first_width_only models the revision 9 hypothesis for the RC6 photos
    (only the first _width assignment of a clip in the frame takes effect). Dolphin disproved it;
    the real cause is in TestTooltipV11.
    """
    from kwce import avm1_sim as V

    class SuperRef(V.Obj):
        def __init__(self, start, this):
            super().__init__()
            self.start, self.this = start, this

    class Clip(V.Obj):
        DISPLAY = ('_x', '_y', '_width', '_height', '_xscale', '_yscale')

        def __init__(self, proto, **props):
            super().__init__(proto, props)
            self.width_set = False

    class VM(V.VM):
        def set(self, obj, name, value):
            if isinstance(value, V.Func) and isinstance(obj, V.Obj) and not hasattr(value, 'home'):
                value.home = obj
            if isinstance(obj, Clip) and name in Clip.DISPLAY:
                if value is V.UNDEF or value is V.NULL or not math.isfinite(V.to_number(value)):
                    return
                if name == '_width':
                    if first_width_only and obj.width_set:
                        return
                    obj.width_set = True
                obj.props[name] = V.to_number(value)
                return
            super().set(obj, name, value)

        def get(self, obj, name):
            if isinstance(obj, SuperRef):
                o = obj.start
                while o is not None:
                    if name in o.accessors:
                        getter = o.accessors[name][0]
                        return self.call(getter, obj.this, []) if isinstance(getter, (V.Func, V.Native)) else V.UNDEF
                    if name in o.props:
                        return o.props[name]
                    o = o.proto
                return V.UNDEF
            return super().get(obj, name)

        def call(self, func, this, args):
            return super().call(func, this.this if isinstance(this, SuperRef) else this, args)

        def _invoke(self, func, this, args):
            if not (func.v2 and func.flags & 0x10):
                return super()._invoke(func, this, args)
            regs, n, flags = [V.UNDEF] * max(func.registers, 4), 1, func.flags
            for bit, value in ((0x01, this), (0x04, V.Arr(args, self.array_proto)),
                               (0x10, SuperRef(func.home.proto, this)), (0x40, V.UNDEF), (0x80, V.UNDEF), (0x100, self.globals)):
                if flags & bit:
                    regs[n] = value
                    n += 1
            local = {}
            for i, (register, name) in enumerate(func.params):
                value = args[i] if i < len(args) else V.UNDEF
                if register:
                    regs[register] = value
                else:
                    local[name] = value
            return self.run(func.code, func.start, func.end, regs, local, this)

    vm = VM()
    system = vm.obj(LANG_JAPANESE=0.0, LANG_ENGLISH=1.0, LANG_KOREAN=9.0)
    system.props['getLanguage'] = vm.native(lambda *_: float(language), 'getLanguage')
    vm.set(vm.path('nintendo.vodf.wii.system', create=True), 'WiiSystem', system)
    vm.set(vm.path('nintendo.sugar.core', create=True), 'WiiSugarApplication',
           vm.obj(__get__isWidescreen=vm.native(lambda *_: True, 'isWidescreen')))
    return V, vm, Clip


def _show_tooltip(base_code, tip_code, text, first_width_only, x_offset=0.0, center_width=None, state=None):
    """UIButton rollover on a fresh ToolTip (sprite 683 children) -> final geometry of the bubble.

    Setter order as UIButton's rollover: labelText, xOffset, yOffset (XML y_offset), centerWidth
    (_toolTipCenterWidth; None = undefined, a button that gives no width), pointDown. The
    settings cards (HSGridButton) give xOffset NaN and centerWidth text.length * 15 (TestTooltipV11).
    state: optional dict that receives the tooltip's own properties afterwards.
    """
    V, vm, Clip = _tooltip_vm(first_width_only)
    vm.run_class(base_code)
    vm.run_class(tip_code)
    proto = vm.get(vm.path('gb.buttons.GumballButtonToolTip'), 'prototype')
    p = vm.object_proto
    children = dict(base_Center=Clip(p, _x=0.0, _y=12.0, _width=26 * 4.1667, _height=42.0),
                    label=Clip(p, _x=-50.0, _y=14.0, _width=100.0, _height=38.6),
                    baseEnd_Left=Clip(p, _x=-61.0, _y=12.0, _width=11.0, _height=42.0),
                    baseEnd_Right=Clip(p, _x=50.0, _y=12.0, _width=11.0, _height=42.0),
                    pointer=Clip(p, _x=0.0, _y=0.0, _width=25.9, _height=19.25))
    tip = V.Obj(proto, dict(children, _x=427.0, _y=200.0, y=200.0, _centerWidth=26 * 4.1667))
    for name, value in (('__set__labelText', text), ('__set__xOffset', x_offset), ('__set__yOffset', 20.0),
                        ('__set__centerWidth', V.UNDEF if center_width is None else center_width),
                        ('__set__pointDown', True)):
        vm.call(vm.get(tip, name), tip, [value])
    if state is not None:
        state.update(tip.props)
    c = {k: v.props for k, v in children.items()}
    return dict(body=c['base_Center']['_width'], label_x=c['label']['_x'], label_width=c['label']['_width'],
                left_cap=c['baseEnd_Left']['_x'], right_cap=c['baseEnd_Right']['_x'])


class TestTooltipV9(unittest.TestCase):
    """Revision 9: one Hangul-aware width call. The first-width model below was the revision 9
    hypothesis for the RC6 photos; Dolphin disproved it (real cause: TestTooltipV11)."""

    @classmethod
    def setUpClass(cls):
        _, _, fws = kirbytv_swf.unpack(_wiilink_swf())
        classes = kirbytv_swf.init_actions(fws)
        cls.base = classes['__Packages.nintendo.sugar.core.UIButtonToolTip'][2]
        original = classes['__Packages.gb.buttons.GumballButtonToolTip'][2]
        cls.codes = {'original': original}
        for name, editor in (('v8', kirbytv_swf.korean_tooltip_width), ('v9', kirbytv_swf.korean_tooltip_width_once)):
            acts = kirbytv_swf.parse(original)
            record = editor(acts, kirbytv_swf.pool(acts))
            cls.codes[name] = kirbytv_swf.serialize(acts)
            if name == 'v9':
                cls.record = record

    def test_one_width_call_on_every_console(self):
        for language in (9, 1):
            V, vm, _ = _tooltip_vm(False, language)
            vm.run_class(self.codes['v9'])
            proto = vm.get(vm.path('gb.buttons.GumballButtonToolTip'), 'prototype')
            for text, expected in (('에피소드 편성표 안내', 218.0), ('Episode Timetable Information', 29 * 14 + 10.0)):
                calls = []
                tip = V.Obj(proto, {'_dynamicProps': True, '_labelText': '', '_x': 300.0, 'base_Center': vm.obj(_width=50.0)})
                tip.props['__set__centerWidth'] = vm.native(lambda _vm, this, args: calls.append(args[0]), 'centerWidth')
                tip.props['__set__xOffset'] = vm.native(lambda *_: None, 'xOffset')
                vm.call(vm.get(proto, '__set__labelText'), tip, [text])
                self.assertEqual(calls, [expected], (language, text))
        self.assertIn('every console', self.record['scope'])

    def test_console_photos_and_fix(self):
        widths = dict(zip(SETTINGS_TIPS, (104.0, 218.0, 144.0, 232.0)))
        for text in SETTINGS_TIPS:
            old = sum(1 for _ in text) * 14 + 10.0
            new = widths[text]
            for console in (False, True):
                v7 = _show_tooltip(self.base, self.codes['original'], text, console)
                self.assertEqual(v7, dict(body=old, label_x=-old / 2, label_width=old, left_cap=-old / 2 - 11, right_cap=old / 2))
                v9 = _show_tooltip(self.base, self.codes['v9'], text, console)
                self.assertEqual(v9, dict(body=new, label_x=-new / 2, label_width=new, left_cap=-new / 2 - 11, right_cap=new / 2))
            # revision 8: fine under the plain Flash rule; under the (disproved) first-width model the
            # caps and the label start move to the new width while the body and the label keep the old one
            self.assertEqual(_show_tooltip(self.base, self.codes['v8'], text, False)['body'], new)
            self.assertEqual(_show_tooltip(self.base, self.codes['v8'], text, True),
                             dict(body=old, label_x=-new / 2, label_width=old, left_cap=-new / 2 - 11, right_cap=new / 2))


class TestTooltipV11(unittest.TestCase):
    """Revisions 10-11: the cause of the RC6 photos (IMG_5702-5705), found by the revision 10 probe in Dolphin.

    HSGridButton.invalidate (the settings cards) gives toolTipXOffset = Number(undefined) = NaN (the
    help XML has no x_offset) and toolTipCenterWidth = text.length * 15. UIButton's rollover sets
    labelText first (Hangul-aware width; caps and label placed), then xOffset NaN, so every later _x
    is NaN and ignored, then centerWidth = length * 15, which only the _width assignments follow.
    Probe text in Dolphin for '새 에피소드 소식 설정': L c232 c180 xNaN.
    """

    @classmethod
    def setUpClass(cls):
        _, _, fws = kirbytv_swf.unpack(_wiilink_swf())
        classes = kirbytv_swf.init_actions(fws)
        cls.base = classes['__Packages.nintendo.sugar.core.UIButtonToolTip'][2]
        original = classes['__Packages.gb.buttons.GumballButtonToolTip'][2]
        cls.tips = {}
        for name, editor in (('v9', kirbytv_swf.korean_tooltip_width_once), ('v10', kirbytv_swf.korean_tooltip_width_guarded)):
            acts = kirbytv_swf.parse(original)
            editor(acts, kirbytv_swf.pool(acts))
            cls.tips[name] = kirbytv_swf.serialize(acts)
        cls.grid = {'original': classes[kirbytv_swf.HS_GRID_BUTTON][2]}
        acts = kirbytv_swf.parse(cls.grid['original'])
        cls.record = kirbytv_swf.korean_hs_tooltip_width(acts, kirbytv_swf.pool(acts))
        cls.grid['v11'] = kirbytv_swf.serialize(acts)

    def _invalidate(self, grid, text):
        """HSGridButton.invalidate on mock help data -> the tooltip values it sets."""
        V, vm, _ = _tooltip_vm(False)
        vm.run_class(self.base)
        vm.run_class(self.tips['v10'])
        vm.run_class(self.grid[grid])
        proto = vm.get(vm.path('gb.buttons.HSGridButton'), 'prototype')
        got = {}
        this = V.Obj(proto, {})
        for key in ('toolTipLinkageID', 'useToolTip', 'toolTipXOffset', 'toolTipYOffset', 'toolTipCenterWidth',
                    'toolTipPointDown', 'toolTipLabelText', 'label'):
            this.props['__set__' + key] = vm.native(lambda _vm, _this, a, key=key: got.__setitem__(key, a[0]), key)
        this.props['updateDisplay'] = vm.native(lambda *_: None, 'updateDisplay')
        this.props['_data'] = vm.obj(getToolTipXOffset=vm.native(lambda *_: math.nan, 'getToolTipXOffset'),
                                     getToolTipYOffset=vm.native(lambda *_: 20.0, 'getToolTipYOffset'),
                                     getToolTipText=vm.native(lambda *_: text, 'getToolTipText'), btnLabel='알림')
        vm.call(vm.get(proto, 'invalidate'), this, [])
        return got

    def test_settings_card_widths(self):
        widths = dict(zip(SETTINGS_TIPS, (104.0, 218.0, 144.0, 232.0)))
        for text in SETTINGS_TIPS:
            old, new = self._invalidate('original', text), self._invalidate('v11', text)
            self.assertEqual(old['toolTipCenterWidth'], len(text) * 15.0, text)
            self.assertEqual(new['toolTipCenterWidth'], widths[text], text)
            for got in (old, new):
                self.assertTrue(math.isnan(got['toolTipXOffset']), text)
                self.assertEqual(got['toolTipLabelText'], text)
        self.assertEqual(self._invalidate('original', '새 에피소드 소식 설정')['toolTipCenterWidth'], 180.0)  # probe c180
        # text without Hangul: 14 px per character + 10 instead of 15 px per character
        self.assertEqual(self._invalidate('v11', 'Settings')['toolTipCenterWidth'], 8 * 14 + 10.0)
        self.assertEqual(self.record['actions'], 5)
        acts = kirbytv_swf.parse(self.grid['v11'])
        with self.assertRaises(ValueError):
            kirbytv_swf.korean_hs_tooltip_width(acts, kirbytv_swf.pool(acts))

    def test_probe_reproduced_and_fixed(self):
        widths = dict(zip(SETTINGS_TIPS, (104.0, 218.0, 144.0, 232.0)))
        for text in SETTINGS_TIPS:
            new, grid = widths[text], len(text) * 15.0
            for name in ('v9', 'v10'):
                # revisions 9-10: caps and label start from labelText, body and label width from length * 15
                got = _show_tooltip(self.base, self.tips[name], text, False, x_offset=math.nan, center_width=grid)
                self.assertEqual(got, dict(body=grid, label_x=-new / 2, label_width=grid,
                                           left_cap=-new / 2 - 11, right_cap=new / 2), (name, text))
            # revision 11: the card passes the same kwceTipWidth, so everything agrees
            got = _show_tooltip(self.base, self.tips['v10'], text, False, x_offset=math.nan, center_width=new)
            self.assertEqual(got, dict(body=new, label_x=-new / 2, label_width=new,
                                       left_cap=-new / 2 - 11, right_cap=new / 2), text)

    def test_revision10_ignores_undefined_width(self):
        for name in ('v9', 'v10'):
            state = {}
            _show_tooltip(self.base, self.tips[name], '새 에피소드 소식 설정', False, state=state)
            width = state.get('_centerWidth')
            if name == 'v10':
                self.assertEqual(width, 232.0)
            else:
                self.assertFalse(isinstance(width, float) and math.isfinite(width), width)


class TestLogoV8(unittest.TestCase):
    """Revision 8: Korean '채널' logo pieces (SWF bitmaps, Wii Menu banner/icon textures)."""

    @classmethod
    def setUpClass(cls):
        from kwce import kirbytv_logo
        cls.L = kirbytv_logo
        cls.swf = _wiilink_swf()
        cls.logos = kirbytv_logo.korean_logo_set(cls.swf)

    def test_pieces_keep_sizes_and_are_deterministic(self):
        _, _, fws = kirbytv_swf.unpack(self.swf)
        for cid, payload in self.logos['bitmaps'].items():
            fmt, w, h = __import__('struct').unpack_from('<BHH', payload, 2)
            self.assertEqual((fmt, (w, h)), (5, self.L.bitmap(fws, cid).size), cid)
        again = self.L.korean_logo_set(self.swf)
        self.assertEqual(again['bitmaps'], self.logos['bitmaps'])
        self.assertEqual(again['icon_word'].tobytes(), self.logos['icon_word'].tobytes())
        self.assertEqual(self.logos['icon_word'].size, (49, 18))
        self.assertLess(self.logos['record']['small_still']['residual_outside_mask'], 6.0)

    def test_banner_only_changes_word_blocks(self):
        from kwce import kirbytv_banner, tpl
        from libWiiPy.archive import decompress_lz77
        t = _title()
        banner, record = kirbytv_banner.korean_banner_art(t.get_content_by_index(0), logos=self.logos)
        info = record['meta/banner.bin']
        self.assertEqual(info['changed'], ['arc/blyt/banner.brlyt', 'arc/timg/Logo_English.tpl'])
        self.assertLess(info['banner_logo']['residual_outside_mask'], 9.0)
        stock = ChannelArchive(decompress_lz77(ChannelArchive(t.get_content_by_index(0)[0x640:]).get('meta/banner.bin')[32:]))
        new = ChannelArchive(decompress_lz77(ChannelArchive(banner[0x640:]).get('meta/banner.bin')[32:]))
        a, b = stock.get('arc/timg/Logo_English.tpl'), new.get('arc/timg/Logo_English.tpl')
        self.assertEqual(len(a), len(b))
        before, after = tpl.decode(a, 0), tpl.decode(b, 0)
        changed = [(x, y) for y in range(before.height) for x in range(before.width) if before.getpixel((x, y)) != after.getpixel((x, y))]
        xs, ys = [p[0] for p in changed], [p[1] for p in changed]
        # only around the word at the TV screen's lower part, never in the 'Kirby' wordmark rows
        self.assertGreater(min(ys), 60)
        self.assertGreater(min(xs), 50)
        self.assertEqual(record['meta/icon.bin']['changed'], ['arc/blyt/icon.brlyt', 'arc/timg/ENG_channel.tpl'])


class TestBuildV8(unittest.TestCase):
    def test_v8_reproducible_and_scoped(self):
        out = ROOT / 'workspace/channels/kirbytv/build-v8'
        if not (out / 'kirbytv-ko-local-test.wad').exists():
            self.skipTest('build-v8 not present')
        manifest = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        title, reference, record = kirbytv_build.build_title(local=True, revision=8)
        self.assertEqual(hashlib.sha256(title.dump_wad()).hexdigest(), manifest['wad_sha256'])
        v7 = ROOT / 'workspace/channels/kirbytv/build-v7/kirbytv-ko-local-test.wad'
        if v7.exists():
            old = load_library().title.Title()
            old.load_wad(v7.read_bytes())
            self.assertEqual([i for i in range(len(title.tmd.content_records))
                              if title.get_content_by_index(i) != old.get_content_by_index(i)], [0, 2])
        swf = ChannelArchive(title.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH)
        self.assertEqual(sorted(record['content2']['swf']['logo_bitmaps']), ['1403', '1406', '1409', '1782', '1785'])
        self.assertEqual(record['content2']['swf']['GumballButtonToolTip']['label_check']['size_px'], 23.0)
        self.assertFalse(manifest['full_localization_complete'] or manifest['hardware_success_verified'])


def _bitmap_users(fws, cid):
    """Shape character ids whose fill styles may reference bitmap cid (byte scan, superset)."""
    import struct
    needle = struct.pack('<H', cid)
    users = []
    for code, pos, head, length in kirbytv_swf.tags(fws):
        if code in (2, 22, 32, 83):
            body = fws[pos + head:pos + head + length]
            if any(body[k] in (0x40, 0x41, 0x42, 0x43) and body[k + 1:k + 3] == needle for k in range(2, len(body) - 2)):
                users.append(struct.unpack_from('<H', body, 0)[0])
    return users


class TestLogoV9(unittest.TestCase):
    """Revision 9: '채널' in the usual top-left logo (mc_logo, sprite 1848, frame image 1840)."""

    @classmethod
    def setUpClass(cls):
        from kwce import kirbytv_logo
        cls.L = kirbytv_logo
        cls.swf = _wiilink_swf()
        cls.v8 = kirbytv_logo.korean_logo_set(cls.swf)
        cls.v9 = kirbytv_logo.korean_logo_set(cls.swf, mc_logo=True)

    def test_mc_logo_image_only_adds_1840(self):
        import struct
        self.assertEqual(sorted(self.v9['bitmaps']), sorted(self.v8['bitmaps']) + [self.L.MC_LOGO_ENG])
        for cid, payload in self.v8['bitmaps'].items():
            self.assertEqual(self.v9['bitmaps'][cid], payload, cid)
        self.assertEqual(self.v9['icon_word'].tobytes(), self.v8['icon_word'].tobytes())
        payload = self.v9['bitmaps'][self.L.MC_LOGO_ENG]
        self.assertEqual(struct.unpack_from('<BHH', payload, 2), (5, 162, 104))
        self.assertLess(self.v9['record']['mc_logo_still']['residual_outside_mask'], 6.0)
        _, _, fws = kirbytv_swf.unpack(self.swf)
        self.assertEqual(_bitmap_users(fws, self.L.MC_LOGO_ENG), [1841])
        before = self.L.bitmap(fws, self.L.MC_LOGO_ENG)
        after = self.L.bitmap(self.L.replace_bitmaps(fws, {self.L.MC_LOGO_ENG: payload}), self.L.MC_LOGO_ENG)
        changed = [(x, y) for y in range(104) for x in range(162) if before.getpixel((x, y)) != after.getpixel((x, y))]
        # only around the word on the TV screen (lower right), never the 'Kirby' wordmark or 'TV'
        self.assertGreater(min(y for _, y in changed), 50)
        self.assertGreater(min(x for x, _ in changed), 50)
        self.assertEqual(self.L.korean_logo_set(self.swf, mc_logo=True)['bitmaps'], self.v9['bitmaps'])


class TestBuildV9(unittest.TestCase):
    def test_v9_reproducible_and_scoped(self):
        out = ROOT / 'workspace/channels/kirbytv/build-v9'
        if not (out / 'kirbytv-ko-local-test.wad').exists():
            self.skipTest('build-v9 not present')
        manifest = json.loads((out / 'build-manifest.json').read_text(encoding='utf-8'))
        title, reference, record = kirbytv_build.build_title(local=True, revision=9)
        self.assertEqual(hashlib.sha256(title.dump_wad()).hexdigest(), manifest['wad_sha256'])
        swf = ChannelArchive(title.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH)
        _, _, fws = kirbytv_swf.unpack(swf)
        v8 = ROOT / 'workspace/channels/kirbytv/build-v8/kirbytv-ko-local-test.wad'
        if v8.exists():
            old = load_library().title.Title()
            old.load_wad(v8.read_bytes())
            self.assertEqual([i for i in range(len(title.tmd.content_records))
                              if title.get_content_by_index(i) != old.get_content_by_index(i)], [2])
            _, _, before = kirbytv_swf.unpack(ChannelArchive(old.get_content_by_index(2)).get(kirbytv_swf.SWF_PATH))
            names = kirbytv_swf.exports(before)
            diff = []
            self.assertEqual(len(kirbytv_swf.tags(before)), len(kirbytv_swf.tags(fws)))
            for (c1, p1, h1, l1), (c2, p2, h2, l2) in zip(kirbytv_swf.tags(before), kirbytv_swf.tags(fws)):
                if before[p1:p1 + h1 + l1] != fws[p2:p2 + h2 + l2]:
                    cid = __import__('struct').unpack_from('<H', before, p1 + h1)[0]
                    diff.append((c1, c2, str(names.get(cid, cid))))
            self.assertEqual(sorted(diff), sorted([(59, 59, '__Packages.gb.buttons.GumballButtonToolTip'), (35, 36, '1840')]))
        code = kirbytv_swf.init_actions(fws)['__Packages.gb.buttons.GumballButtonToolTip'][2]
        self.assertIn(b'kwceTipWidth', code)
        self.assertNotIn(b'LANG_KOREAN', code)
        self.assertEqual(sorted(record['content2']['swf']['logo_bitmaps']), ['1403', '1406', '1409', '1782', '1785', '1840'])
        self.assertIn('every console', record['content2']['swf']['GumballButtonToolTip']['scope'])
        self.assertFalse(manifest['full_localization_complete'] or manifest['hardware_success_verified'])


if __name__ == '__main__':
    unittest.main()
