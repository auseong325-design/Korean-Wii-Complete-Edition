import unittest
from kwce.gc_card import inspect_card
from kwce.gc_fixture import raw_card

class CardInspectionTests(unittest.TestCase):
    def test_empty_and_synthetic_cards(self):
        for saved in [False,True]:
            result=inspect_card(raw_card(saved,encoding=1,mbits=128))
            self.assertEqual(len(result['entries']),int(saved))
            self.assertEqual(result['free_blocks'],2043-int(saved))

    def test_redundancy_and_corruption(self):
        data=bytearray(raw_card(True,encoding=1,mbits=128))
        data[8192]^=1
        self.assertEqual(len(inspect_card(data)['entries']),1)
        data[16384]^=1
        with self.assertRaises(ValueError):inspect_card(data)
        with self.assertRaises(ValueError):inspect_card(bytes(8192))
