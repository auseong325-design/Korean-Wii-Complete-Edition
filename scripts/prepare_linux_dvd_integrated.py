"""Create an isolated offline menu profile with a pinned virtual SD fixture.

No physical SD access, folder synchronization, network or console credentials.
The native candidate is installed only into this new experimental NAND.
"""
import os
import argparse
import configparser
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kwce.linux_runtime import prepare,runtime,digest,content_manifest,validate,stopped,PRIVATE


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--revision',type=int,required=True)
    a=ap.parse_args();stopped()
    source=ROOT/f'workspace/experiments/dvd-native-hook-v{a.revision}'
    record=json.loads((source/'manifest.json').read_text())
    if not record.get('sd_worker_service') or record['source_revision'] not in (34,35,36,37,38):
        raise ValueError('Only the reviewed integrated source is allowed')
    if digest(source/'menu.dol')!=record['sha256']:raise ValueError('Candidate hash mismatch')
    name=prepare('menu');dest=runtime(name);user=dest/'user'
    meta=json.loads((dest/'profile.json').read_text())
    content=user/'Wii/title/00000001/00000002/content'
    tmd=bytearray((content/'title.tmd').read_bytes());patched=(source/'menu-with-card-encoding.dol').read_bytes()
    for i in range(int.from_bytes(tmd[0x1de:0x1e0],'big')):
        at=0x1e4+36*i;cid,index=struct.unpack_from('>IH',tmd,at)
        if index==6:
            (content/f'{cid:08x}.app').write_bytes(patched)
            struct.pack_into('>Q',tmd,at+8,len(patched));tmd[at+16:at+36]=hashlib.sha1(patched).digest();break
    else:raise ValueError('Menu DOL missing in experimental profile')
    (content/'title.tmd').write_bytes(tmd)
    image=user/'Wii/sd.raw'
    with image.open('xb') as f:f.truncate(64*1024*1024)
    def run(*cmd):
        r=subprocess.run(cmd,capture_output=True,text=True)
        if r.returncode:
            (PRIVATE/'dvd-virtual-sd-error.log').write_text(r.stdout+r.stderr)
            raise ValueError('Virtual SD creation failed; private diagnostic saved')
    run('mkfs.fat','-F','16','-i','4b574345',str(image))
    run('mmd','-i',str(image),'::kwce','::kwce/dvd')
    files={'boot.ash':ROOT/f'workspace/experiments/dvd-native-module-v{record["module_revision"]}/player.ash',
           'menu.arc':ROOT/'workspace/experiments/dvd-native-banner-v2/menu.arc',
           'icon.arc':ROOT/'workspace/experiments/dvd-native-icon-v1/icon.arc'}
    if record.get('forwarder'):
        files['player.dol']=ROOT/f'workspace/channels/dvd-player/build-v{record["player_revision"]}/boot.dol'
        if digest(files['player.dol'])!=record['sd_player_sha256']:raise ValueError('Pinned player differs')
    for rel,path in files.items():run('mcopy','-i',str(image),str(path),'::kwce/dvd/'+rel)
    (user/'Pipes').mkdir(exist_ok=True)
    os.mkfifo(user/'Pipes/kwce-gc')
    (user/'Config/WiimoteNew.ini').write_text('[Wiimote1]\nSource = 1\nDevice = Pipe/0/kwce-gc\nButtons/A = `Button A`\nButtons/B = `Button B`\nButtons/Home = `Button START`\nIR/Up = `Axis MAIN Y +`\nIR/Down = `Axis MAIN Y -`\nIR/Left = `Axis MAIN X -`\nIR/Right = `Axis MAIN X +`\n[Wiimote2]\nSource = 0\n[Wiimote3]\nSource = 0\n[Wiimote4]\nSource = 0\n')
    c=configparser.ConfigParser();c.optionxform=str
    c.read(user/'Config/Dolphin.ini');c['Core']['WiiSDCard']='True'
    c['General']['WiiSDCardPath']='/profile/user/Wii/sd.raw'
    with (user/'Config/Dolphin.ini').open('w') as f:c.write(f)
    meta['content_manifest']=content_manifest(user)
    meta['virtual_sd']={'relative_path':'Wii/sd.raw','read_only':True,'sha256':digest(image)}
    meta['dvd_integrated']={'revision':a.revision,'sha256':digest(source/'menu-with-card-encoding.dol')}
    (dest/'profile.json').write_text(json.dumps(meta,indent=2)+'\n')
    catalog=ROOT/'configs/channels.catalog.json';j=json.loads(catalog.read_text())
    j['test_beds'].append({'profile':name,'purpose':'Linux offline integrated DVD/Settings qualification',
                          'native_hook':source.name,'player_build':f'build-v{record["player_revision"]}','platform':'linux',
                          'role':'experimental'})
    catalog.write_text(json.dumps(j,ensure_ascii=False,indent=1)+'\n')
    validate(name)
    print(json.dumps({'profile':name,'revision':a.revision,'virtual_sd_read_only':True,
                      'physical_sd_access':False}))


if __name__=='__main__':main()
