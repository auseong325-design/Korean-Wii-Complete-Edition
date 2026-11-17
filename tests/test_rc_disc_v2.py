"""RC30 disc profiles: GC card-menu fixes + frozen forwarder DVD section, through the old parser."""
import hashlib
import json
import struct
import unittest
from pathlib import Path

from kwce import rc_disc_v2, rc_hardware
from kwce.gc_native import dol_offset
from kwce.priiloader_hacks import GROUPS, hacks, DVD_GROUP, GC_LAYOUT_GROUP
from kwce.priiloader_legacy import parse, apply_streaming

ROOT = Path(__file__).resolve().parents[1]
MENU = ROOT / 'workspace/console-baseline/menu-original-43K.dol'
TESTED = ROOT / 'workspace/linux/menu-v24/user/Wii/title/00000001/00000002/content/0000009e.app'
FORWARDER_V2 = ROOT / 'workspace/hardware/kwce-dvd-forwarder-v2'


class DiscProfileV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.menu = MENU.read_bytes()
        cls.only, cls.only_rec = rc_hardware.disc_ini_v2(cls.menu, dvd=False, dvd_hook=77)
        cls.dvd, cls.dvd_rec = rc_hardware.disc_ini_v2(cls.menu, dvd=True, dvd_hook=77)

    def test_section_names_and_order(self):
        gc = [name for name, _, _ in GROUPS]
        self.assertEqual([r['name'] for r in parse(self.only)], gc + [GC_LAYOUT_GROUP])
        self.assertEqual([r['name'] for r in parse(self.dvd)], gc + [DVD_GROUP])

    def test_card_menu_fixes_are_in_the_result(self):
        image = apply_streaming(self.menu, parse(self.dvd))
        word = lambda a: struct.unpack_from('>I', image, dol_offset(image, a))[0]
        self.assertEqual(word(0x815375ac), 0x38600000)              # CARDInit: li r3,0 (ANSI format)
        call = word(0x813cd634)                                     # getComment -> region dispatcher
        self.assertEqual(0x813cd634 + ((call & 0x3fffffc) ^ 0x2000000) - 0x2000000, 0x81545a20)

    def test_gc_dvd_equals_the_menu_tested_in_dolphin(self):
        image = apply_streaming(self.menu, parse(self.dvd))
        self.assertEqual(image, rc_disc_v2.final_image(self.menu, 77))
        if TESTED.exists():
            self.assertEqual(image, TESTED.read_bytes())

    def test_unchanged_sections_stay_byte_identical(self):
        from kwce.dvd_integrated_hardware import definition
        self.assertIn(definition(77), self.dvd)
        delivered = {r['name']: r for r in parse((FORWARDER_V2 / 'kwce-rc/priiloader/fragment-gc-dvd.ini').read_bytes())}
        rows = {r['name']: r for r in parse(self.dvd)}
        self.assertEqual(rows[GROUPS[0][0]], delivered[GROUPS[0][0]])
        self.assertEqual(rows[DVD_GROUP], delivered[DVD_GROUP])
        self.assertNotEqual(rows[GROUPS[1][0]], delivered[GROUPS[1][0]])
        self.assertNotEqual(rows[GROUPS[2][0]], delivered[GROUPS[2][0]])
        self.assertEqual(parse(self.only)[0], {k: v for k, v in rows[GROUPS[0][0]].items()})

    def test_gc_only_has_no_dvd_and_keeps_the_layout(self):
        image = apply_streaming(self.menu, [r for r in parse(self.only) if r['name'] != GC_LAYOUT_GROUP])
        self.assertEqual(image, rc_disc_v2.final_image(self.menu))
        self.assertFalse(self.only_rec['dvd_hook'])
        self.assertTrue(self.only_rec['gc_only_layout'])

    def test_first_section_matches_the_rc29_generator(self):
        self.assertEqual(rc_disc_v2.gc_entries(self.menu)[0], hacks(self.menu)[0])

    def test_runtime_files_equal_the_forwarder_delivery(self):
        from kwce.channels import load_library
        cfg = json.loads((ROOT / 'configs/rc-package-v30-ko.json').read_text(encoding='utf-8'))
        files, hook = rc_disc_v2.runtime_files(cfg['native_dvd'], cfg['dvd_forwarder'], load_library())
        self.assertEqual(hook, 77)
        self.assertEqual(sorted(files), ['kwce/dvd/boot.ash', 'kwce/dvd/home.arc', 'kwce/dvd/icon.arc',
                                         'kwce/dvd/menu.arc', 'kwce/dvd/player.dol', 'kwce/dvd/wbf1.brfna'])
        self.assertTrue(all(rc_hardware.allowed(p) for p in files))

    def test_rc31_runtime_files_pin_the_new_pair(self):
        # RC31: native79 + R66 shipped only in the RC; unchanged resources equal forwarder-v2.
        from kwce.channels import load_library
        from kwce.dvd_forwarder_sd import frozen_inputs
        cfg = json.loads((ROOT / 'configs/rc-package-v31-ko.json').read_text(encoding='utf-8'))
        files, hook = rc_disc_v2.runtime_files(cfg['native_dvd'], cfg['dvd_forwarder'], load_library())
        self.assertEqual((hook, cfg['native_dvd']['home_ui']), (79, 9))
        module, player = frozen_inputs(3)
        self.assertEqual((files['kwce/dvd/boot.ash'], files['kwce/dvd/player.dol']), (module, player))
        delivered = json.loads((ROOT / 'workspace/hardware/kwce-dvd-forwarder-v2/package-manifest.json')
                               .read_text())['runtime_inputs']
        for rel in ('kwce/dvd/icon.arc', 'kwce/dvd/menu.arc', 'kwce/dvd/wbf1.brfna'):
            self.assertEqual(rc_hardware.sha(files[rel]), delivered[rel])
        self.assertNotEqual(rc_hardware.sha(files['kwce/dvd/home.arc']), delivered['kwce/dvd/home.arc'])
        # The streamed gc-dvd profile is the menu qualified in Dolphin (menu-v27/v28).
        menu = (ROOT / 'workspace/console-baseline/menu-original-43K.dol').read_bytes()
        self.assertEqual(hashlib.sha256(rc_disc_v2.final_image(menu, 79)).hexdigest()[:16], '6f23b773627b7082')

    def test_account_linker_paths_allowed(self):
        for path in rc_hardware.ACCOUNT_LINKER_FILES:
            self.assertTrue(rc_hardware.allowed(path))
        self.assertFalse(rc_hardware.allowed('apps/wiilink-account-linker/extra.dol'))


if __name__ == '__main__':
    unittest.main()
