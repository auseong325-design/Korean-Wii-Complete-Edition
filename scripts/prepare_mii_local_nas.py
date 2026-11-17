"""Redirect only NAS URLs in the separate Mii experiment to the local stub.

No external authentication or registration is performed. The localized release
and its preserved install remain unchanged.
"""
import json,re,struct,sys
from prepare_channel_access import ROOT,stopped
from audit_sd import sha256
sys.path.insert(0,str(ROOT))
from kwce.channels import load_library

def main():
 stopped();base=ROOT/'workspace/channels/mii-contest';out=base/'access-build-v3'
 if out.exists():raise SystemExit('Existing experiment revision preserved')
 source=base/'access-build-v2/mii-contest-local-test.wad'
 lib=load_library();t=lib.title.Title();t.load_wad(source.read_bytes())
 original=t.get_content_by_index(1);updated=bytearray(original);patches=[]
 sections=[]
 for i in range(18):
  at=struct.unpack_from('>I',original,4*i)[0];size=struct.unpack_from('>I',original,0x90+4*i)[0]
  if size:sections.append((at,at+size))
 for match in re.finditer(rb'https?://naswii\.(?:(?:test|dev)\.)?nintendowifi\.net[^\x00\s]*',original):
  before=match.group();after=re.sub(rb'^https?://[^/]+',b'http://127.0.0.2',before)
  if len(after)>len(before)or not any(a<=match.start()<match.end()<=b for a,b in sections):raise ValueError('NAS string range')
  updated[match.start():match.end()]=after.ljust(len(before),b'\0')
  patches.append(dict(offset=match.start(),old_size=len(before),new_size=len(after)))
 if len(patches)!=6:raise ValueError('Expected six NAS URL constants')
 t.set_content(bytes(updated),1);out.mkdir();wad=out/'mii-contest-local-test.wad';wad.write_bytes(t.dump_wad())
 meta=json.loads((base/'access-build-v2/build-manifest.json').read_text())
 meta.update(wad_sha256=sha256(wad),changed_contents=[1],nas_local_stub=True,nas_url_ranges=patches)
 (out/'build-manifest.json').write_text(json.dumps(meta,indent=2))
 lib.nand.EmuNAND(ROOT/'workspace/sandbox/mii-contest-test-v1/user/Wii').install_title(t)
 (base/'active-access.json').write_text(json.dumps(dict(revision=3)))
 print('Mii experiment v3: six fixed-size NAS URL strings redirected to local stub')

if __name__=='__main__':main()
