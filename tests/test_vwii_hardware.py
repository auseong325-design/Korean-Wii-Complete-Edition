"""vWii conversion and deployment boundary regressions (no console access)."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from kwce.vwii_hardware import (APP, DATA, README, KIND, TITLES, convert_wad,
                                 installer_source, sd_files, sha, validate_rows)
from kwce.channels import load_library

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import deploy_channel_package as deployment


def fixture(root):
    rows = [dict(id=c, title_id=t) for c, t in TITLES.items()]
    files = {f'{APP}/{n}': n.encode() for n in ('boot.dol', 'meta.xml', 'icon.png')}
    files.update({f'{DATA}/packages.txt': b'list', README: b'guide'})
    files.update({f'{DATA}/{c}/korean.wad': c.encode() for c in TITLES})
    for name, data in files.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    record = dict(kind=KIND, package='kwce-vwii-ko-v1', channels=rows,
                  menu_writer_linked=False, priiloader_update=False,
                  system_titles_included=False, iso_included=False,
                  hardware_success_verified=False, publish=False,
                  install_only=True, downgrade_allowed=False,
                  compile_warnings=0, forbidden_symbols_absent=True, configuration_save_wrapped=True,
                  sd_files=[dict(path=n, bytes=len(b), sha256=sha(b)) for n, b in files.items()])
    save_manifest(root, record)
    return record


def save_manifest(root, record):
    raw = json.dumps(record).encode()
    (root/'package-manifest.json').write_bytes(raw)
    (root/'package-manifest.sha256').write_text(sha(raw))


class VwiiBoundaryTests(unittest.TestCase):
    def test_system_title_duplicate_and_id_title_mismatch_refused(self):
        good = [dict(id=c, title_id=t) for c, t in TITLES.items()]
        validate_rows(good)
        for key, value in [('title_id', '0000000100000002'), ('id', '../state')]:
            bad = [dict(r) for r in good]
            bad[0][key] = value
            with self.assertRaises(ValueError):
                validate_rows(bad)
        with self.assertRaises(ValueError):
            validate_rows(good+[good[0]])

    def test_installer_cannot_write_system_menu_settings_or_delete_title_contents(self):
        rows = json.loads((ROOT/'configs/hardware-vwii-ko-v1.json').read_text())['channels']
        code = installer_source((ROOT/'homebrew/kwce-installer/source/main.c').read_text(), rows)
        self.assertIn('target_vwii && target_korean ? IOS_ReloadIOS(249) : -1', code)
        for forbidden in ('ES_DeleteTitleContent(', 'menu_install(', 'menu_restore(',
                          'CONF_SaveChanges(', 'ISFS_Write(', 'do_restore(',
                          'allow-current-ios.txt', 'sd:/kwce"'):
            self.assertNotIn(forbidden, code)
        self.assertIn('Downgrades are refused', code)
        self.assertIn('sd:/kwce-vwii', code)

    def test_manifest_rejects_corruption_system_scope_and_state_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = fixture(root)
            _, plan = sd_files(root)
            self.assertEqual(len(plan), 13)
            (root/APP/'boot.dol').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                sd_files(root)
            (root/APP/'boot.dol').write_bytes(b'boot.dol')
            for flag in ('system_titles_included', 'priiloader_update', 'hardware_success_verified',
                         'downgrade_allowed'):
                bad = dict(record, **{flag: True})
                save_manifest(root, bad)
                with self.assertRaises(ValueError):
                    sd_files(root)
            record['sd_files'][0]['path'] = DATA+'/state/forecast.txt'
            save_manifest(root, record)
            with self.assertRaises(ValueError):
                sd_files(root)

    def test_mock_card_copy_preserves_guide_wii_and_vwii_state_and_backs_up_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            package = root/'package'
            package.mkdir()
            fixture(package)
            card = root/'card'
            card.mkdir()
            protected = {'apps/Priiloader/hacks_hash.ini': b'guide hacks',
                         'apps/kor-vwii/boot.dol': b'guide app',
                         'apps/kwce-installer/boot.dol': b'Wii app',
                         'kwce/packages.txt': b'Wii packages',
                         'kwce-vwii/state/forecast.txt': b'first state',
                         'kwce-vwii/log.txt': b'console log',
                         'kwce-dvd-test/packages.txt': b'dvd'}
            for name, data in {**protected, f'{APP}/boot.dol': b'old candidate'}.items():
                p = card/name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            before = deployment.PRIVATE
            deployment.PRIVATE = root/'evidence'
            try:
                deployment.deploy(package, card, True, verifier=sd_files)
                self.assertEqual((card/APP/'boot.dol').read_bytes(), b'old candidate')
                deployment.deploy(package, card, verifier=sd_files)
                for name, data in protected.items():
                    self.assertEqual((card/name).read_bytes(), data)
                backup = next((card/'kwce-deploy-backups').iterdir())
                self.assertEqual((backup/APP/'boot.dol').read_bytes(), b'old candidate')
                result = json.loads(next(deployment.PRIVATE.glob('*/result.json')).read_text())
                self.assertEqual(result['unplanned_changes'], 0)
                self.assertEqual(result['verified_files'], 13)
            finally:
                deployment.PRIVATE = before


@unittest.skipUnless((ROOT/'workspace/channels/forecast/build-v103').exists(), 'Local source absent')
class VwiiWadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = json.loads((ROOT/'configs/hardware-vwii-ko-v1.json').read_text())
        row = next(r for r in cfg['channels'] if r['id'] == 'forecast')
        cls.korean = (ROOT/'workspace/channels/forecast'/row['korean']).read_bytes()
        cls.original = (ROOT/'workspace/channels/forecast'/row['original']).read_bytes()

    def mutate(self, change):
        t = load_library().title.Title()
        t.load_wad(self.korean)
        change(t)
        return t.dump_wad()

    def test_conversion_preserves_contents_and_repeats_identically(self):
        converted, checks = convert_wad(self.korean, self.original, 'forecast')
        again, _ = convert_wad(self.korean, self.original, 'forecast')
        self.assertEqual(converted, again)
        before, after = load_library().title.Title(), load_library().title.Title()
        before.load_wad(self.korean)
        after.load_wad(converted)
        self.assertEqual(after.tmd.region, 3)
        self.assertEqual(after.tmd.ios_tid, before.tmd.ios_tid)
        self.assertEqual(after.tmd.title_id, before.tmd.title_id)
        for i in range(len(before.tmd.content_records)):
            self.assertEqual(after.get_content_by_index(i), before.get_content_by_index(i))
        self.assertFalse(checks['hardware_success_verified'])

    def test_wrong_ios_system_flag_and_personalized_ticket_refused(self):
        changes = [lambda t: setattr(t.tmd, 'ios_tid', '00000001000000f9'),
                   lambda t: setattr(t.tmd, 'vwii', 1),
                   lambda t: setattr(t.ticket, 'console_id', 1)]
        for change in changes:
            with self.assertRaises(ValueError):
                convert_wad(self.mutate(change), self.original, 'forecast')

    def test_system_title_and_wrong_channel_refused(self):
        with self.assertRaises(ValueError):
            convert_wad(self.korean, self.original, 'dvd-player')
        with self.assertRaises(ValueError):
            convert_wad(self.korean, self.original, 'news')
        with self.assertRaises(ValueError):
            convert_wad(self.mutate(lambda t: setattr(t.tmd, 'title_id', '0000000100000002')),
                        self.original, 'forecast')
