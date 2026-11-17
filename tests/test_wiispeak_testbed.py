import configparser
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kwce import wiispeak_testbed as bed  # noqa: E402

FEED_RUNNER = ROOT / 'scripts/FeedRunner.cs'


class RunnerDerivationTest(unittest.TestCase):
    def test_keeps_capability_zero_container_and_drops_feed_server(self):
        text = FEED_RUNNER.read_text()
        out = bed.derive_runner(text)
        for needed in ('class WiiSpeakRunner', '"wiispeak-test-v1"', '000100014843464b', '--nand_title 0000000100000002',
                       'Child is not AppContainer', 'Child has capabilities', 'OS network probe did not pass'):
            self.assertIn(needed, out)
        for gone in ('FeedServer.exe', 'Spawn(sid', 'feed-ready.txt', '"news-v1"', '0001000248414745', 'class FeedRunner'):
            self.assertNotIn(gone, out)

    def test_source_guard_refuses_unexpected_runner(self):
        text = FEED_RUNNER.read_text()
        for broken in (text.replace(bed._BLOCK_START, ''), text + text, text.replace('class FeedRunner', 'class Other')):
            with self.assertRaises(ValueError):
                bed.derive_runner(broken)


class DolphinIniTest(unittest.TestCase):
    def bed_ini(self, root):
        source, base = root / 'votes-test-v1', root / 'wiispeak-test-v1'
        text = ('[Core]\nwiisdcard = True\ndefaultiso = C:/disc.iso\n'
                f'memcardapath = {source}\\user\\GC\\MemoryCardA.USA.raw\nEnableWiiLink = True\n'
                '[EmulatedUSBDevices]\nemulatewiispeak = True\n[usbpassthrough]\nDevices = 057e:0308\n'
                '[Interface]\nusepanichandlers = False\n')
        path = base / 'user/Config/Dolphin.ini'
        path.parent.mkdir(parents=True)
        path.write_text(bed.sanitized_dolphin_ini(text, source, base), encoding='utf-8')
        return path, base / 'user'

    def test_sanitize_forces_devices_off_without_case_duplicates(self):
        with tempfile.TemporaryDirectory(prefix='kwce-wiispeak-') as name:
            path, user = self.bed_ini(Path(name).resolve())
            bed.check_dolphin_ini(path, user)
            strict = configparser.ConfigParser(strict=True, interpolation=None)
            strict.read(path, encoding='utf-8')  # raises on a case-insensitive duplicate key
            sections = [s.lower() for s in strict.sections()]
            self.assertEqual(len(sections), len(set(sections)))
            self.assertEqual(strict['usbpassthrough']['devices'], '')
            self.assertEqual(strict['EmulatedUSBDevices']['emulatewiispeak'], 'False')
            self.assertTrue(Path(strict['Core']['memcardapath']).is_relative_to(user))

    def test_check_refuses_each_unsafe_setting(self):
        cases = [('EmulatedUSBDevices', 'EmulateWiiSpeak', 'True'), ('EmulatedUSBDevices', 'EmulateLogitechMic', 'maybe'),
                 ('USBPassthrough', 'Devices', '057e:0308'), ('BluetoothPassthrough', 'Enabled', 'True'),
                 ('Interface', 'UsePanicHandlers', 'False'), ('Core', 'EnableWiiLink', 'True'), ('Core', 'WiiSDCard', 'True'),
                 ('Core', 'DefaultISO', 'C:/disc.iso'), ('Core', 'MemcardAPath', 'C:/outside/card.raw')]
        for section, key, value in cases:
            with self.subTest(key=key), tempfile.TemporaryDirectory(prefix='kwce-wiispeak-') as name:
                path, user = self.bed_ini(Path(name).resolve())
                cfg = configparser.ConfigParser(strict=False, interpolation=None)
                cfg.optionxform = str
                cfg.read(path, encoding='utf-8')
                target = next(s for s in cfg.sections() if s.lower() == section.lower())
                for k in [k for k in cfg[target] if k.lower() == key.lower()]:
                    cfg.remove_option(target, k)
                cfg[target][key] = value
                with path.open('w', encoding='utf-8') as f:
                    cfg.write(f)
                with self.assertRaises(ValueError):
                    bed.check_dolphin_ini(path, user)


class PinnedBuildsTest(unittest.TestCase):
    def channel(self, root, original=None, **meta):
        digest = hashlib.sha256(b'original').hexdigest()
        (root / 'originals').mkdir()
        (root / 'hardware-v1').mkdir()
        row = dict(alias='wiispeak-korea-v512.wad', title_id=bed.TITLE, version=512, sha256=digest,
                   tmd_signature_valid=True, content_sha1_verified=True)
        row.update(original or {})
        (root / 'originals/acquisition.json').write_text(json.dumps(dict(titles=[row])), encoding='utf-8')
        manifest = dict(title_id=bed.TITLE, title_version=512, hardware_candidate=True, changed_contents=[1],
                        original_sha256=digest, wad_sha256=hashlib.sha256(b'candidate').hexdigest())
        manifest.update(meta)
        (root / 'hardware-v1/build-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return digest

    def test_consistent_manifests_pin_both_builds(self):
        with tempfile.TemporaryDirectory(prefix='kwce-wiispeak-') as name:
            root = Path(name)
            digest = self.channel(root)
            self.assertEqual(bed.pinned_builds(root), {'original-v512': digest, 'hardware-v1': hashlib.sha256(b'candidate').hexdigest()})

    def test_inconsistent_manifests_refused(self):
        cases = [dict(original=dict(tmd_signature_valid=False)), dict(original=dict(title_id='0001000148434645')),
                 dict(changed_contents=[1, 2]), dict(original_sha256='0' * 64), dict(hardware_candidate=False),
                 dict(wad_sha256=hashlib.sha256(b'original').hexdigest())]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix='kwce-wiispeak-') as name:
                self.channel(Path(name), **case)
                with self.assertRaises(ValueError):
                    bed.pinned_builds(Path(name))


@unittest.skipUnless((ROOT / bed.CHANNEL / bed.BUILDS['hardware-v1']).exists(), 'ignored Wii Speak WADs not present')
class RealChannelPinsTest(unittest.TestCase):
    def test_pins_match_the_preserved_wads(self):
        pinned = bed.pinned_builds(ROOT / bed.CHANNEL)
        for name, rel in bed.BUILDS.items():
            self.assertEqual(hashlib.sha256((ROOT / bed.CHANNEL / rel).read_bytes()).hexdigest(), pinned[name], name)


if __name__ == '__main__':
    unittest.main()
