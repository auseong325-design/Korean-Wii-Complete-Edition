"""Use original localized code with local emulator network substitutions.

Mii is absent from 2609a's WC24 allowlist. A separately hashed derivative
replaces one unused Region Select entry in that constant table in the Mii
experiment only. Official binaries and previous runtimes remain preserved.
"""
import json,shutil,struct,sys
from audit_sd import ROOT,sha256
from prepare_channel_access import CHANNELS,register,stopped
import launch_dolphin as launcher
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

HOSTS={
 'votes':['vt.wii.rc24.xyz','vtp.wii.rc24.xyz'],
 'nintendo':['ncc.wiilink24.com','conf.n.wiinoma.com','post.n.wiinoma.com','dol.n.wiinoma.com','entd.wapp.wii.com','entu.wapp.wii.com','ente.wapp.wii.com','entj.wapp.wii.com'],
 'mii-contest':['miicontest24.wiilink.ca','miicontestp24.wiilink.ca'],
}

def main():
 stopped();lib=load_library();runtime={}
 for channel,(revision,title_id,game_id)in CHANNELS.items():
  root=ROOT/f'workspace/sandbox/{channel}-test-v1';user=root/'user'
  source=ROOT/f'workspace/channels/{channel}/build-v{revision}/{channel}-ko-ui-test.wad'
  out=ROOT/f'workspace/channels/{channel}/access-build-v2'
  if out.exists() and channel!='votes':raise SystemExit('Existing v2 preserved')
  out.mkdir(exist_ok=True)
  wad=out/f'{channel}-local-test.wad'
  if not wad.exists():shutil.copy2(source,wad)
  if sha256(wad)!=sha256(source):raise ValueError('Expected unchanged localized WAD')
  title=lib.title.Title();title.load_wad(wad.read_bytes());lib.nand.EmuNAND(user/'Wii').install_title(title)
  rows=[(f'Local{i}_{kind}',host,kind)for i,host in enumerate(HOSTS[channel])for kind in[0,1]]
  patch='[WC24Patch]\n'+''.join('$'+name+'\n'+host+':127.0.0.2:'+str(kind)+'\n'for name,host,kind in rows)+'\n[WC24Patch_Enabled]\n'+''.join('$'+name+'\n'for name,host,kind in rows)
  # Prefix INIs also cover NAND title codes whose internal ID has a maker suffix.
  ini=user/f'GameSettings/{game_id[:3]}.ini';ini.write_text(patch,encoding='ascii')
  meta=dict(channel=channel,title_id=title_id,source_revision=revision,source_wad_sha256=sha256(source),wad_sha256=sha256(wad),changed_contents=[],local_simulation=True,external_network_allowed=False,full_localization_complete=False,network_patch_sha256=sha256(ini))
  if channel=='mii-contest':
   exe=root/'Dolphin-x64/Dolphin.exe';original=exe.read_bytes()
   expected=json.loads((ROOT/'configs/gc-fst-runtime.lock.json').read_text())['output_sha256']
   if sha256(exe)!=expected:raise ValueError('Expected pinned v6 runtime as derivative input')
   ids=[0x0001000148415445,0x000100014841544a,0x0001000148415450,0x0001000248414645,0x000100024841464a,0x0001000248414650,0x0001000248414745,0x000100024841474a,0x0001000248414750,0x0001000148414a45,0x0001000148414a4a,0x0001000148414a50,0x0001000848414c45,0x0001000848414c4a,0x0001000848414c50]
   sequence=struct.pack('<15Q',*ids)
   if original.count(sequence)!=1:raise ValueError('Expected unique complete WC24 title allowlist')
   at=original.index(sequence)+12*8
   updated=original[:at]+struct.pack('<Q',int(title_id,16))+original[at+8:]
   backup=out/'Dolphin-pinned-before.exe'
   if backup.exists():raise ValueError('Runtime snapshot preserved')
   backup.write_bytes(original);exe.write_bytes(updated)
   meta['runtime_patch']=dict(input_sha256=expected,output_sha256=sha256(exe),file_offset=at,changed_bytes=sum(a!=b for a,b in zip(original,updated)),scope='one WC24 allowlist constant: unused Region Select US to Mii Contest US')
  runtime[channel]=dict(sha256=sha256(root/'Dolphin-x64/Dolphin.exe'))
  (out/'build-manifest.json').write_text(json.dumps(meta,indent=2))
  (out.parent/'active-access.json').write_text(json.dumps(dict(revision=2)))
  launcher.scrub_download_tasks(register(channel));launcher.validate(register(channel))
  print(f'{channel}: unchanged localized WAD, prefix network configuration, separate runtime')
 (ROOT/'configs/channel-access-runtime.lock.json').write_text(json.dumps(dict(base='gc-fst-runtime.lock.json',capability_count=0,local_simulation=True,channels=runtime),indent=2))

if __name__=='__main__':main()
