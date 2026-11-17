"""Create isolated, explicitly local-only channel access experiments.

The localized releases and their installed NANDs remain untouched. URL changes
are confined to new personal test WADs; no request is forwarded off the machine.
"""
import configparser
import json
import re
import shutil
import subprocess
import sys
from audit_sd import ROOT, sha256
from prepare_votes_local_settings import records
import launch_dolphin as launcher
sys.path.insert(0, str(ROOT))
from kwce.channels import load_library

CHANNELS = {
    'votes': (10, '0001000148414a45', 'HAJE'),
    'nintendo': (2, '0001000148415445', 'HATE'),
    'mii-contest': (7, '0001000148415045', 'HAPE'),
}


def stopped():
    # Read bytes, not text: on a Korean-locale host tasklist prints its "no tasks" line in cp949,
    # and a detached process (no UTF-8 console) would crash a text=True decode. The ASCII image
    # name check is encoding-independent.
    output = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Dolphin.exe', '/FO', 'CSV', '/NH'], capture_output=True).stdout or b''
    if b'dolphin.exe' in output.lower():
        raise SystemExit('Close Dolphin before preparing or checking a profile')


def register(channel):
    profile = channel + '-test-v1-user'
    launcher.NATIVE_PROFILES[profile] = 'workspace/sandbox/' + channel + '-test-v1'
    if profile not in launcher.PROFILES:
        launcher.PROFILES = (*launcher.PROFILES, profile)
    return profile


def main():
    stopped()
    lib = load_library()
    for channel, (revision, title_id, game_id) in CHANNELS.items():
        target = ROOT / f'workspace/sandbox/{channel}-test-v1'
        if target.exists():
            raise SystemExit('Existing experiment preserved: ' + channel)
        source = ROOT / f'workspace/sandbox/{channel}-v1'
        out = ROOT / f'workspace/channels/{channel}/access-build-v1'
        if out.exists():
            raise SystemExit('Existing access WAD preserved')
        wad = ROOT / f'workspace/channels/{channel}/build-v{revision}/{channel}-ko-ui-test.wad'
        metadata = json.loads(wad.with_name('build-manifest.json').read_text())
        if sha256(wad) != metadata['wad_sha256']:
            raise ValueError('Localized input hash differs')
        title = lib.title.Title(); title.load_wad(wad.read_bytes())
        before = title.get_content_by_index(1)
        changed = 0
        def local_url(match):
            nonlocal changed
            old = match.group(0)
            if not old.startswith(b'http://'):
                return old
            new = re.sub(rb'http://[^/\x00]+', b'http://127.0.0.2', old, count=1)
            if len(new) > len(old):
                raise ValueError('Local URL exceeds original string capacity')
            changed += new != old
            return new + bytes(len(old) - len(new))
        updated = re.sub(rb'https?://[^\x00\s]+', local_url, before)
        if not changed or len(updated) != len(before):
            raise ValueError('Expected fixed-size HTTP endpoint replacements')
        title.set_content(updated, 1)
        out.mkdir(parents=True)
        test_wad = out / f'{channel}-local-test.wad'
        test_wad.write_bytes(title.dump_wad())
        # Copies are made only while all emulators are stopped.
        for folder in ['user', 'Dolphin-x64']:
            shutil.copytree(source / folder, target / folder,
                            ignore=shutil.ignore_patterns('Logs', 'ScreenShots', 'Cache', 'StateSaves'))
        shutil.copy2(source / 'NetProbe.exe', target / 'NetProbe.exe')
        user = target / 'user'
        ini = user / 'Config/Dolphin.ini'
        cfg = configparser.ConfigParser(strict=False); cfg.optionxform = str
        cfg.read(ini, encoding='utf-8-sig')
        for section in cfg.sections():
            for key, value in list(cfg[section].items()):
                cfg[section][key] = value.replace(str(source), str(target))
        cfg['Core']['DefaultISO'] = ''; cfg['Core']['EnableWiiLink'] = 'False'
        cfg['Core']['OverrideRegionSettings'] = 'True'
        with ini.open('w', encoding='utf-8') as stream: cfg.write(stream)
        controls = user / 'Config/WiimoteNew.ini'
        control = controls.read_text(encoding='utf-8-sig')
        control = re.sub(r'^Buttons/Home\s*=.*$', 'Buttons/Home = RETURN | `Click 2`', control, flags=re.M)
        controls.write_text(control, encoding='utf-8')
        # Only the three non-identity standby settings and synthetic wired config.
        reference = ROOT / 'workspace/sandbox/news-v1/user/Wii'
        path = user / 'Wii/shared2/sys/SYSCONF'
        data = bytearray(path.read_bytes()); ref = (reference / 'shared2/sys/SYSCONF').read_bytes()
        a, b = records(data), records(ref)
        for key in ['IPL.INC', 'NET.WCFG', 'IPL.IDL']:
            start, end, kind = a[key]; left, right, other = b[key]
            if (end-start, kind) != (right-left, other): raise ValueError('Setting type differs')
            data[start:end] = ref[left:right]
        path.write_bytes(data)
        shutil.copy2(reference / 'shared2/sys/net/02/config.dat', user / 'Wii/shared2/sys/net/02/config.dat')
        lib.nand.EmuNAND(user / 'Wii').install_title(title)
        profile = register(channel)
        launcher.scrub_download_tasks(profile); launcher.validate(profile)
        feed = target / 'local-feed'; feed.mkdir()
        (feed / 'routes.tsv').write_text('', encoding='ascii')
        manifest = dict(channel=channel, profile=profile, title_id=title_id,
                        source_revision=revision, source_wad_sha256=sha256(wad),
                        wad_sha256=sha256(test_wad), http_strings_changed=changed,
                        changed_contents=[1], local_simulation=True,
                        external_network_allowed=False, full_localization_complete=False)
        (out / 'build-manifest.json').write_text(json.dumps(manifest, indent=2))
        print(f'Prepared {channel}: separate profile, fixed-size local endpoints, {changed} HTTP strings')


if __name__ == '__main__': main()
