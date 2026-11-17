import unittest
from pathlib import Path
from kwce.channels import load_library,ChannelArchive,layout_sections,textbox


class ForecastTextReviewTests(unittest.TestCase):
    @unittest.skipUnless(Path('workspace/channels/forecast/build-v39/forecast-ko-personal-test.wad').is_file(),'local diagnostic required')
    def test_native_style_is_preserved_and_production_code_unchanged(self):
        lib=load_library();from libWiiPy.archive import decompress_lz77
        original,review=lib.title.Title(),lib.title.Title()
        original.load_wad(Path('workspace/channels/forecast/build-v30/forecast-ko-personal-test.wad').read_bytes())
        review.load_wad(Path('workspace/channels/forecast/build-v39/forecast-ko-personal-test.wad').read_bytes())
        for i in range(12):
            if i!=9:self.assertEqual(original.get_content_by_index(i),review.get_content_by_index(i))
        def layout(title):
            archive=ChannelArchive(title.get_content_by_index(9))
            layouts=ChannelArchive(decompress_lz77(archive.get('weather_layout.arc.LZ')))
            path=next(n for n in layouts.files if Path(n).stem=='error0')
            return layout_sections(layouts.get(path))
        before,after=layout(original),layout(review)
        source=next(s for s in before if textbox(s)and textbox(s)[0]=='textTUS0')
        target=next(s for s in after if textbox(s)and textbox(s)[0]=='textTUS5')
        self.assertEqual(source[:12],target[:12]);self.assertEqual(source[28:],target[28:])

    @unittest.skipUnless(Path('workspace/channels/forecast/build-v76/forecast-ko-personal-test.wad').is_file(),'local current-style diagnostic required')
    def test_original_font_material_is_copied_across_layouts(self):
        import struct
        lib=load_library();from libWiiPy.archive import decompress_lz77
        source,review=lib.title.Title(),lib.title.Title()
        source.load_wad(Path('workspace/channels/forecast/build-v61/forecast-ko-personal-test.wad').read_bytes())
        review.load_wad(Path('workspace/channels/forecast/build-v76/forecast-ko-personal-test.wad').read_bytes())
        def style(title,stem,pane):
            archive=ChannelArchive(title.get_content_by_index(9));layouts=ChannelArchive(decompress_lz77(archive.get('weather_layout.arc.LZ')))
            path=next(n for n in layouts.files if Path(n).stem==stem);sections=layout_sections(layouts.get(path))
            text=next(s for s in sections if textbox(s)and textbox(s)[0]==pane)
            mat=next(s for s in sections if s[:4]==b'mat1');count=int.from_bytes(mat[8:10],'big')
            offsets=list(struct.unpack_from('>'+str(count)+'I',mat,12))+[len(mat)];index=int.from_bytes(text[80:82],'big')
            return text,mat[offsets[index]:offsets[index+1]]
        before,material=style(source,'error4','textTUS1');after,copied=style(review,'error0','textTUS5')
        self.assertEqual(material,copied)
        self.assertEqual(before[:12],after[:12]);self.assertEqual(before[28:80],after[28:80]);self.assertEqual(before[82:],after[82:])
