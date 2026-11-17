"""Threat-oriented guard checks with synthetic data only; no Dolphin/network.

Uses a throwaway ignored workspace, never reads/writes the console profiles.
"""
import struct,tempfile,unittest,shutil,configparser,json,hashlib
from pathlib import Path
import launch_dolphin as launcher

class LaunchGuards(unittest.TestCase):
    def setUp(self):
        self.previous=launcher.ROOT
        self.temp=tempfile.TemporaryDirectory(dir=self.previous/'workspace/private')
        launcher.ROOT=Path(self.temp.name)
        self.wii=launcher.ROOT/'workspace/dolphin/experiment-user/Wii'
        self.wc=self.wii/'shared2/wc24';self.wc.mkdir(parents=True)
        sysdir=self.wii/'shared2/sys';sysdir.mkdir(parents=True)
        # Minimal valid synthetic entries: Korean byte, country array byte.
        a=bytes([3<<5|6])+b'IPL.LNG'+bytes([9])
        b=bytes([2<<5|7])+b'IPL.SADR'+bytes([0,136])
        self.sysconf=b'SCv0'+struct.pack('>HHH',2,10,10+len(a))+a+b
        (sysdir/'SYSCONF').write_bytes(self.sysconf)
        baseline=launcher.ROOT/'workspace/dolphin/baseline-user/Wii/shared2/wc24'
        baseline.mkdir(parents=True)
        original=bytearray(1024);original[8:16]=b'original';(baseline/'nwc24msg.cfg').write_bytes(original)
        self.cfg=bytearray(1024);struct.pack_into('>II',self.cfg,0,0x57634366,8)
        for i in range(5):
            u=f'http://127.0.0.1:9/disabled/{i}'.encode();o=156+128*i
            self.cfg[o:o+len(u)]=u
        self.save_cfg()
        self.dl=bytearray(0xf800);struct.pack_into('>II',self.dl,0,0x5763446c,1)
        (self.wc/'nwc24dl.bin').write_bytes(self.dl)

    def tearDown(self):
        launcher.ROOT=self.previous;self.temp.cleanup()

    def save_cfg(self):
        struct.pack_into('>I',self.cfg,1020,sum(struct.unpack('>255I',self.cfg[:1020]))&0xffffffff)
        (self.wc/'nwc24msg.cfg').write_bytes(self.cfg)

    def test_valid_sanitized_profile(self):
        self.assertEqual(launcher.validate(),self.wii.parent)

    def test_new_visual_profile_uses_same_guards(self):
        target=self.wii.parent.with_name('gc-visual-v1-user')
        shutil.copytree(self.wii.parent,target)
        self.assertEqual(launcher.validate('gc-visual-v1-user'),target)

    def test_baseline_or_arbitrary_profile_is_refused(self):
        for name in ['baseline-user','../private/dolphin-first-session','unknown']:
            with self.subTest(name=name),self.assertRaises(SystemExit):launcher.validate(name)

    def native_fixture(self):
        profile='gc-native-v4-user';runtime=launcher.ROOT/'workspace/sandbox/gc-v4';target=runtime/'user'
        shutil.copytree(self.wii.parent,target)
        cfg=target/'Config/Dolphin.ini';cfg.parent.mkdir();cfg.write_text('[Core]\nSlotA=1\nSlotB=1\nSerialPort1=255\nSerialPort2=255\n')
        exe=runtime/'Dolphin-x64/Dolphin.exe';exe.parent.mkdir();exe.write_bytes(b'synthetic-dolphin')
        locks=launcher.ROOT/'configs';locks.mkdir();(locks/'dolphin.lock.json').write_text(json.dumps(dict(executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())))
        helper=launcher.ROOT/'tools/gc-sandbox/bin';helper.mkdir(parents=True)
        p=helper/'AppContainerRunner.exe';p.write_bytes(b'synthetic-runner')
        probe=runtime/'NetProbe.exe';probe.write_bytes(b'synthetic-probe')
        (helper/'helper-build.json').write_text(json.dumps(dict(files=[dict(path=p.relative_to(launcher.ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest())],probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest())))
        return profile,cfg,runtime

    def test_native_profile_mapping_and_compiled_runtime_guard(self):
        profile,cfg,runtime=self.native_fixture()
        self.assertEqual(launcher.validate(profile),runtime/'user')
        self.assertEqual(launcher.validate_native_runtime(profile),runtime)
        (runtime/'Dolphin-x64/Dolphin.exe').write_bytes(b'changed')
        with self.assertRaises(SystemExit):launcher.validate_native_runtime(profile)

    def test_native_outside_card_path_refused(self):
        profile,cfg,runtime=self.native_fixture()
        with cfg.open('a') as f:f.write('MemcardAPath='+str(launcher.ROOT/'workspace/dolphin/baseline-user/GC/card.raw')+'\n')
        with self.assertRaises(SystemExit):launcher.validate_native_runtime(profile)

    def test_native_network_device_and_SD_refused(self):
        profile,cfg,runtime=self.native_fixture();original=cfg.read_text()
        for key,value in [('SerialPort1','5'),('WiiSDCard','True')]:
            cfg.write_text(original.replace('SerialPort1=255','SerialPort1='+value) if key=='SerialPort1' else original+key+'='+value+'\n')
            with self.subTest(key=key),self.assertRaises(SystemExit):launcher.validate_native_runtime(profile)

    def test_native_arbitrary_disc_and_modified_helper_refused(self):
        profile,cfg,runtime=self.native_fixture();original=cfg.read_text()
        cfg.write_text(original+'DefaultISO='+str(launcher.ROOT/'sd/arbitrary.iso')+'\n')
        with self.assertRaises(SystemExit):launcher.validate_native_runtime(profile)
        cfg.write_text(original);(launcher.ROOT/'tools/gc-sandbox/bin/AppContainerRunner.exe').write_bytes(b'changed')
        with self.assertRaises(SystemExit):launcher.validate_native_runtime(profile)

    def test_authentic_key_container_is_refused(self):
        (self.wii/'keys.bin').write_bytes(b'synthetic-test-no-real-key')
        with self.assertRaises(SystemExit):launcher.validate()

    def test_registered_state_is_refused(self):
        struct.pack_into('>I',self.cfg,20,2);self.save_cfg()
        with self.assertRaises(SystemExit):launcher.validate()

    def test_changed_korean_language_is_refused(self):
        b=bytearray(self.sysconf);b[18]=1
        (self.wii/'shared2/sys/SYSCONF').write_bytes(b)
        with self.assertRaises(SystemExit):launcher.validate()

    def test_invalid_config_checksum_is_refused(self):
        self.cfg[1023]^=1;(self.wc/'nwc24msg.cfg').write_bytes(self.cfg)
        with self.assertRaises(SystemExit):launcher.validate()

    def test_mail_password_is_refused(self):
        self.cfg[88]=1;self.save_cfg()
        with self.assertRaises(SystemExit):launcher.validate()

    def test_original_console_mail_id_is_refused(self):
        self.cfg[8:16]=b'original';self.save_cfg()
        with self.assertRaises(SystemExit):launcher.validate()

    def test_nonloopback_mail_destination_is_refused(self):
        u=b'http://192.0.2.1/example';self.cfg[156:284]=u+bytes(128-len(u));self.save_cfg()
        with self.assertRaises(SystemExit):launcher.validate()

    def test_external_download_task_is_refused_then_scrubbed(self):
        off=2048;struct.pack_into('>I',self.dl,off+12,1)
        u=b'http://192.0.2.1/example';self.dl[off+180:off+416]=u+bytes(236-len(u))
        (self.wc/'nwc24dl.bin').write_bytes(self.dl)
        with self.assertRaises(SystemExit):launcher.validate()
        launcher.scrub_download_tasks()
        self.assertEqual(launcher.validate(),self.wii.parent)

    def test_client_certificate_is_refused(self):
        (self.wii/'clientca.pem').write_bytes(b'synthetic-test-no-real-certificate')
        with self.assertRaises(SystemExit):launcher.validate()

if __name__=='__main__':unittest.main()
