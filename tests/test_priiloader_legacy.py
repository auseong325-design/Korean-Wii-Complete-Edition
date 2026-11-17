import unittest
from pathlib import Path
from kwce.priiloader_legacy import parse,apply,apply_streaming,token_bytes,packed_tokens,checked_ini

ROOT=Path(__file__).resolve().parents[1]
MENU=ROOT/'workspace/console-baseline/menu-original-43K.dol'


class LegacyParserTests(unittest.TestCase):
    def test_packed_tokens_preserve_zero_leading_words_across_boundaries(self):
        data=bytes.fromhex('112233440080002055667788')
        words=packed_tokens(data)
        self.assertEqual(b''.join(token_bytes(f'0x{n:08x}') for n in words),data)
        with self.assertRaises(ValueError):packed_tokens(bytes.fromhex('00010203'))
        with self.assertRaises(ValueError):packed_tokens(bytes.fromhex('010000000002'))
    def raw(self,patch):
        return ('[test]\r\nmaxversion=518\r\nminversion=518\r\namount=1\r\n'
                'hash=0x11223344,0x55667788\r\npatch='+patch+'\r\n').encode()

    def test_zero_token_is_empty_and_all_zero_patch_causes_eof(self):
        self.assertEqual(token_bytes('0x00000000'),b'')
        self.assertEqual(token_bytes('0x00010000'),b'\x01\0\0')
        with self.assertRaisesRegex(ValueError,'unexpected EOF @ line 7'):
            parse(self.raw('0x00000000,0x00000000'))

    def test_zero_inside_a_word_is_preserved_but_zero_words_are_lost(self):
        entries=parse(self.raw('0x60000000,0x00000000,0x4e800020'))
        self.assertEqual(entries[0]['pairs'][0][1],bytes.fromhex('600000004e800020'))
        body=bytes.fromhex('112233445566778899aabbcc')
        self.assertEqual(apply(body,entries),bytes.fromhex('600000004e80002099aabbcc'))

    def test_export_gate_refuses_a_parseable_but_truncated_patch(self):
        body=bytes.fromhex('112233445566778899aabbcc')
        entries=[dict(name='test',pairs=[([0x11223344,0x55667788],[0x60000000,0])])]
        with self.assertRaisesRegex(ValueError,'lose leading zero bytes'):checked_ini(body,entries)

    def test_variable_width_original_short_tokens_remain_supported(self):
        entries=parse(self.raw('0x01,0x0200'))
        self.assertEqual(entries[0]['pairs'][0][1],b'\x01\x02\0')

    def test_known_bad_packages_are_refused_before_any_sd_write(self):
        import sys,tempfile
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/'scripts'))
        import deploy_dvd_package as deployment
        with tempfile.TemporaryDirectory()as folder:
            for kind in ['dvd-only-r25','dvd-only-r26']:
                with patch.object(deployment,'sd_files',return_value=(dict(kind=kind),[])):
                    with self.assertRaisesRegex(ValueError,'deployment withdrawn'):
                        deployment.deploy(folder,folder,True)
            self.assertEqual(list(Path(folder).iterdir()),[])


