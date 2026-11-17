import struct
import unittest
from kwce.dvd_native_loader import Region, inspect_dol, preflight


def dol(address=0x80004000):
    data = bytearray(0x120)
    for offset, value in ((0, 0x100), (0x48, address), (0x90, 0x20), (0xe0, address)):
        struct.pack_into('>I', data, offset, value)
    return data


class NativeLoaderTests(unittest.TestCase):
    def test_real_transition_requires_relocation(self):
        report = preflight(dol(), dol())
        self.assertTrue(report['static_destination_overlap'])
        self.assertFalse(report['installable'])
        self.assertFalse(report['boot_verified'])

    def test_entry_and_truncation(self):
        data = dol()
        struct.pack_into('>I', data, 0xe0, 0x80005000)
        for invalid in (data, dol()[:0x110], dol(0x1000), dol(0xfffffff0)):
            with self.assertRaises(ValueError):
                inspect_dol(invalid)

    def test_bss_cannot_erase_loader(self):
        player = dol()
        struct.pack_into('>II', player, 0xd8, 0x91000000, 0x1000)
        with self.assertRaisesRegex(ValueError, 'overlaps player'):
            preflight(player, dol(0x81300000),
                      staging=Region(0x92000000, 0x1000, 'staging'),
                      trampoline=Region(0x91000000, 0x100, 'trampoline'))

    def test_resident_broad_bss_is_reserved_without_loading(self):
        menu = dol()
        struct.pack_into('>II', menu, 0xd8, 0x80004000, 0x1000)
        with self.assertRaises(ValueError):
            inspect_dol(menu)
        report = preflight(dol(), menu)
        self.assertEqual(len(report['menu_collisions']), 2)

    def test_physical_entry_only_for_resident_reference(self):
        menu = dol()
        struct.pack_into('>I', menu, 0xe0, 0x4000)
        self.assertEqual(inspect_dol(menu, resident=True)[0], 0x80004000)
        with self.assertRaises(ValueError):
            inspect_dol(menu)

    def test_staging_and_trampoline(self):
        stage = Region(0x92000000, 0x1000, 'staging')
        report = preflight(dol(), dol(0x81300000), staging=stage,
                           trampoline=Region(0x93000000, 0x100, 'trampoline'))
        self.assertTrue(report['allocations_checked'])
        self.assertFalse(report['runtime_memory_reservation_verified'])
        for bad in (Region(stage.start, 0x100, 'overlap'),
                    Region(0x93400000, 0x100, 'IOS'),
                    Region(0x93000001, 0x100, 'unaligned')):
            with self.assertRaises(ValueError):
                preflight(dol(), dol(), staging=stage, trampoline=bad)


if __name__ == '__main__':
    unittest.main()
