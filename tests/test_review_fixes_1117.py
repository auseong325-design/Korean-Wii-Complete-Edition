"""Full-review fixes 2026-11-17: Nintendo v25, Food hardware-v22, Internet hardware-v13, Kirby TV hardware-v13,
Votes v24 (only the intended files change)."""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = {'nintendo': ('build-v21', 'build-v25', 'nintendo-ko-ui-test.wad', [5, 6, 8]),
         'food': ('hardware-v18', 'hardware-v22', 'food-ko-hardware-test.wad', [2, 4, 6]),
         'internet': ('hardware-v12', 'hardware-v13', 'internet-ko-hardware-candidate.wad', [2, 6]),
         'kirbytv': ('hardware-v11', 'hardware-v13', 'kirbytv-ko-hardware-test.wad', [2]),
         'votes': ('build-v23', 'build-v24', 'votes-ko-ui-test.wad', [1]),
         'votes26': ('build-v23', 'build-v26', 'votes-ko-ui-test.wad', [1]),
         'votes27': ('build-v26', 'build-v27', 'votes-ko-ui-test.wad', [1]),
         'votes28': ('build-v27', 'build-v28', 'votes-ko-ui-test.wad', [1])}


def contents(path):
    from kwce.channels import load_library
    t = load_library().title.Title(); t.load_wad(path.read_bytes())
    return [t.get_content_by_index(i) for i in range(len(t.tmd.content_records))]


def changed_files(a, b):
    from kwce.channels import ChannelArchive
    x, y = ChannelArchive(a), ChannelArchive(b)
    assert set(x.files) == set(y.files)
    return sorted(p for p in x.files if x.get(p) != y.get(p))


