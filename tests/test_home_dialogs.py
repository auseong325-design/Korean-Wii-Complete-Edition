import re,struct,unittest
from unittest.mock import patch
from kwce.home_menu import localize_dialog_csv,korean_runtime_home_messages,SAVE_WARNING
from kwce.channels import ChannelArchive,compress_lz10,load_library


class HomeDialogTests(unittest.TestCase):
    messages=['Wii 리모컨을 접속해 주세요.','접속 해제 중...','Wii 메뉴로 돌아가시겠습니까?','리셋하시겠습니까?']

    def source(self,warning=True):
        english=['Pair remotes','Disconnecting...','Return to the Wii Menu?','Reset the software?']
        if warning:
            for i in(2,3):english[i]+='\r\n(Anything not saved will be lost.)'
        rows=[]
        for i,text in enumerate(english):
            cells=[f'language-{j}-row-{i}'for j in range(7)];cells[1]=text
            rows.append(','.join('"'+s+'"'for s in cells))
        return b'\xfe\xff'+'\r\n'.join(rows).encode('utf-16-be')

    def test_only_fallback_column_changes_and_warning_survives(self):
        before=self.source();after,targets=localize_dialog_csv(before,self.messages)
        old=re.findall(r'"([^"]*)"',before[2:].decode('utf-16-be'));new=re.findall(r'"([^"]*)"',after[2:].decode('utf-16-be'))
        self.assertEqual(len(new),28)
        for i in range(28):
            if i%7!=1:self.assertEqual(old[i],new[i])
        self.assertEqual(new[15],self.messages[2]+'\r\n'+SAVE_WARNING)
        self.assertEqual(new[22],self.messages[3]+'\r\n'+SAVE_WARNING)
        self.assertEqual(new[1::7],targets)

    def test_no_save_table_stays_without_save_warning(self):
        after,_=localize_dialog_csv(self.source(False),self.messages)
        self.assertNotIn(SAVE_WARNING,after.decode('utf-16'))

    def test_every_legacy_language_slot_uses_covered_korean_text(self):
        after,targets=localize_dialog_csv(self.source(),self.messages,tuple(range(7)))
        cells=re.findall(r'"([^"]*)"',after[2:].decode('utf-16-be'))
        for row in range(4):self.assertEqual(cells[row*7:row*7+7],[targets[row]]*7)

    def test_actual_compressed_runtime_table_and_other_resources(self):
        load_library();from libWiiPy.archive import decompress_lz77
        for prefix in(b'',b'LZ77'):
            payload=prefix+compress_lz10(self.source(False))
            names=b'\0home_nosave.csv.LZ\0other.bin\0';root=32;header=36+len(names);start=(root+header+31)&~31
            data=bytearray(start);struct.pack_into('>4I',data,0,0x55aa382d,root,header,start)
            for i,node in enumerate([(0x1000000,0,3),(1,start,len(payload)),(20,start+len(payload),4)]):
                struct.pack_into('>III',data,root+i*12,*node)
            data[root+36:root+header]=names;data.extend(payload+b'KEEP')
            before=ChannelArchive(bytes(data))
            with patch('kwce.home_menu.korean_dialog_messages',return_value=self.messages):
                after,record=korean_runtime_home_messages(before)
            self.assertEqual(after.get('other.bin'),b'KEEP')
            packed=after.get('home_nosave.csv.LZ');self.assertEqual(packed.startswith(b'LZ77'),bool(prefix))
            cells=re.findall(r'"([^"]*)"',decompress_lz77(packed).decode('utf-16'))
            for row in range(4):self.assertEqual(cells[row*7:row*7+7],[self.messages[row]]*7)
            self.assertTrue(record['compression_roundtrip'])

    def test_unknown_layout_encoding_and_delimiters_refused(self):
        with self.assertRaises(ValueError):localize_dialog_csv(b'plain text',self.messages)
        with self.assertRaises(ValueError):localize_dialog_csv(self.source().replace('Return'.encode('utf-16-be'),'Cancel'.encode('utf-16-be')),self.messages)
        with self.assertRaises(ValueError):localize_dialog_csv(self.source(),['"bad',*self.messages[1:]])
        with self.assertRaises(ValueError):localize_dialog_csv(self.source(),self.messages[:3])
