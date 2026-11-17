"""Regression evidence for the one-call KOR service-language candidate."""
import unittest
from pathlib import Path
from kwce.channels import load_library
from kwce.ppc_patch import to_file
from scripts.build_nintendo_language_fix import CALL, build

ROOT = Path(__file__).resolve().parents[1]


def title(path):
    obj = load_library().title.Title(); obj.load_wad(path.read_bytes()); return obj


@unittest.skipUnless((ROOT/'workspace/channels/nintendo/build-v17/nintendo-ko-ui-test.wad').is_file(), 'local Nintendo candidate parent required')
class NintendoLanguageCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = title(ROOT/'workspace/channels/nintendo/build-v17/nintendo-ko-ui-test.wad')
        wad, cls.meta = build()
        cls.new = load_library().title.Title(); cls.new.load_wad(wad)
        diagnostic_path = ROOT/'workspace/channels/nintendo/access-build-v22/nintendo-local-test.wad'
        cls.diagnostic = title(diagnostic_path) if diagnostic_path.is_file() else None

    def test_edit_boundary_and_diagnostic_equivalence(self):
        old, new = self.old.get_content_by_index(1), self.new.get_content_by_index(1)
        at = to_file(old, CALL, 4)
        self.assertEqual(new[at:at+4], bytes.fromhex('38600001'))
        self.assertEqual(old[:at], new[:at]); self.assertEqual(old[at+4:], new[at+4:])
        for i in range(len(self.old.tmd.content_records)):
            if i != 1:
                self.assertEqual(self.old.get_content_by_index(i), self.new.get_content_by_index(i))
        # The local v22 test adds only four labeled 262000 sites to this candidate.
        if self.diagnostic is None:
            return  # The diagnostic artifact is optional in a fresh workspace.
        from scripts.audit_nintendo_error_sites import SITES
        expected = bytearray(new)
        for i, site in enumerate(SITES, 1):
            off = to_file(new, site, 4)
            self.assertEqual(int.from_bytes(expected[off+2:off+4], 'big'), 0xff70)
            expected[off+2:off+4] = (0xff70+i).to_bytes(2, 'big')
        self.assertEqual(bytes(expected), self.diagnostic.get_content_by_index(1))

    def test_metadata_states_limits(self):
        fix = self.meta['service_language_fix']
        self.assertFalse(fix['wii_system_settings_changed'])
        self.assertFalse(fix['global_language_getter_changed'])
        self.assertFalse(fix['real_wii_success_verified'])


if __name__ == '__main__': unittest.main()
