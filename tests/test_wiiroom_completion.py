"""Resource/boot regression checks, without console data or live service IO."""
import base64,binascii,json,struct,unittest
from pathlib import Path
from xml.etree.ElementTree import fromstring
from kwce.wiiroom_guest import synthetic_mii
from kwce.wiiroom_feed import xml_response
from kwce.channels import load_library,ChannelArchive
from kwce.wiiroom_formats import decompress_lz11
from kwce.ppc_patch import to_file
from kwce.wiiroom_compat import patch_korean_area

class SyntheticGuestTests(unittest.TestCase):
    def test_avatar_is_built_from_constants_with_a_valid_crc_and_no_console_origin(self):
        a=synthetic_mii();self.assertEqual(a,synthetic_mii());self.assertEqual(len(a),76)
        self.assertEqual(binascii.crc_hqx(a,0),0)
        self.assertEqual(a[28:32],bytes(4));self.assertEqual(a[2:22].decode('utf-16-be').rstrip('\0'),'안내원')
    def test_binary_fields_use_reference_base64_without_loss(self):
        b=synthetic_mii();root=fromstring(xml_response('SpPageBin',dict(bininfo=[dict(miibin=b)])))
        self.assertEqual(base64.b64decode(root.findtext('bininfo/miibin')),b)

@unittest.skipUnless(Path('workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad').exists(),'local Room original required')
class KoreanAreaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library();t=lib.title.Title();t.load_wad(Path('workspace/channels/wiiroom/originals/wiiroom-english-wiilink-archive.wad').read_bytes());cls.raw=decompress_lz11(t.get_content_by_index(1));cls.changed,cls.record=patch_korean_area(cls.raw)
    def test_only_korean_area_maps_to_supported_slot_and_epilogue_still_restores_lr(self):
        # Execute actual assembled instructions up to the original epilogue.
        for value in list(range(13))+[0xffffffff]:
            pc=0x803087bc;regs={3:value,0:0};eq=False
            for _ in range(12):
                if pc==0x803087c0:break
                w=int.from_bytes(self.changed[to_file(self.changed,pc):to_file(self.changed,pc)+4],'big');op=w>>26;nxt=pc+4
                def signed(v,bits):return v-(1<<bits)if v&(1<<(bits-1))else v
                if op==18:nxt=pc+signed(w&0x3fffffc,26)
                elif op==11:eq=regs[3]==signed(w&65535,16)
                elif op==16:
                    self.assertEqual((w>>21)&31,12);self.assertEqual((w>>16)&31,2)
                    if eq:nxt=pc+signed(w&0xfffc,16)
                elif op==14:self.assertEqual((w>>16)&31,0);regs[3]=signed(w&65535,16)&0xffffffff
                elif op==32:self.assertEqual(w,0x80010024);regs[0]=0x81234560
                else:self.fail('Unexpected epilogue instruction')
                pc=nxt
            self.assertEqual(pc,0x803087c0);self.assertEqual(regs[0],0x81234560)
            self.assertEqual(regs[3],0 if value==6 else value)
    def test_native_filesystem_functions_and_strings_are_byte_identical(self):
        for lo,hi in [(0x80302cd0,0x80303000),(0x80304a90,0x80304b48),(0x80702d68,0x80702e64)]:
            self.assertEqual(self.raw[to_file(self.raw,lo):to_file(self.raw,hi)],self.changed[to_file(self.changed,lo):to_file(self.changed,hi)])
        allowed=set(range(to_file(self.raw,0x803087bc),to_file(self.raw,0x803087bc)+4))
        for va in (0x802cfe64,0x802d0524,0x802d1304):allowed.update(range(to_file(self.raw,va),to_file(self.raw,va)+12))
        self.assertTrue(all(i in allowed for i,(a,b)in enumerate(zip(self.raw,self.changed))if a!=b))
    def test_other_binary_refused(self):
        with self.assertRaises(ValueError):patch_korean_area(bytes(1024))

@unittest.skipUnless(Path('workspace/channels/wiiroom/build-v26/build-manifest.json').exists(),'local Korean Room assets required')
class RoomResourceTests(unittest.TestCase):
    def test_strap_all_languages_keep_art_outside_caption_boxes(self):
        from kwce import tpl
        load_library();lib=load_library();titles=[]
        for v in (24,26):
            t=lib.title.Title();t.load_wad(Path(f'workspace/channels/wiiroom/build-v{v}/wiiroom-ko-local-test.wad').read_bytes());titles.append(t)
        old=ChannelArchive(titles[0].get_content_by_index(13));new=ChannelArchive(titles[1].get_content_by_index(13))
        source=decompress_lz11(old.get('strapImage_En_LZ.bin'));reference=decompress_lz11(new.get('strapImage_En_LZ.bin'))
        for name in old.files:
            if name.startswith('strapImage_'):
                self.assertEqual(decompress_lz11(new.get(name)),reference)
            else:self.assertEqual(old.get(name),new.get(name))
        for index in (0,1):
            a,b=tpl.decode(source,index),tpl.decode(reference,index)
            self.assertEqual(a.crop((0,0,640,216)).tobytes(),b.crop((0,0,640,216)).tobytes())
            self.assertEqual(a.crop((0,216,269,356)).tobytes(),b.crop((0,216,269,356)).tobytes())
            self.assertNotEqual(a.tobytes(),b.tobytes())

