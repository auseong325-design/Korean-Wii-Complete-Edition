import unittest
from pathlib import Path
from kwce.channels import load_library
from kwce.ppc_patch import to_file
from kwce.forecast_time import korean_time


class ForecastClockTests(unittest.TestCase):
    @unittest.skipUnless(Path('workspace/channels/forecast/originals/forecast-usa-wiilink-archive.wad').is_file(), 'local original required')
    def test_korean_clock_registration_and_unknown_source_refused(self):
        load_library()
        from libWiiPy.title import Title
        title=Title(); title.load_wad(Path('workspace/channels/forecast/originals/forecast-usa-wiilink-archive.wad').read_bytes())
        original=title.get_content_by_index(1)
        legacy,_=korean_time(original)
        fixed,record=korean_time(original,clock_language_fallback=True)
        at=to_file(original,0x8003b9d8,4)
        self.assertEqual(legacy[:at],fixed[:at]); self.assertEqual(legacy[at+4:],fixed[at+4:])
        self.assertEqual(fixed[at:at+4],bytes.fromhex('38000001'))  # li r0,1
        self.assertTrue(record['clock_language_fallback'])
        complete,_=korean_time(original,clock_language_fallback=True,clock_font_fallback=True)
        expected=bytearray(fixed)
        for va in (0x8003b4b0,0x8003b4c4):
            pos=to_file(original,va,4); expected[pos:pos+4]=bytes.fromhex('38000001')
        self.assertEqual(complete,bytes(expected))
        enabled,record=korean_time(original,clock_region_enabled=True)
        pos=to_file(original,0x8000d6f4,4)
        expected=bytearray(legacy);expected[pos:pos+4]=bytes.fromhex('9bad8c88')
        self.assertEqual(enabled,bytes(expected));self.assertTrue(record['clock_region_enabled'])
        visible,record=korean_time(original,clock_display_enabled=True)
        pos=to_file(original,0x8003d02c,4)
        expected=bytearray(legacy);expected[pos:pos+4]=bytes.fromhex('38000000')
        self.assertEqual(visible,bytes(expected));self.assertTrue(record['clock_display_enabled'])
        scoped,record=korean_time(original,clock_main_views_only=True)
        self.assertEqual(len(scoped),len(legacy));self.assertTrue(record['clock_main_views_only'])
        self.assertEqual(scoped[to_file(scoped,0x8003d02c):to_file(scoped,0x8003d02c)+4],
                         original[to_file(original,0x8003d02c):to_file(original,0x8003d02c)+4])
        ranges=[(to_file(legacy,a,b-a),b-a)for a,b in[(0x8000efa4,0x8000efa8),(0x8000f6e0,0x8000f6e4),(0x8003c8b8,0x8003c914)]]
        self.assertTrue(all(a==b or any(lo<=i<lo+size for lo,size in ranges)for i,(a,b)in enumerate(zip(legacy,scoped))))
        active,record=korean_time(original,clock_active_view_only=True)
        self.assertEqual(len(active),len(legacy));self.assertTrue(record['clock_active_view_only'])
        ranges=[(to_file(legacy,a,b-a),b-a)for a,b in[(0x8003d02c,0x8003d030),(0x8003c8b8,0x8003c914)]]
        self.assertTrue(all(a==b or any(lo<=i<lo+size for lo,size in ranges)for i,(a,b)in enumerate(zip(legacy,active))))
        wrong=bytearray(original); wrong[at]^=1
        with self.assertRaisesRegex(ValueError,'Unexpected original code'):
            korean_time(wrong,clock_language_fallback=True)
