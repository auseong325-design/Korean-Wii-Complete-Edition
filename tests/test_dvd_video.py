import hashlib,io,stat,struct,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from import_dvd_video import dvd_entries,validate_folder,verify_iso

class DvdVideoImportTests(unittest.TestCase):
    def archive(self,names):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w')as z:
            for name in names:z.writestr(name,b'example')
        buffer.seek(0);return zipfile.ZipFile(buffer)
    def test_nested_standard_files_are_normalized(self):
        with self.archive(['VIDEO_TS/video_ts.ifo','VIDEO_TS/video_ts.bup','VIDEO_TS/VTS_01_0.IFO','VIDEO_TS/VTS_01_1.VOB'])as z:
            self.assertEqual(set(dvd_entries(z)),{'VIDEO_TS.IFO','VIDEO_TS.BUP','VTS_01_0.IFO','VTS_01_1.VOB'})
    def test_paths_duplicates_and_non_dvd_payloads_rejected(self):
        for bad in ['../VIDEO_TS.VOB','C:/VIDEO_TS.VOB','/VIDEO_TS.VOB','extra.exe','folder/video_ts.ifo']:
            with self.subTest(entry=bad),self.archive(['VIDEO_TS.IFO','VIDEO_TS.BUP',bad])as z:
                with self.assertRaises(ValueError):dvd_entries(z)
    def test_symlink_and_missing_manager_rejected(self):
        link=zipfile.ZipInfo('VIDEO_TS.VOB');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
        for names in [[link],['VTS_01_1.VOB']]:
            with self.archive(names)as z:
                with self.assertRaises(ValueError):dvd_entries(z)
    def test_ifo_backup_and_alignment_are_checked(self):
        with tempfile.TemporaryDirectory()as temp:
            p=Path(temp);vmg=b'DVDVIDEO-VMG'+bytes(2036);vts=b'DVDVIDEO-VTS'+bytes(2036)
            for name,data in [('VIDEO_TS.IFO',vmg),('VIDEO_TS.BUP',vmg),('VTS_01_0.IFO',vts),('VTS_01_0.BUP',vts),('VTS_01_1.VOB',bytes(2048))]:(p/name).write_bytes(data)
            rows,scrambled=validate_folder(p);self.assertEqual(len(rows),5);self.assertEqual(scrambled,0)
            (p/'VIDEO_TS.BUP').write_bytes(bytes(2048))
            with self.assertRaises(ValueError):validate_folder(p)
            (p/'VIDEO_TS.BUP').write_bytes(vmg);(p/'VTS_01_1.VOB').write_bytes(bytes(2047))
            with self.assertRaises(ValueError):validate_folder(p)

    def test_iso_preserves_payload_and_detects_corruption(self):
        # Tiny generated ISO9660/UDF bridge fixture, with no user media.
        def record(name,sector,size,directory=False):
            name=name.encode('ascii');r=bytearray(33+len(name)+(len(name)%2==0))
            r[0]=len(r);struct.pack_into('<I',r,2,sector);struct.pack_into('<I',r,10,size)
            r[25]=2 if directory else 0;r[32]=len(name);r[33:33+len(name)]=name
            return r
        payload=b'DVDVIDEO-VMG'+bytes(2036);data=bytearray(44*2048)
        data[16*2048:16*2048+7]=b'\x01CD001\x01';data[17*2048+1:17*2048+6]=b'NSR02'
        root=record('\0',40,2048,True);data[16*2048+156:16*2048+156+len(root)]=root
        folder=record('VIDEO_TS',41,2048,True);data[40*2048:40*2048+len(folder)]=folder
        file=record('VIDEO_TS.IFO;1',42,len(payload));data[41*2048:41*2048+len(file)]=file
        data[42*2048:43*2048]=payload
        rows=[dict(name='VIDEO_TS.IFO',size=len(payload),sha256=hashlib.sha256(payload).hexdigest())]
        with tempfile.TemporaryDirectory()as temp:
            iso=Path(temp)/'test.iso';iso.write_bytes(data)
            self.assertEqual(verify_iso(iso,rows)['VIDEO_TS.IFO']['sha256'],rows[0]['sha256'])
            data[42*2048+99]^=1;iso.write_bytes(data)
            with self.assertRaises(ValueError):verify_iso(iso,rows)
            iso.write_bytes(data[:42*2048+10])
            with self.assertRaises(ValueError):verify_iso(iso,rows)