@unittest.skipUnless(Path('workspace/channels/wiiroom/build-v34/build-manifest.json').exists(),'local Room labels required')
class StaticLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib=load_library()
        from libWiiPy.archive import decompress_lz77
        cls.titles=[];cls.layouts=[]
        for v in (30,34,35):
            t=lib.title.Title();t.load_wad(Path(f'workspace/channels/wiiroom/build-v{v}/wiiroom-ko-local-test.wad').read_bytes());cls.titles.append(t)
        for t in cls.titles[:2]:
            a=ChannelArchive(t.get_content_by_index(2));rows={}
            for name in a.files:
                if not(name.startswith('layout/')and name.endswith('.lex')):continue
                raw=a.get(name);raw=decompress_lz11(raw)if raw[0]==17 else decompress_lz77(raw)if raw[0]==16 else raw
                if len(raw)==98:continue
                inner=ChannelArchive(raw)
                for p in inner.files:
                    if p.endswith('.brlyt'):rows[name+'/'+p]=inner.get(p)
            cls.layouts.append(rows)
    def test_all_active_japanese_labels_replaced_while_other_sections_preserved(self):
        from kwce.channels import layout_sections,textbox
        from kwce.wiiroom_static import bounded_text,JP
        before,after=self.layouts;self.assertEqual(before.keys(),after.keys());count=0
        for key in before:
            a,b=layout_sections(before[key]),layout_sections(after[key]);self.assertEqual(len(a),len(b))
            for old,new in zip(a,b):
                if old[:4]!=b'txt1':self.assertEqual(old,new);continue
                previous,_=bounded_text(old);current,_=bounded_text(new)
                self.assertFalse(JP.search(current[1]))
                if previous[1]!=current[1]:
                    count+=1;self.assertTrue(JP.search(previous[1]));self.assertTrue(any('\uac00'<=c<='\ud7a3'for c in current[1]))
                    self.assertEqual(old[8:76],new[8:76]) # flags, pane transform, extent
                else:self.assertEqual(old,new)
        self.assertEqual(count,253)
    def test_hardware_has_same_assets_and_native_code_only_original_bootstrap_url(self):
        emu,hardware=self.titles[1:]
        for i in range(16):
            if i!=1:self.assertEqual(emu.get_content_by_index(i),hardware.get_content_by_index(i))
        a,b=(decompress_lz11(t.get_content_by_index(1))for t in (emu,hardware))
        old=b'http://prod.wiilink24.com/conf/first.bin';local=b'http://127.0.0.2/conf/first.bin'
        self.assertEqual(b.count(old+b'\0'),1);self.assertNotIn(local,b)
        self.assertEqual(a,b.replace(old,local+bytes(len(old)-len(local))))
    def test_malformed_label_cannot_escape_section(self):
        from kwce.wiiroom_static import bounded_text
        s=bytearray(128);s[:4]=b'txt1';struct.pack_into('>H',s,78,65535);struct.pack_into('>I',s,88,0xfffffffc)
        with self.assertRaises(ValueError):bounded_text(s)
    def test_dynamic_buffers_never_shrink_to_placeholder_translation_length(self):
        from kwce.channels import layout_sections
        before,after=self.layouts;larger=0
        for key in before:
            for old,new in zip(layout_sections(before[key]),layout_sections(after[key])):
                if old[:4]!=b'txt1':continue
                capacity=struct.unpack_from('>H',old,76)[0]
                self.assertGreaterEqual(struct.unpack_from('>H',new,76)[0],capacity)
                if capacity>struct.unpack_from('>H',old,78)[0]:
                    larger+=1;self.assertEqual(old[100:104],new[100:104])
        self.assertGreater(larger,50)

class GuestMediaTests(unittest.TestCase):
    def test_native_room_image_dimensions_and_binary_fields(self):
        import io
        from kwce.wiiroom_guest import add_guest_fixtures
        load_library();from PIL import Image
        saved={}
        add_guest_fixtures(lambda path,name,body:saved.update({path:body}),'2026-01-01T00:00:00Z','2030-01-01T00:00:00Z')
        for name,size in [('g1234',(184,80)),('f1234',(320,180)),('c0001',(160,120))]:
            with Image.open(io.BytesIO(saved[f'/url1/special/1/img/{name}.img']))as im:self.assertEqual(im.size,size)
        root=fromstring(saved['/url1/special/allbin.xml'])
        self.assertEqual(base64.b64decode(root.findtext('bininfo/miibin')),synthetic_mii())

if __name__=='__main__':unittest.main()
