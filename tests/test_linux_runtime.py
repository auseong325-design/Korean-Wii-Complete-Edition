"""Synthetic-only guard tests; no console files, Dolphin UI or host settings."""
import json
from pathlib import Path
import struct
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from kwce import linux_runtime as rt
from kwce.toolchain import tool


class LinuxGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'workspace/linux'
        self.folder = self.base / 'menu-v1'
        self.user = self.folder / 'user'
        (self.user / 'Config').mkdir(parents=True)
        rt.sanitize(self.user)
        setting = 'title/00000001/00000002/data/setting.txt'
        path = self.user / 'Wii' / setting
        path.parent.mkdir(parents=True)
        path.write_bytes(b'synthetic-region-fixture')
        (self.folder / 'profile.json').write_text(json.dumps({'source': 'menu',
            'title': '0000000100000002', 'content_manifest': {},
            'locale_hashes': {setting: rt.digest(path)}}))
        original = self.root / 'workspace/dolphin/baseline-user/Wii/shared2/wc24/nwc24msg.cfg'
        original.parent.mkdir(parents=True)
        raw = bytearray(1024)
        raw[8:16] = b'fixture!'
        original.write_bytes(raw)
        self.exe = self.root / 'tools/linux/test/bin/dolphin-emu'
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b'synthetic executable fixture')
        self.lock = self.root / 'linux.lock.json'
        self.lock.write_text(json.dumps({'prefix': 'tools/linux/test',
            'executable': 'tools/linux/test/bin/dolphin-emu', 'executable_sha256': rt.digest(self.exe)}))
        sys.path.insert(0, str(rt.ROOT / 'scripts'))
        import launch_dolphin
        for target, value in [('ROOT', self.root), ('BASE', self.base), ('LOCK', self.lock)]:
            context = patch.object(rt, target, value)
            context.start()
            self.addCleanup(context.stop)
        for context in (patch.object(rt, 'sources', return_value={'menu': ('', '0000000100000002')}),
                        patch.object(launch_dolphin, 'korean_locale', return_value=True)):
            context.start()
            self.addCleanup(context.stop)

    def modify_cfg(self, edit):
        p = self.user / 'Wii/shared2/wc24/nwc24msg.cfg'
        b = bytearray(p.read_bytes())
        edit(b)
        struct.pack_into('>I', b, 1020, sum(struct.unpack('>255I', b[:1020])) & 0xffffffff)
        p.write_bytes(b)

    def test_valid_synthetic_profile(self):
        self.assertEqual(rt.validate('menu-v1')[2], self.exe)

    def test_virtual_sd_requires_pinned_local_image_and_forbids_writes(self):
        c = self.user / 'Config/Dolphin.ini'
        c.write_text(c.read_text().replace('WiiSDCard = False','WiiSDCard = True')+
                     'WiiSDCardPath = /profile/user/Wii/sd.raw\n')
        with self.assertRaisesRegex(ValueError,'SD passthrough'):
            rt.validate('menu-v1')
        image = self.user / 'Wii/sd.raw'
        with image.open('wb') as f:
            f.truncate(64*1024*1024)
        p = self.folder / 'profile.json'
        meta = json.loads(p.read_text())
        meta['virtual_sd']={'relative_path':'Wii/sd.raw','read_only':True,'sha256':rt.digest(image)}
        p.write_text(json.dumps(meta))
        rt.validate('menu-v1')
        c.write_text(c.read_text().replace('WiiSDCardAllowWrites = False','WiiSDCardAllowWrites = True'))
        with self.assertRaisesRegex(ValueError,'SD passthrough'):
            rt.validate('menu-v1')
        c.write_text(c.read_text().replace('WiiSDCardAllowWrites = True','WiiSDCardAllowWrites = False'))
        with image.open('r+b') as f:
            f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'image differs'):
            rt.validate('menu-v1')

    def test_unsafe_alias_and_symlink_refused(self):
        for alias in ('../menu-v1', '/tmp/menu-v1', 'menu', 'menu-v0'):
            with self.assertRaises(ValueError):
                rt.runtime(alias)
        (self.user / 'escape').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'Indirect'):
            rt.validate('menu-v1')

    def test_authentic_id_or_registered_stage_refused(self):
        self.modify_cfg(lambda b: b.__setitem__(slice(8,16), b'fixture!'))
        with self.assertRaisesRegex(ValueError, 'Authentic'):
            rt.validate('menu-v1')
        self.modify_cfg(lambda b: (b.__setitem__(slice(8,16), bytes(8)),
                                  b.__setitem__(slice(20,24), (2).to_bytes(4,'big'))))
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            rt.validate('menu-v1')

    def test_remote_destination_and_credentials_refused(self):
        self.modify_cfg(lambda b: b.__setitem__(slice(163,172), b'192.0.2.1'))
        with self.assertRaisesRegex(ValueError, 'Non-local'):
            rt.validate('menu-v1')
        rt.sanitize(self.user)
        self.modify_cfg(lambda b: b.__setitem__(88, 1))
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            rt.validate('menu-v1')

    def test_keys_and_outside_paths_refused(self):
        (self.user / 'Wii/keys.bin').write_bytes(b'fixture')
        with self.assertRaisesRegex(ValueError, 'Keys'):
            rt.validate('menu-v1')
        (self.user / 'Wii/keys.bin').unlink()
        p = self.user / 'Config/Dolphin.ini'
        p.write_text(p.read_text() + '\n[General]\nNANDRoot = /home/personal\n')
        with self.assertRaisesRegex(ValueError, 'Outside'):
            rt.validate('menu-v1')

    def test_added_title_content_refused(self):
        p = self.user / 'Wii/title/00000001/00000002/content/fixture.app'
        p.parent.mkdir(parents=True)
        p.write_bytes(b'changed installed content fixture')
        with self.assertRaisesRegex(ValueError, 'contents differ'):
            rt.validate('menu-v1')

    def test_check_does_not_scrub_and_bad_executable_never_mutates_tasks(self):
        p = self.user / 'Wii/shared2/wc24/nwc24dl.bin'
        raw = bytearray(p.read_bytes());raw[2060] = 1;p.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'scrubbing'):
            rt.validate('menu-v1')
        self.assertEqual(p.read_bytes(), raw)
        self.exe.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            rt.validate('menu-v1', scrub_tasks=True)
        self.assertEqual(p.read_bytes(), raw)

    def test_running_profile_never_scrubbed(self):
        p = self.user / 'Wii/shared2/wc24/nwc24dl.bin'
        raw = bytearray(p.read_bytes());raw[2060] = 1;p.write_bytes(raw)
        with patch.object(rt, 'stopped', side_effect=ValueError('Close Dolphin')):
            with self.assertRaisesRegex(ValueError, 'Close Dolphin'):
                rt.validate('menu-v1', scrub_tasks=True)
        self.assertEqual(p.read_bytes(), raw)

    def test_host_tool_suffix_preserved_on_windows(self):
        with patch('sys.platform', 'win32'):
            self.assertEqual(tool('powerpc-eabi-as.exe').name, 'powerpc-eabi-as.exe')
        with patch('sys.platform', 'linux'):
            self.assertEqual(tool('powerpc-eabi-as.exe').name, 'powerpc-eabi-as')

    def test_no_unisolated_fallback(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'unisolated'):
                rt.sandbox(self.folder, '/bin/true', [], gui=False)

    def test_new_revisions_preserve_source_and_existing_profile(self):
        src = self.root / 'workspace/sandbox/fixture/user'
        shutil.copytree(self.user, src)
        sysconf = src / 'Wii/shared2/sys/SYSCONF'
        sysconf.parent.mkdir(parents=True, exist_ok=True)
        sysconf.write_bytes(b'synthetic locale fixture')
        (src / 'Wii/keys.bin').write_bytes(b'omit synthetic key fixture')
        (src / 'Wii/cdb.vff').write_bytes(b'omit copied message-board cache')
        def snapshot(base):
            return {p.relative_to(base).as_posix(): (rt.digest(p), p.stat().st_mtime_ns)
                    for p in base.rglob('*') if p.is_file()}
        before_src, before_old = snapshot(src), snapshot(self.folder)
        with patch.object(rt, 'sources', return_value={'menu': ('workspace/sandbox/fixture/user', '0000000100000002')}):
            with patch.object(rt, 'stopped'):
                self.assertEqual(rt.prepare('menu'), 'menu-v2')
                self.assertEqual(rt.prepare('menu'), 'menu-v3')
                with self.assertRaises(FileExistsError):
                    rt.prepare('menu', target_name='menu-v1')
        self.assertEqual(snapshot(src), before_src)
        self.assertEqual(snapshot(self.folder), before_old)
        self.assertFalse((self.base / 'menu-v2/user/Wii/keys.bin').exists())
        self.assertFalse((self.base / 'menu-v2/user/Wii/cdb.vff').exists())

    def test_mount_policy_never_exposes_sd_or_host_home(self):
        with patch('shutil.which', return_value='/usr/bin/bwrap'):
            cmd = rt.sandbox(self.folder, '/usr/bin/true', [], gui=False)
        self.assertIn('--unshare-all', cmd)
        self.assertEqual(cmd[cmd.index('--cap-drop')+1], 'ALL')
        self.assertNotIn(str(self.root / 'sd'), cmd)
        self.assertNotIn(str(Path.home()), cmd)
        self.assertEqual(cmd.count('--bind'), 1)
        self.assertEqual(cmd[cmd.index('--bind')+1], str(self.folder))


if __name__ == '__main__':
    unittest.main()
