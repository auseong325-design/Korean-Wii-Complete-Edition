import hashlib
import struct
import unittest
from pathlib import Path

from kwce import channel_script as cs
from kwce import forecast_banner_language as fbl
from kwce.channels import ChannelArchive, load_library

ROOT = Path(__file__).resolve().parents[1]
V103 = ROOT / 'workspace/channels/forecast/build-v103/forecast-ko-personal-test.wad'
V106 = ROOT / 'workspace/channels/forecast/build-v106/forecast-ko-personal-test.wad'


def _contents(path):
    title = load_library().title.Title()
    title.load_wad(path.read_bytes())
    return [title.get_content_by_index(i) for i in range(12)]


def _modules(contents):
    return (fbl._lz(ChannelArchive(contents[4]).get(fbl.ICON_MEMBER)),
            fbl._lz(ChannelArchive(contents[5]).get(fbl.BANNER_MEMBER)))


def _run_check(script, pc, data_lang, console_lang):
    """Evaluate one patched/original icon language check; True = data accepted."""
    module = cs.parse(script)
    ins = {i['pc']: i for i in cs.decode(module)}
    stack, acc, at = [data_lang], data_lang, pc
    while True:
        if at == pc + 20:
            return True
        i = ins[at]
        m, nxt = i['mnemonic'], at + i['size']
        if m == 'load' and i['text'] == 'load System':
            acc = 'System'
        elif m == 'callm' and i['method'] == 'SCGetLanguage':
            acc = console_lang
        elif m == 'ne':
            acc = int(stack.pop() != acc)
        elif m == 'case':
            if stack and stack[-1] == acc:
                stack.pop()
                nxt = i['target']
        elif m == 'gei':
            acc = int(acc >= int(i['text'].split()[1]))
        elif m in ('bf', 'bt'):
            if bool(acc) == (m == 'bt'):
                nxt = i['target']
        elif m == 'ldi':
            acc = int(i['text'].split()[1])
        elif m == 'pop':
            acc = stack.pop()
        elif m == 'retv':
            if stack:
                raise AssertionError('unbalanced stack on failure path')
            return False
        elif m in ('ldstr', 'push', 'callf') or i['text'] == 'load print':
            if m == 'push':
                stack.append(acc)
            elif m == 'callf':
                stack.pop()
        else:
            raise AssertionError(f'unexpected {i["text"]}')
        at = nxt


@unittest.skipUnless(V103.exists(), 'Forecast build-v103 not present')
class ForecastBannerLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contents = _contents(V103)
        cls.icon, cls.rso = _modules(cls.contents)

    def test_decoder_reads_whole_icon_script(self):
        m = cs.parse(self.icon)
        self.assertEqual((len(m['code']), len(m['symbols']), len(m['methods']), len(m['strings'])), (8464, 19, 35, 86))
        self.assertFalse([i for i in cs.decode(m) if i['mnemonic'] == 'db'])
        self.assertIn('wc24dl.vff', m['strings'])
        self.assertIn('$ forecastData: language changed.\n', m['strings'])

    def test_icon_patch_rule(self):
        patched, record = fbl.patch_icon_script(self.icon)
        self.assertEqual(len(patched), len(self.icon))
        diff = [k for k in range(len(patched)) if patched[k] != self.icon[k]]
        code = 0x20 + struct.unpack_from('>I', self.icon, 0x30)[0]
        windows = [range(code + pc, code + pc + 20) for pc in fbl.ICON_CHECKS]
        self.assertTrue(all(any(k in w for w in windows) for k in diff))
        for pc in fbl.ICON_CHECKS:
            for data, console, want in [(1, 9, True), (9, 9, True), (1, 1, True), (0, 0, True), (6, 6, True),
                                        (0, 1, False), (2, 1, False), (1, 0, False), (3, 9, False), (1, 7, True)]:
                self.assertEqual(_run_check(patched, pc, data, console), want, (pc, data, console))
                self.assertEqual(_run_check(self.icon, pc, data, console), data == console, (pc, data, console))

    def test_rso_patch_redirects_both_language_calls(self):
        patched, record = fbl.patch_banner_rso(self.rso)
        self.assertEqual(len(patched), len(self.rso))
        for off in fbl.RSO_CALLS:
            word = struct.unpack_from('>I', patched, off)[0]
            delta = word & 0x03FFFFFC
            self.assertEqual(word & 0xFC000003, 0x48000001)
            self.assertEqual(off + delta, fbl.RSO_GET_LANGUAGE)
        erel, ersz, imports, _ = fbl._rso_tables(patched)
        lang = imports.index('SCGetLanguage')
        types = {}
        for i in range(ersz // 12):
            off, info, _ = struct.unpack_from('>III', patched, erel + 12 * i)
            if info >> 8 == lang:
                types[off] = info & 0xFF
        self.assertEqual(types[fbl.RSO_CALLS[0]], 0)
        self.assertEqual(types[fbl.RSO_CALLS[1]], 0)
        self.assertEqual(types[fbl.RSO_GET_LANGUAGE + 0xC], fbl.R_PPC_REL24)  # Common::getLanguage keeps SCGetLanguage
        changed = [k for k in range(len(patched)) if patched[k] != self.rso[k]]
        self.assertEqual(len(changed) <= 16, True)

    def test_guards_refuse_other_modules(self):
        with self.assertRaises(ValueError):
            fbl.patch_icon_script(fbl.patch_icon_script(self.icon)[0])
        with self.assertRaises(ValueError):
            fbl.patch_banner_rso(fbl.patch_banner_rso(self.rso)[0])

    def test_patch_contents_is_deterministic(self):
        a = fbl.patch_contents(self.contents[4], self.contents[5])
        b = fbl.patch_contents(self.contents[4], self.contents[5])
        self.assertEqual(a[:2], b[:2])
        icon, rso = _modules([None, None, None, None, a[0], a[1]])
        self.assertEqual(icon, fbl.patch_icon_script(self.icon)[0])
        self.assertEqual(rso, fbl.patch_banner_rso(self.rso)[0])

    @unittest.skipUnless(V106.exists(), 'Forecast build-v106 not built')
    def test_v106_changes_only_banner_contents(self):
        new = _contents(V106)
        self.assertEqual([i for i in range(12) if new[i] != self.contents[i]], [4, 5])
        self.assertEqual(hashlib.sha256(new[1]).digest(), hashlib.sha256(self.contents[1]).digest())


if __name__ == '__main__':
    unittest.main()
