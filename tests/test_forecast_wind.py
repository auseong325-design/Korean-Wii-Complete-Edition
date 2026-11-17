import unittest
from kwce.forecast_wind import korean_wind,DIRECTIONS,OFFSETS,CALM,SOURCE


class WindTest(unittest.TestCase):
    def source(self):
        data=bytearray(OFFSETS[-1]+len(SOURCE)+40)
        for at in OFFSETS:data[at:at+len(SOURCE)]=SOURCE
        data[CALM:CALM+10]='Calm\0'.encode('utf-16-be')
        return bytes(data)

    def test_all_compass_labels_and_fixed_bounds(self):
        before=self.source();after,record=korean_wind(before)
        expected=['북북동','북동','동북동','동','동남동','남동','남남동','남','남남서','남서','서남서','서','서북서','북서','북북서','북']
        self.assertEqual(len(before),len(after));self.assertEqual(record['directions_per_table'],16)
        for at in OFFSETS:
            labels=[after[at+8*i:at+8*(i+1)].decode('utf-16-be').rstrip('\0')for i in range(16)]
            self.assertEqual(labels,expected)
        self.assertEqual(after[CALM:CALM+10].decode('utf-16-be').rstrip('\0'),'무풍')
        allowed=set(range(CALM,CALM+8))|{j for at in OFFSETS for j in range(at,at+len(SOURCE))}
        self.assertTrue(all(a==b or i in allowed for i,(a,b)in enumerate(zip(before,after))))

    def test_unknown_or_already_localized_source_refused(self):
        before=bytearray(self.source());before[OFFSETS[0]]^=1
        with self.assertRaises(ValueError):korean_wind(before)
        localized,_=korean_wind(self.source())
        with self.assertRaises(ValueError):korean_wind(localized)

    def test_calm_guard(self):
        before=bytearray(self.source());before[CALM]^=1
        with self.assertRaises(ValueError):korean_wind(before)
