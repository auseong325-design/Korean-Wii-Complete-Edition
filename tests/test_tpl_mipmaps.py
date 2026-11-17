import struct
import unittest

from kwce.channels import load_library
from kwce.tpl import encode_mipmaps


class TplMipmapsTests(unittest.TestCase):
    def fixture(self):
        data = bytearray(352)
        struct.pack_into('>III', data, 0, 0x0020af30, 2, 12)
        struct.pack_into('>IIII', data, 12, 32, 0, 72, 0)
        struct.pack_into('>HHII', data, 32, 16, 16, 0, 128)
        data[32 + 34] = 2
        struct.pack_into('>HHII', data, 72, 8, 8, 0, 320)
        data[320:] = b'\x5a' * 32
        return bytes(data)

    def test_every_stored_level_changes_without_touching_metadata_or_neighbor(self):
        load_library()
        from PIL import Image
        source = self.fixture()
        result = encode_mipmaps(source, 0, Image.new('RGBA', (16, 16), 'white'))
        self.assertEqual(result[:128], source[:128])
        self.assertEqual(result[128:320], b'\xff' * 192)
        self.assertEqual(result[320:], source[320:])
        self.assertEqual(len(result), len(source))

    def test_chain_overlapping_next_texture_is_rejected(self):
        load_library()
        from PIL import Image
        source = bytearray(self.fixture())
        struct.pack_into('>I', source, 72 + 8, 256)
        with self.assertRaisesRegex(ValueError, 'allocation'):
            encode_mipmaps(bytes(source), 0, Image.new('RGBA', (16, 16)))


if __name__ == '__main__':
    unittest.main()
