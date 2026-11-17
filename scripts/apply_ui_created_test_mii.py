"""Apply only the avatar named test that was created in the isolated Mii UI."""
import binascii,json,shutil
from audit_sd import ROOT,PRIVATE,sha256
from prepare_channel_access import CHANNELS,stopped

def main():
 stopped();source=ROOT/'workspace/sandbox/mii-contest-test-v1/user/Wii/shared2/menu/FaceLib/RFL_DB.dat'
 original=source.read_bytes()
 if len(original)!=779968 or binascii.crc_hqx(original[:127454],0)!=int.from_bytes(original[127454:127456],'big'):raise ValueError('UI-created database size/CRC invalid')
 clean=bytearray(original);selected=[]
 for i in range(100):
  at=4+74*i;record=original[at:at+74]
  name=record[2:22].decode('utf-16-be').rstrip('\0')
  if name=='test':selected.append(i)
  else:clean[at:at+74]=bytes(74)
 if len(selected)!=1:raise ValueError('Expected exactly one UI-created test avatar')
 clean[127454:127456]=binascii.crc_hqx(clean[:127454],0).to_bytes(2,'big')
 snapshot=PRIVATE/'channel-access-mii-ui-created-db.dat'
 if snapshot.exists():raise SystemExit('Existing UI database snapshot preserved')
 snapshot.write_bytes(original)
 for channel in CHANNELS:
  target=ROOT/f'workspace/sandbox/{channel}-test-v1/user/Wii/shared2/menu/FaceLib/RFL_DB.dat'
  backup=PRIVATE/f'{channel}-access-before-ui-created-mii.dat'
  if backup.exists():raise SystemExit('Existing avatar backup preserved')
  shutil.copy2(target,backup);target.write_bytes(clean)
  (PRIVATE/f'{channel}-ui-created-test-mii.json').write_text(json.dumps(dict(name='test',synthetic=True,created_in_mii_channel=True,official_slot=selected[0],avatar_count=1,database_sha256=sha256(target)),indent=2))
  print(f'{channel}: one UI-created synthetic test avatar applied; original clone and earlier experiments preserved')

if __name__=='__main__':main()
