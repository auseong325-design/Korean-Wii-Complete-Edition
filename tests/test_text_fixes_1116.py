"""2026-11-16 text fixes: each derived build carries its fix and the term 'Wii 게시판' is gone."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDS = {'forecast': 'build-v108', 'news': 'build-v30', 'nintendo': 'build-v19', 'food': 'hardware-v16',
          'wiiroom': 'build-v69', 'mii-contest': 'build-v33'}


def wad(channel):
    p = ROOT / f'workspace/channels/{channel}/{BUILDS[channel]}'
    return next(p.glob('*.wad'), None)


@unittest.skipUnless(all(wad(c) for c in BUILDS), 'text fix builds not present')
class TextFixTests(unittest.TestCase):
    def contents(self, channel):
        from kwce.channels import load_library
        t = load_library().title.Title(); t.load_wad(wad(channel).read_bytes())
        return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]

    def test_news_date_font_has_gan(self):
        from kwce.channels import ChannelArchive
        from libWiiPy.archive import decompress_lz77
        from kwce.channel_font import font_data
        c9 = ChannelArchive(self.contents('news')[9])
        _, mapping, _ = font_data(decompress_lz77(c9.get('font_news_date.brfnt.LZ')))
        self.assertIn(ord('간'), mapping)

    def test_board_term(self):
        old = 'Wii 게시판'.encode('utf-16-be'); new = 'Wii 알림판'.encode('utf-16-be')
        c5 = self.contents('nintendo')[5]
        self.assertNotIn(old, c5); self.assertEqual(c5.count(new), 9)

    def test_forecast_title(self):
        from kwce.text_fixes_1116 import forecast
        from kwce.channels import ChannelArchive, layout_sections, textbox
        from libWiiPy.archive import decompress_lz77
        inner = ChannelArchive(decompress_lz77(ChannelArchive(self.contents('forecast')[9]).get('weather_layout.arc.LZ')))
        texts = [e[1] for s in layout_sections(inner.get('arc/blyt/set_area1.brlyt')) if (e := textbox(s))]
        self.assertNotIn('현재 위치와 가장 가까운 지역을 선택해 주세요.', texts)
        self.assertEqual(texts.count('현재 위치와 가까운 지역을 선택해 주세요.'), 7)


if __name__ == '__main__':
    unittest.main()
