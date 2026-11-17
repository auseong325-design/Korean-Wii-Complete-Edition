"""Create a new isolated DVD test bed without a KDVD title. Never touch real SD."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import stopped


def main():
    stopped()
    source=ROOT/'workspace/sandbox/dvd-test-v2'
    target=ROOT/'workspace/sandbox/dvd-test-v3'
    if target.exists():raise SystemExit('Existing native test bed preserved')
    target.mkdir()
    for folder in ('user','Dolphin-x64','sd-sync','disc'):
        shutil.copytree(source/folder,target/folder,ignore=shutil.ignore_patterns('Logs','Cache','Dump','ScreenShots','StateSaves'))
    shutil.copy2(source/'NetProbe.exe',target/'NetProbe.exe')
    record=json.loads((source/'test-bed-manifest.json').read_text(encoding='utf-8'))
    native=ROOT/'workspace/experiments/dvd-native-hook-v1'
    data=(native/'menu.dol').read_bytes()
    details=json.loads((native/'manifest.json').read_text())
    if hashlib.sha256(data).hexdigest()!=details['sha256']:raise ValueError('Native menu differs')
    content=target/'user/Wii/title/00000001/00000002/content'
    tmd=bytearray((content/'title.tmd').read_bytes())
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==6:
            (content/f'{cid:08x}.app').write_bytes(data)
            struct.pack_into('>Q',tmd,at+8,len(data));tmd[at+16:at+36]=hashlib.sha1(data).digest()
            record['system_menu_contents']['6']=details['sha256'];break
    else:raise ValueError('Menu DOL not found')
    (content/'title.tmd').write_bytes(tmd)
    private=PRIVATE/'dvd-native-v3-removed-title'
    private.mkdir()
    for relative in ('title/00010001/4b445644','ticket/00010001/4b445644.tik'):
        path=(target/'user/Wii'/relative).resolve()
        path.relative_to(target.resolve())
        if path.exists():shutil.move(str(path),str(private/path.name))
    shutil.copy2(ROOT/'workspace/channels/dvd-player/build-v31/boot.dol',target/'sd-sync/kwce/dvd/boot.dol')
    ini=target/'user/Config/Dolphin.ini'
    text=ini.read_text(encoding='utf-8-sig').replace(str(source),str(target)).replace(source.as_posix(),target.as_posix())
    ini.write_text(text,encoding='utf-8')
    helper=ROOT/'tools/dvd-test/v3/bin';helper.mkdir(parents=True)
    code=(ROOT/'tools/dvd-test/v2/bin/DvdTestRunner.cs').read_text().replace('"dvd-test-v2"','"dvd-test-v3"')
    cs=helper/'DvdTestRunner.cs';cs.write_text(code,encoding='utf-8')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/out:'+str(helper/'DvdTestRunner.exe'),str(cs)],check=True,capture_output=True)
    record['helper_sha256']=sha256(helper/'DvdTestRunner.exe')
    record['native_hook']=dict(revision=1,sha256=details['sha256'],player_sha256=details['player_sha256'])
    record['channel_independent']=True
    (target/'test-bed-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PASS new native test bed; KDVD title/ticket absent; original v2 preserved')


if __name__=='__main__':main()
