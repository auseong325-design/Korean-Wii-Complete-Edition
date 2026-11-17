import importlib.util,json,struct,sys,unittest
from pathlib import Path
from kwce.wii_mail import MailConfig,MailReplay,WIILINK_URLS,checksum,korean_message,parse_cgi,synthetic_config,validate_synthetic_message

class MailTests(unittest.TestCase):
    def test_endpoint_patch_preserves_identity_credentials_flags(self):
        source=synthetic_config();raw=bytearray(source.raw);raw[16:24]=struct.pack('>II',3,2);raw[88:156]=bytes(range(68));raw[1016:1020]=b'flag';struct.pack_into('>I',raw,1020,checksum(raw))
        before=MailConfig(bytes(raw));after=before.with_endpoints(WIILINK_URLS)
        self.assertEqual(before.raw[:156],after.raw[:156]);self.assertEqual(before.raw[796:1020],after.raw[796:1020]);self.assertTrue(after.summary()['wiilink_endpoints'])
    def test_invalid_config_checksum_and_oversize_url_rejected(self):
        source=synthetic_config();raw=bytearray(source.raw);raw[900]^=1
        with self.assertRaises(ValueError):MailConfig(bytes(raw))
        for urls in[(WIILINK_URLS[0],),('http://a/'+'x'*128,)*5,('http://user:password@localhost/',)*5]:
            with self.assertRaises(ValueError):source.with_endpoints(urls)
    def test_korean_mime_roundtrip(self):
        raw=korean_message('한글 제목','한글 본문\n둘째 줄');self.assertEqual(validate_synthetic_message(raw),('한글 제목','한글 본문\r\n둘째 줄\r\n'))
        with self.assertRaises(ValueError):validate_synthetic_message(raw.replace(b'@kwce.invalid',b'@example.com',1))
    def test_challenge_and_auth_are_verified(self):
        replay=MailReplay();fields=replay.credentials();response=replay.check(dict(mlchkid=fields['mlchkid'],chlng='10'))
        self.assertTrue(replay.verify_check('10',response));self.assertFalse(replay.verify_check('11',response));self.assertEqual(parse_cgi(replay.check(dict(mlchkid='wrong',chlng='10')))['cd'],'321')
    def test_delete_requires_delivery_and_correct_count(self):
        replay=MailReplay();creds=replay.credentials();replay.seed(korean_message('시험','본문'))
        self.assertEqual(parse_cgi(replay.delete(dict(creds,delnum=1)))['cd'],'340')
        replay.receive(dict(creds,maxsize=200000));self.assertEqual(parse_cgi(replay.delete(dict(creds,delnum=2)))['cd'],'340')
        self.assertEqual(parse_cgi(replay.delete(dict(creds,delnum=1)))['deletenum'],'1');self.assertEqual(replay.summary()['queued'],0)
    def test_http_protocol_roundtrip(self):
        sys.path.insert(0,str(Path('scripts').resolve()));from check_wii_mail import roundtrip
        self.assertTrue(roundtrip()['synthetic_send_verified'])
    def test_preview_has_no_registration_and_config_write_symbols(self):
        import subprocess
        base=Path('workspace/hardware/mail-candidate-v3')
        if not base.exists():self.skipTest('private mail preview required')
        nm=Path('tools/devkitpro-root/opt/devkitpro/devkitPPC/bin/powerpc-eabi-nm.exe')
        symbols=subprocess.check_output([str(nm),'-C','--defined-only',str(base/'preview.elf')],text=True)
        self.assertNotIn('Patcher()',symbols);self.assertNotIn('NWC24Config::WriteConfig()',symbols)
