"""Unit tests for the Korean-console WiiLink Food editions (kwce.food_variants). No Dolphin.

Run: .venv\\Scripts\\python.exe -m unittest tests.test_food_variants
"""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library, sha256  # noqa: E402
from kwce import bspatch, food_variants as fv  # noqa: E402
from kwce.wiiroom_formats import decompress_lz11  # noqa: E402

DOMINOS_SERVER = {18, 49}                       # Demae-Dominos dominos/new.go
JUSTEAT_SERVER = {66, 78, 82, 83, 105, 110}     # Demae-JustEat justeat/client.go GetCountry
HAVE_SOURCE = (ROOT / fv.SOURCE).is_file() and (ROOT / fv.REF).is_dir()


def _dols():
    lib = load_library()
    t = lib.title.Title()
    t.load_wad((ROOT / fv.SOURCE).read_bytes())
    stock = {i: t.get_content_by_index(i) for i in range(t.tmd.num_contents)}
    out = {}
    for edition in fv.EDITIONS:
        wl, _ = fv.edition_contents(stock, t.tmd.dump(), edition)
        raw = wl[1]
        out[edition] = decompress_lz11(raw) if raw[:1] == b'\x11' else raw
    return out


class Tables(unittest.TestCase):
    def test_countries_are_the_ones_the_servers_accept(self):
        dominos = {code for ed, code, _n, _k in fv.VARIANTS.values() if ed == 'dominos'}
        justeat = {code for ed, code, _n, _k in fv.VARIANTS.values() if ed == 'justeat'}
        self.assertEqual(dominos, DOMINOS_SERVER)
        self.assertEqual(justeat, JUSTEAT_SERVER)
        self.assertEqual(len(fv.VARIANTS), 8)

    def test_labels_and_names_fit(self):
        for variant in fv.VARIANTS:
            self.assertTrue(fv.label(variant).isascii() and '|' not in fv.label(variant))
            self.assertLessEqual(len(fv.label(variant)), 39)
            self.assertLessEqual(len(fv.korean_name(variant).encode('utf-16-be')) + 2, 84)
            self.assertRegex(variant, r'^[a-z0-9-]+$')


@unittest.skipUnless(HAVE_SOURCE, 'Food original / WiiLink edition patches not on disk')
class Executable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dols = _dols()

    def test_payload_section(self):
        for dol in self.dols.values():
            off = fv._payload(dol)
            self.assertGreater(off, 0)

    def test_country_one_word(self):
        for edition, dol in self.dols.items():
            for code in (18, 110):
                out, rec = fv.patch_country(dol, edition, code)
                diff = [i for i in range(len(dol)) if dol[i] != out[i]]
                self.assertEqual(len(out), len(dol))
                self.assertLessEqual(len(diff), 4)
                at = int(rec['dol_file_offset'], 16)
                self.assertEqual(struct.unpack_from('>I', dol, at)[0], fv.SRWI_R3_R29_24)
                self.assertEqual(struct.unpack_from('>I', out, at)[0], 0x38600000 | code)
                self.assertEqual(rec['site'], f"0x{fv.EDITIONS[edition]['country_site']:08x}")
                with self.assertRaises(ValueError):
                    fv.patch_country(out, edition, code)          # already patched: refuses
        self.assertEqual(fv.patch_country(self.dols['dominos'], 'dominos', 49)[1]['callers'], 3)
        self.assertEqual(fv.patch_country(self.dols['justeat'], 'justeat', 110)[1]['callers'], 2)

    def test_local_redirect(self):
        for edition, dol in self.dols.items():
            out, rec = fv.redirect_local(dol, edition)
            self.assertEqual(len(out), len(dol))
            self.assertEqual(rec['hosts'], 4)
            self.assertNotIn(fv.EDITIONS[edition]['host'], out)
            self.assertEqual(rec['https_downgraded'], 1 if edition == 'dominos' else 0)

    def test_default_id_check_is_dominos_only(self):
        out, rec = fv.skip_default_id_check(self.dols['dominos'])
        self.assertEqual(sum(a != b for a, b in zip(out, self.dols['dominos'])), 2)
        self.assertEqual(rec['patched'], '48000024')
        with self.assertRaises(ValueError):
            fv.skip_default_id_check(self.dols['justeat'])
        with self.assertRaises(ValueError):
            fv.build('dominos-us', local=False, revision=2)


class Builds(unittest.TestCase):
    def test_hardware_manifests(self):
        found = 0
        for variant, (edition, code, _n, _k) in fv.VARIANTS.items():
            folder = ROOT / f'workspace/channels/food/{variant}-hardware-v1'
            if not folder.is_dir():
                continue
            found += 1
            m = json.loads((folder / 'build-manifest.json').read_text(encoding='utf-8'))
            wad = (folder / 'food-ko-hardware-test.wad').read_bytes()
            self.assertEqual(sha256(wad), m['wad_sha256'])
            self.assertEqual((m['variant'], m['edition'], m['country_code']), (variant, edition, code))
            self.assertTrue(m['hardware_candidate'])
            self.assertFalse(m['local_only'] or m['real_orders_tested'] or m['hardware_success_verified'])
            self.assertEqual(m['changed_contents'], [0, 1, 2, 3, 4])
            self.assertEqual(m['tmd_region'], 4)
            self.assertNotIn(b'127.0.0', wad)
        if not found:
            self.skipTest('no edition hardware builds on disk')


if __name__ == '__main__':
    unittest.main()