class ReviewFixes1117Tests(unittest.TestCase):
    def pair(self, channel):
        parent, child, name, changed = PAIRS[channel]
        a, b = (ROOT / f'workspace/channels/{channel.rstrip("0123456789")}/{d}/{name}' for d in (parent, child))
        if not (a.is_file() and b.is_file()): self.skipTest('builds not present')
        old, new = contents(a), contents(b)
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], changed)
        return old, new

    def test_nintendo(self):
        from kwce import review_fixes_1117 as rf
        from kwce.channel_font import font_data
        old, new = self.pair('nintendo')
        self.assertEqual(changed_files(old[5], new[5]), ['HomeButton3/Wiiware_guid_jpn.jpg', 'HomeButton3/network.csv',
                                                         'font/E/Promotion_RodinNTLGPro_DB_32_IA4.brfnt', 'font/F/Promotion_RodinNTLGPro_DB_32_IA4.brfnt',
                                                         'font/S/Promotion_RodinNTLGPro_DB_32_IA4.brfnt'])
        from kwce.channels import ChannelArchive
        c5 = ChannelArchive(new[5])
        for p in c5.files:
            if p.endswith('Promotion_RodinNTLGPro_DB_32_IA4.brfnt'):
                _, mapping, _ = font_data(c5.get(p))
                self.assertTrue(all(ord(c) in mapping for c in rf.MOVIE_PROMPT if c != ' '))
        network = c5.get('HomeButton3/network.csv')[2:].decode('utf-16-be')
        self.assertEqual(network.count(rf.QUIT_MESSAGE), 7)
        self.assertEqual(changed_files(old[8], new[8]), ['HomeButton3/LZ77_homeBtn_nwm_jpn.arc'])

    def test_food(self):
        from kwce import review_fixes_1117 as rf
        from kwce.channels import ChannelArchive
        old, new = self.pair('food')
        self.assertEqual(changed_files(old[2], new[2]), ['Dtest/Home/Demae_guide-00.jpg', 'Dtest/Home/network_nosave.csv'])
        self.assertEqual(ChannelArchive(new[2]).get('Dtest/Home/network_nosave.csv')[2:].decode('utf-16-be').count(rf.QUIT_MESSAGE), 7)
        self.assertEqual(changed_files(old[6], new[6]), ['HomeButton3/LZ77_homeBtn_nwm_jpn.arc'])

    def test_home_font_covers_quit_message(self):
        from kwce import review_fixes_1117 as rf
        from kwce.home_menu import home_font_mapping, missing_glyphs
        from kwce.channels import ChannelArchive
        for channel, index in (('nintendo', 6), ('food', 4)):
            _, new = self.pair(channel)
            arc = ChannelArchive(new[index])
            for p in arc.files:
                if '/LZ77_homeBtn' in p and 'nwm' not in p:
                    self.assertEqual(missing_glyphs([rf.QUIT_MESSAGE], home_font_mapping(arc.get(p))), [], p)

    def test_internet(self):
        from kwce import review_fixes_1117 as rf
        from kwce.channels import ChannelArchive
        old, new = self.pair('internet')
        for i in (2, 6):
            self.assertEqual(changed_files(old[i], new[i]), ['english.lng'])
            self.assertIn('-1504149836="240004: 쓸 수 없는 주소입니다."', ChannelArchive(new[i]).get('english.lng').decode('utf-8'))

    def test_kirbytv(self):
        from kwce.channels import ChannelArchive
        from kwce import kirbytv_swf as S
        old, new = self.pair('kirbytv')
        self.assertEqual(changed_files(old[2], new[2]), ['trusted/Gumball2.12.RC-1.swf'])
        data = S.unpack(ChannelArchive(new[2]).get('trusted/Gumball2.12.RC-1.swf'))[2]
        self.assertIn('커비 에피소드를 보고 나면<br/>열쇠를 받을 수도 있습니다.'.encode(), data)
        self.assertNotIn('보고 나면 </br> 열쇠를'.encode(), data)

    def test_votes(self):
        from kwce.ppc_patch import to_file
        from kwce.channel_service_fixes import VOTES_REGION_SELECT
        old, new = self.pair('votes')
        diff = sorted({i - i % 4 for i in range(len(old[1])) if old[1][i] != new[1][i]})
        self.assertEqual(diff, [to_file(old[1], VOTES_REGION_SELECT[0][0], 4)])
        at = diff[0]
        self.assertEqual(struct.unpack_from('>I', new[1], at)[0], 0x38844c4b)   # addi r4,r4,'LK' -> 00010008-HALK

    def test_votes_v26(self):
        from kwce.ppc_patch import to_file
        from kwce import channel_service_fixes as f
        old, new = self.pair('votes26')
        sites = f.VOTES_REGION_SELECT + f.VOTES_REGION_LAUNCH + f.VOTES_LAUNCH_REGION
        diff = sorted({i - i % 4 for i in range(len(old[1])) if old[1][i] != new[1][i]})
        self.assertEqual(diff, sorted(to_file(old[1], s, 4) for s, _, _ in sites))
        for s, o, n in sites:
            self.assertEqual(struct.unpack_from('>I', old[1], to_file(old[1], s, 4))[0], o)
            self.assertEqual(struct.unpack_from('>I', new[1], to_file(new[1], s, 4))[0], n)

    def test_votes_usa_japan_whole_country(self):
        from kwce.ppc_patch import to_file
        from kwce import channel_service_fixes as f
        for key, sites in (('votes27', f.VOTES_WHOLE_COUNTRY), ('votes28', f.VOTES_JAPAN)):
            old, new = self.pair(key)
            diff = sorted({i - i % 4 for i in range(len(old[1])) if old[1][i] != new[1][i]})
            self.assertEqual(diff, [to_file(old[1], s, 4) for s, _, _ in sites])
        _, v28 = self.pair('votes28')
        word = lambda va: struct.unpack_from('>I', v28[1], to_file(v28[1], va, 4))[0]
        self.assertEqual((word(0x800509c8), word(0x800509ec)), (0x38600001, 0x38600001))   # country 1, region 1


if __name__ == '__main__':
    unittest.main()
