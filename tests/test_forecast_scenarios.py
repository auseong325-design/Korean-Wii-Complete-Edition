import datetime,struct,unittest,zlib
from kwce.forecast_scenarios import fixture
from kwce.channels import compress_lz10,load_library


class ForecastScenarioTests(unittest.TestCase):
    def source(self,kind):
        size=216 if kind=='forecast'else 60
        data=bytearray(size);struct.pack_into('>II',data,0,0,size)
        struct.pack_into('>II',data,12,10000,10063);data[20]=136;data[24]=1
        struct.pack_into('>II',data,32 if kind=='forecast'else 28,1,88 if kind=='forecast'else 36)
        at=88 if kind=='forecast'else 36
        struct.pack_into('>II',data,at+4,10009,10000)
        struct.pack_into('>I',data,8,zlib.crc32(data[12:])&0xffffffff)
        return compress_lz10(bytes(data))

    def decode(self,payload):
        load_library();from libWiiPy.archive import decompress_lz77
        return decompress_lz77(payload)

    def test_pm_fixture_updates_both_validity_and_record_times(self):
        for kind in ('forecast','short'):
            data=self.decode(fixture(self.source(kind),kind,'clock-pm'));at=88 if kind=='forecast'else 36
            self.assertEqual(struct.unpack_from('>II',data,12),(10720,10783))
            self.assertEqual(struct.unpack_from('>II',data,at+4),(10729,10720))
            self.assertEqual(data[20],136);self.assertEqual(data[24],1)
            self.assertEqual(zlib.crc32(data[12:])&0xffffffff,struct.unpack_from('>I',data,8)[0])

    def test_no_service_fixture_covers_today_tomorrow_week_and_uv(self):
        data=self.decode(fixture(self.source('forecast'),'forecast','no-service'))
        for at in [16,18,20,22,24,44,46,48,50,52,*range(72,128,8)]:
            self.assertEqual(struct.unpack_from('>H',data,88+at)[0],65535)
        self.assertEqual(data[88+41],231);self.assertEqual(data[88+69],231)

    def test_unknown_and_corrupt_sources_are_refused(self):
        with self.assertRaises(ValueError):fixture(self.source('short'),'short','outside')
        data=bytearray(self.decode(self.source('short')));data[20]=49
        with self.assertRaises(ValueError):fixture(compress_lz10(data),'short','public')

    def test_missing_location_requires_a_unique_explicit_public_city(self):
        payload=self.source('short')
        with self.assertRaises(ValueError):fixture(payload,'short','missing-location')
        with self.assertRaises(ValueError):fixture(payload,'short','missing-location',b'NONE')
        data=self.decode(fixture(payload,'short','missing-location',bytes(4)))
        self.assertEqual(struct.unpack_from('>I',data,28)[0],0)