@unittest.skipUnless(MENU.exists(),'local original menu missing')
class NativeLegacyRegressionTests(unittest.TestCase):
    def test_v16_packed_profile_matches_reviewed_menu_in_forward_order(self):
        import json
        from kwce.rc_hardware import disc_ini
        from kwce.gc_native import patch_gc_native
        menu=MENU.read_bytes();pin_path=ROOT/'workspace/experiments/dvd-native-hook-v16/manifest.json'
        if not pin_path.exists():self.skipTest('v16 candidate not built')
        cfg=json.loads((ROOT/'configs/rc-package-v24-ko.json').read_text(encoding='utf-8'))
        if cfg.get('native_dvd',{}).get('hook')!='dvd-native-hook-v16':self.skipTest('v16 snapshot unavailable')
        raw,_=disc_ini(menu,dvd=True,native_dvd=cfg['native_dvd'],strict_search_order=True,packed_tokens=True)
        expected=(pin_path.parent/'menu.dol').read_bytes()
        self.assertEqual(apply_streaming(menu,parse(raw)),expected)

    def test_v23_packed_profile_matches_reviewed_menu_in_forward_order(self):
        import json
        from kwce.rc_hardware import disc_ini
        menu=MENU.read_bytes()
        cfg=json.loads((ROOT/'configs/rc-package-v25-ko.json').read_text(encoding='utf-8'))
        if cfg.get('native_dvd',{}).get('hook')!='dvd-native-hook-v23':self.skipTest('v23 snapshot unavailable')
        raw,_=disc_ini(menu,dvd=True,native_dvd=cfg['native_dvd'],strict_search_order=True,packed_tokens=True)
        expected=(ROOT/'workspace/experiments/dvd-native-hook-v23/menu.dol').read_bytes()
        self.assertEqual(apply_streaming(menu,parse(raw)),expected)

    def test_v27_packed_profile_matches_reviewed_menu_in_forward_order(self):
        import json
        from kwce.rc_hardware import disc_ini
        menu=MENU.read_bytes()
        cfg=json.loads((ROOT/'configs/rc-package.json').read_text(encoding='utf-8'))
        if cfg.get('native_dvd',{}).get('hook')!='dvd-native-hook-v27':self.skipTest('v27 not selected')
        raw,_=disc_ini(menu,dvd=True,native_dvd=cfg['native_dvd'],strict_search_order=True,packed_tokens=True)
        expected=(ROOT/'workspace/experiments/dvd-native-hook-v27/menu.dol').read_bytes()
        self.assertEqual(apply_streaming(menu,parse(raw)),expected)

    def test_gc_only_profile_follows_real_forward_cursor(self):
        from kwce.priiloader_hacks import gc_layout_entry
        from kwce.gc_disc_layout import patch_gc_only_layout
        menu=MENU.read_bytes()
        old=parse(checked_ini(menu,[gc_layout_entry(menu)]))
        with self.assertRaisesRegex(ValueError,'forward search failed.*pair 9'):
            apply_streaming(menu,old)
        new=parse(checked_ini(menu,[gc_layout_entry(menu,ordered=True)]))
        self.assertEqual(apply_streaming(menu,new),patch_gc_only_layout(menu)[0])

    def test_r25_bytes_differ_and_r26_eof_reproduces(self):
        old25=ROOT/'workspace/hardware/kwce-dvd-r25-v1/priiloader/kwce-hacks.ini'
        old26=ROOT/'workspace/hardware/kwce-dvd-r26-v1/priiloader/kwce-hacks.ini'
        if not old25.exists()or not old26.exists():self.skipTest('old candidates not present')
        from kwce.dvd_disc_banner_hook_v10 import patch_dvd_banner_hook
        menu=MENU.read_bytes()
        self.assertNotEqual(apply(menu,parse(old25.read_bytes())),patch_dvd_banner_hook(menu)[0])
        with self.assertRaisesRegex(ValueError,'unexpected EOF @ line 47'):parse(old26.read_bytes())

    def test_v12_real_legacy_bytes_equal_hook_with_and_without_gc(self):
        from kwce.priiloader_hacks import hacks,DVD_GROUP
        from kwce.dvd_disc_banner_hook_v12 import patch_dvd_banner_hook
        from kwce.gc_native import patch_gc_native
        menu=MENU.read_bytes();entries=hacks(menu,dvd=True,dvd_banner=12)
        dvd=[e for e in entries if e['name']==DVD_GROUP]
        self.assertEqual(apply(menu,parse(checked_ini(menu,dvd))),patch_dvd_banner_hook(menu)[0])
        gc=patch_gc_native(menu,japanese_cards=True,japanese_comments=True)[0]
        self.assertEqual(apply(menu,parse(checked_ini(menu,entries))),patch_dvd_banner_hook(gc)[0])

    def test_export_gate_rejects_r26_and_cave_guard_rejects_corruption(self):
        from kwce.priiloader_hacks import hacks,DVD_GROUP
        from kwce.dvd_disc_banner_hook_v12 import patch_dvd_banner_hook,CAVE,END
        from kwce.ppc_patch import to_file
        menu=MENU.read_bytes()
        dvd=[e for e in hacks(menu,dvd=True,dvd_banner=11)if e['name']==DVD_GROUP]
        with self.assertRaises(ValueError):checked_ini(menu,dvd)
        for address in [CAVE,END-4]:
            bad=bytearray(menu);bad[to_file(bad,address)]^=1
            with self.assertRaises(ValueError):patch_dvd_banner_hook(bytes(bad))


if __name__=='__main__':unittest.main()
