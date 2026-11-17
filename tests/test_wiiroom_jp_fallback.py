"""v54/v55: JP list-font fallback, TMD region 4, FONT-heap bound, hardware candidate."""
import json, struct, unittest
from pathlib import Path

from kwce.channels import load_library, ChannelArchive, sha256
from kwce.channel_font import font_data
from kwce.photoprints_font import find_glyph
from kwce.hardware import local_reference_counts
from kwce import wiiroom_jp_fallback as JF

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'workspace/channels/wiiroom'
HEAP = 0x46c650


def content9(wad):
    t = load_library().title.Title(); t.load_wad(Path(wad).read_bytes())
    return t


# Representative kanji from news / program-list vocabulary.
SAMPLE = [0x65e5, 0x672c, 0x8a9e, 0x9031, 0x756a, 0x7d44, 0x60c5, 0x5831, 0x6620, 0x753b]


class JpFallbackTests(unittest.TestCase):
    def test_builds_region4_and_targets(self):
        for v, target in ((54, 'dolphin-local-replay'), (55, 'hardware')):
            meta = json.loads((BASE / f'build-v{v}/build-manifest.json').read_text())
            self.assertEqual(meta['target'], target)
            t = content9(BASE / f'build-v{v}/wiiroom-ko-local-test.wad')
            self.assertEqual(t.tmd.region, 4)
            self.assertEqual(t.tmd.title_id, '000100014843494a')
            self.assertEqual(sha256(t.dump_wad()), meta['wad_sha256'])
            self.assertIn('jp_list_fallback', meta)

    def test_fallback_coverage_and_heap(self):
        for v in (54, 55):
            meta = json.loads((BASE / f'build-v{v}/build-manifest.json').read_text())
            arc = ChannelArchive(content9(BASE / f'build-v{v}/wiiroom-ko-local-test.wad').get_content_by_index(9))
            base50 = ChannelArchive(content9(BASE / 'build-v50/wiiroom-ko-local-test.wad').get_content_by_index(9))
            for name in ('wbf1.brfna', 'wbf2.brfna'):
                rec = meta['jp_list_fallback']['fonts'][name]
                self.assertEqual(rec['dropped'], 0)
                self.assertGreaterEqual(rec['added_glyphs'], 2900)
                self.assertLessEqual(rec['require_estimate'], HEAP)
                self.assertLessEqual(rec['sheets_after'], JF.SAFE_SHEETS)
                nf = arc.get(name); of = base50.get(name)
                for c in SAMPLE:                       # kanji now render
                    self.assertIsNotNone(find_glyph(nf, c), f'{name} missing {c:#x}')
                _, om, _ = font_data(b'RFNT' + of[4:])
                for c in list(om)[::53]:               # every original glyph unchanged
                    self.assertEqual(find_glyph(nf, c), find_glyph(of, c))

    def test_cmap_cannot_shadow_hangul(self):
        arc = ChannelArchive(content9(BASE / 'build-v54/wiiroom-ko-local-test.wad').get_content_by_index(9))
        for name in ('wbf1.brfna', 'wbf2.brfna'):
            nf = arc.get(name)
            for c in (0xac00, 0xb155, 0xd7a3):          # Hangul still resolves
                self.assertIsNotNone(find_glyph(nf, c))

    def test_hardware_candidate_region4_fakesigned(self):
        cand = sorted(ROOT.glob('workspace/hardware/wiiroom-candidate-v*/candidate-manifest.json'),
                      key=lambda p: int(p.parent.name.rsplit('-v', 1)[1]))[-1]
        m = json.loads(cand.read_text())
        self.assertEqual(m['revision'], 55)
        wad = cand.parent / 'wiiroom-ko-personal-fakesigned.wad'
        t = content9(wad)
        self.assertEqual(t.tmd.region, 4)
        self.assertTrue(t.get_is_fakesigned())
        o = content9(BASE / 'originals/wiiroom-english-wiilink-archive.wad')
        self.assertEqual(local_reference_counts(t), local_reference_counts(o))


if __name__ == '__main__':
    unittest.main()
