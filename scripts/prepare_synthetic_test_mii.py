"""Install one synthetic local test avatar, never importing a personal Mii.

Database layout/CRC: pinned Mii-Database-Editor public source. Base geometry:
the public MiiContestChannelServer test example, with a new synthetic name and
IDs. No data from the source NAND's avatars is parsed or exposed.
"""
import binascii,json,re,shutil,argparse
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import CHANNELS,stopped

def main():
 stopped()
 ap=argparse.ArgumentParser();ap.add_argument('--revision',type=int,default=2);args=ap.parse_args()
 if args.revision not in [1,2]:raise ValueError('Unknown synthetic avatar revision')
 source=ROOT/'workspace/channels/mii-contest/references/http-server-source/info.go'
 text=source.read_text();candidates=[]
 for match in re.finditer(r'(?:\[\]byte|\[76\]byte)\s*\{([^}]+)\}',text):
  try:data=bytes(int(v.strip(),0)for v in match[1].split(',')if v.strip())
  except ValueError:continue
  if len(data)in(74,76):candidates.append(data[:74])
 for match in re.finditer(r'"([0-9a-fA-F]{148,152})"',text):candidates.append(bytes.fromhex(match[1])[:74])
 if len(candidates)!=1:raise ValueError('Expected exactly one public test-avatar geometry')
 mii=bytearray(candidates[0]);mii[0]&=127;mii[2:22]='LocalTest'.encode('utf-16-be').ljust(20,b'\0')
 mii[24:32]=bytes.fromhex('8000100101000042');mii[54:74]=bytes(20)
 db=bytearray(779968);db[:4]=b'RNOD';db[7404]=128
 db[7424:7432]=b'RNHD'+bytes([255])*4
 db[7432:127432]=(bytes(8)+bytes.fromhex('7fff7fff'))*10000
 # Verify the empty-layout checksum against the independent public writer.
 if binascii.crc_hqx(db[:127454],0)!=0x9aff:raise ValueError('Database layout/CRC mismatch')
 db[4:78]=mii;db[127454:127456]=binascii.crc_hqx(db[:127454],0).to_bytes(2,'big')
 for channel in CHANNELS:
  target=ROOT/f'workspace/sandbox/{channel}-test-v1/user/Wii/shared2/menu/FaceLib/RFL_DB.dat'
  backup=PRIVATE/f'{channel}-access-before-synthetic-mii-v{args.revision}.dat'
  if backup.exists():raise SystemExit('Original clone avatar snapshot preserved')
  shutil.copy2(target,backup);target.write_bytes(db)
  record=dict(profile=channel+'-test-v1-user',synthetic=True,name='LocalTest',avatar_count=1,database_sha256=sha256(target),public_schema_revision='ae6a5372b302f5036f82c21db6a050cff1c486b4')
  (PRIVATE/f'{channel}-synthetic-test-mii-v{args.revision}.json').write_text(json.dumps(record,indent=2))
  print(f'{channel}: one synthetic LocalTest avatar; copied original database privately preserved')

if __name__=='__main__':main()
