"""Index the synthetic Mii DB in stopped test NAND FSTs, preserving metadata.

Host files not present in Dolphin's FST are invisible to emulated IOS. Only
new path components are added; existing records retain all metadata except
the ancestor child counts required by the serialized tree.
"""
import json,struct,sys
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import CHANNELS,stopped
sys.path.insert(0,str(ROOT))
from kwce.dolphin_fst import inspect_fst

def add_file(data,components):
 inspect_fst(data);cursor=0
 def read():
  nonlocal cursor
  row=data[cursor:cursor+32];cursor+=32
  children=[read()for _ in range(struct.unpack_from('>I',row,28)[0])]
  return [row,children]
 tree=read();added=[];parent=tree
 for i,name in enumerate(components):
  found=next((n for n in parent[1]if n[0][:12].split(b'\0')[0]==name.encode('ascii')),None)
  file=i==len(components)-1
  if found is None:
   row=bytearray(32);row[:len(name)]=name.encode('ascii');row[18]=int(file);row[19:22]=bytes([3,3,3])
   found=[bytes(row),[]];parent[1].append(found);added.append(name)
  if bool(found[0][18])!=file:raise ValueError('FST path type collision')
  parent=found
 def dump(node):
  row=bytearray(node[0]);struct.pack_into('>I',row,28,len(node[1]));return bytes(row)+b''.join(dump(n)for n in node[1])
 result=dump(tree);inspect_fst(result)
 return result,added

def main():
 stopped()
 for channel in CHANNELS:
  wii=ROOT/f'workspace/sandbox/{channel}-test-v1/user/Wii';path=wii/'fst.bin'
  target=wii/'shared2/menu/FaceLib/RFL_DB.dat'
  if target.stat().st_size!=779968:raise ValueError('Unexpected synthetic database size')
  data=path.read_bytes();updated,added=add_file(data,['shared2','menu','FaceLib','RFL_DB.dat'])
  backup=PRIVATE/f'{channel}-access-before-mii-index-fst.bin'
  if backup.exists():raise SystemExit('Existing FST snapshot preserved')
  backup.write_bytes(data);path.write_bytes(updated)
  (PRIVATE/f'{channel}-mii-index.json').write_text(json.dumps(dict(added_components=added,before_sha256=sha256(backup),after_sha256=sha256(path),synthetic_db_sha256=sha256(target)),indent=2))
  print(f'{channel}: indexed synthetic Mii path, {len(added)} new components, existing FST metadata preserved')

if __name__=='__main__':main()
