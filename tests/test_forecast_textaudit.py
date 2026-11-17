"""Local text-coverage guarantees for the Forecast channel (build-v103), no Dolphin.

Proves every supply string in the real 136 download is localized by forecast_mapping (so no English
weather/UV/place text on the emulator), that the full weather-condition and UV-level vocabularies are
mapped (so a condition not in today's feed would still render Korean), and that every mapped glyph
exists in the build-v103 fonts.  The dropped in-channel conversion (v104/v105) is NOT reintroduced:
this only reads the mapping and the real payload.  On-screen behaviour is a lead check.
"""
import unittest

from kwce import forecast_textaudit as fa
from kwce.forecast_data import forecast_mapping

# AccuWeather condition set the Forecast Channel can display, and the five UV levels.
CONDITIONS = ['Sunny', 'Mostly Sunny', 'Partly Cloudy', 'Intermittent Clouds', 'Haze',
              'Mostly Cloudy', 'Cloudy', 'Fog', 'Showers', 'Thunderstorms', 'Rain', 'Snow',
              'Sleet', 'Freezing Rain', 'Rain and Snow', 'Clear', 'Mostly Clear']
UV_LEVELS = ['Low', 'Moderate', 'High', 'Very High', 'Extreme']


class ForecastTextAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.supply = fa.supply_coverage()
        cls.glyphs = fa.glyph_coverage()
        cls.status = fa.channel_text_status()
        cls.mapping = forecast_mapping()

    def test_real_136_feed_fully_covered(self):
        self.assertIn(136, self.supply)
        self.assertEqual(self.supply[136]['uncovered'], [])
        self.assertEqual(self.supply[136]['covered'], self.supply[136]['unique'])

    def test_all_weather_conditions_mapped(self):
        missing = [c for c in CONDITIONS if c not in self.mapping]
        self.assertEqual(missing, [], f'unmapped conditions {missing}')

    def test_all_uv_levels_mapped(self):
        missing = [u for u in UV_LEVELS if u not in self.mapping]
        self.assertEqual(missing, [], f'unmapped UV levels {missing}')

    def test_no_missing_glyphs(self):
        self.assertEqual(self.glyphs['gaps'], {})

    def test_channel_resources_fully_localized(self):
        self.assertEqual(self.status['remaining_english_panes'], 0)
        self.assertEqual(self.status['native_error_text_styles'], 22)

    def test_audit_is_deterministic(self):
        again = fa.supply_coverage()
        self.assertEqual(again[136]['uncovered'], self.supply[136]['uncovered'])


if __name__ == '__main__':
    unittest.main()
